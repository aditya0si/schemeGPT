"""Ingestion for SchemeGPT.

Loads the central scheme Markdown docs from the configured data directory and
the nationwide state/Union Territory directory seed docs from ``data/states``
(when present), splits them into chunks, enriches every chunk with catalog
metadata (``source``, ``jurisdiction``, ``state``, ``data_status``,
``last_verified``), and adds vectors with content-hash ids so re-runs are
idempotent and existing vectors are never deleted.

The state directory is picked up automatically: a stale ``DATA_DIR=data/schemes``
value in ``.env`` does not need to be edited, and ``DATA_DIR=data`` (the data
root) is also supported via a recursive scan.

Chunks are identified by a content hash. Ids that already exist in the vector
collection are not re-inserted: their metadata is refreshed in place when the
catalog metadata changes, so runs stay idempotent and existing vectors are
never deleted.
"""

import hashlib
import json
import logging
from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from sqlalchemy import text

from app.catalog import load_schemes_by_source, load_states_catalog, slugify
from app.config import ROOT_DIR, data_dir_path, settings
from app.db import COLLECTION_NAME, get_engine, get_vectorstore

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def _data_root() -> Path:
    return (ROOT_DIR / "data").resolve()


def _plan_directories(configured: Path) -> list[Path]:
    """Markdown source directories to scan (deduplicated, in order).

    - If the configured directory is the data root itself (``data``), scan that
      root recursively so ``schemes/`` and ``states/`` are both covered.
    - Otherwise load the configured directory plus ``data/states`` when it
      exists, so the nationwide directory is ingested without manual ``.env``
      edits.
    """
    root = configured.resolve()
    data_root = _data_root()
    directories: list[Path] = [root]
    if root != data_root:
        states_dir = data_root / "states"
        if states_dir.is_dir() and states_dir.resolve() != root:
            directories.append(states_dir)

    seen: set[str] = set()
    ordered: list[Path] = []
    for directory in directories:
        key = str(directory.resolve())
        if key not in seen:
            seen.add(key)
            ordered.append(directory)
    return ordered


def _relative_source(path: Path, data_root: Path) -> str:
    """Data-root-relative filename used as the ``source`` chunk metadata."""
    try:
        return path.resolve().relative_to(data_root).as_posix()
    except ValueError:
        return path.name


def _state_name_from_filename(rel_source: str) -> str | None:
    """Fallback jurisdiction name from ``india_states.json`` when the catalog
    lookup misses (e.g. the catalog file predates a newly added state file)."""
    if not rel_source.startswith("states/"):
        return None
    filename = Path(rel_source).stem
    for record in load_states_catalog():
        if slugify(record.get("name", "")) == filename:
            return record.get("name")
    return None


def _existing_id_metadata() -> dict[str, dict]:
    """Map content-hash id -> stored metadata for this vector collection.

    PGVector's ``add_texts`` performs a plain insert (no upsert), so ids that
    already exist are either skipped (idempotent) or have only their metadata
    refreshed in place. Existing vectors are never deleted.
    """
    try:
        with get_engine().connect() as conn:
            table_exists = conn.execute(
                text("SELECT to_regclass('public.langchain_pg_embedding')")
            ).scalar()
            if table_exists is None:
                return {}
            rows = conn.execute(
                text(
                    "SELECT e.custom_id, e.cmetadata "
                    "FROM langchain_pg_embedding e "
                    "JOIN langchain_pg_collection c ON e.collection_id = c.uuid "
                    "WHERE c.name = :name AND e.custom_id IS NOT NULL"
                ),
                {"name": COLLECTION_NAME},
            ).fetchall()
        return {
            row[0]: (row[1] or {}) for row in rows
        }
    except Exception:
        logger.warning(
            "Could not query existing vector ids; treating the store as empty.",
            exc_info=True,
        )
        return {}


def _update_chunk_metadata(updates: list[tuple[str, dict]]) -> None:
    """Refresh metadata of already-ingested chunks in place (no vector changes)."""
    if not updates:
        return
    with get_engine().begin() as conn:
        for chunk_id, meta in updates:
            conn.execute(
                text(
                    "UPDATE langchain_pg_embedding SET cmetadata = :meta "
                    "WHERE custom_id = :chunk_id AND collection_id IN ("
                    "  SELECT c.uuid FROM langchain_pg_collection c WHERE c.name = :collection"
                    ")"
                ),
                {"meta": json.dumps(meta), "chunk_id": chunk_id, "collection": COLLECTION_NAME},
            )


def _chunk_metadata(rel_source: str) -> dict:
    """Enrich a chunk with catalog metadata when available."""
    meta: dict = {"source": rel_source}
    record = load_schemes_by_source().get(rel_source)
    if record:
        meta["data_status"] = record.get("data_status")
        meta["last_verified"] = record.get("last_verified")
        meta["jurisdiction"] = record.get("jurisdiction")
        meta["source_url"] = record.get("source_url")
        if record.get("type") in ("state", "union_territory"):
            meta["state"] = record.get("name")
        return meta

    # Catalog record unavailable: derive from the source location only.
    if rel_source.startswith("states/"):
        name = _state_name_from_filename(rel_source)
        if name:
            meta["jurisdiction"] = name
            meta["state"] = name
        meta["data_status"] = "directory_seed"
    elif rel_source.startswith("schemes/"):
        meta["jurisdiction"] = "central"
    return meta


def ingest(data_dir: Path | None = None) -> int:
    """Ingest all Markdown sources; returns the total number of chunks."""
    configured = (data_dir or data_dir_path()).resolve()
    data_root = _data_root()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    existing_metadata = _existing_id_metadata()

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    metadata_updates: list[tuple[str, dict]] = []
    total_chunks = 0

    for directory in _plan_directories(configured):
        if not directory.is_dir():
            logger.warning("Ingest directory not found; skipping: %s", directory)
            continue
        loader = DirectoryLoader(
            str(directory),
            glob="*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            recursive=directory == data_root,
        )
        docs = loader.load()
        chunks = splitter.split_documents(docs)
        total_chunks += len(chunks)
        for chunk in chunks:
            rel_source = _relative_source(
                Path(chunk.metadata["source"]), data_root
            )
            chunk_id = hashlib.md5(chunk.page_content.encode("utf-8")).hexdigest()
            meta = _chunk_metadata(rel_source)
            previous = existing_metadata.get(chunk_id)
            if previous is None:
                # New content: insert a new vector.
                texts.append(chunk.page_content)
                metadatas.append(meta)
                ids.append(chunk_id)
            elif previous != meta:
                # Same content already ingested: refresh metadata only.
                metadata_updates.append((chunk_id, meta))

    if texts:
        get_vectorstore().add_texts(texts=texts, metadatas=metadatas, ids=ids)
    _update_chunk_metadata(metadata_updates)
    # Record which embedding model produced this collection's vectors so
    # startup can warn when the configured model changes (see app.db).
    from app.db import record_embedding_model

    record_embedding_model(settings.embedding_model)
    return total_chunks
