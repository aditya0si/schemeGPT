"""Ingestion for SchemeGPT.

Loads the central scheme Markdown docs from the configured data directory and
the nationwide state/Union Territory directory seed docs from ``data/states``
(when present), splits them into chunks, enriches every chunk with catalog
metadata (``source``, ``jurisdiction``, ``state``, ``data_status``,
``last_verified``), embeds the complete corpus before any database write, and
atomically upserts source-aware chunks while deleting stale rows.

The state directory is picked up automatically: a stale ``DATA_DIR=data/schemes``
value in ``.env`` does not need to be edited, and ``DATA_DIR=data`` (the data
root) is also supported via a recursive scan.

Chunk ids include canonical source, position, and content. Identical policy
boilerplate in different files therefore retains each file's provenance.
"""

import hashlib
import json
import logging
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import text

from app.catalog import load_schemes_by_source, load_states_catalog, slugify
from app.config import ROOT_DIR, data_dir_path, settings
from app.db import (
    VECTOR_GENERATION_COLUMN,
    VECTOR_ID_COLUMN,
    VECTOR_METADATA_COLUMN,
    VECTOR_TABLE,
    ensure_fts_index,
    ensure_vector_table,
    get_embeddings,
    get_engine,
    record_corpus_state,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
INGEST_ADVISORY_LOCK_ID = 0x53434845  # stable application-scoped "SCHE" lock


def _data_root() -> Path:
    return (ROOT_DIR / "data").resolve()


def _plan_directories(configured: Path) -> list[Path]:
    """Markdown source directories to scan (deduplicated, in order).

    - If the configured directory is the data root itself (``data``), scan that
      root recursively so ``schemes/``, ``states/`` and ``myscheme/`` are all
      covered.
    - Otherwise load the configured directory plus the ``data/states`` and
      ``data/myscheme`` directories when they exist, so the nationwide
      directory and the myScheme import corpus are ingested without manual
      ``.env`` edits.
    """
    root = configured.resolve()
    data_root = _data_root()
    directories: list[Path] = [root]
    if root != data_root:
        for extra in ("states", "myscheme"):
            extra_dir = data_root / extra
            if extra_dir.is_dir() and extra_dir.resolve() != root:
                directories.append(extra_dir)

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
    elif rel_source.startswith("myscheme/"):
        # Automated imports from the myScheme portal: honest provenance so
        # the answer layer can distinguish them from verified records.
        meta["jurisdiction"] = "myscheme_import"
        meta["data_status"] = "myscheme_import"
    return meta


def _load_markdown_documents(directory: Path, recursive: bool) -> list[Document]:
    """Read UTF-8 Markdown sources without the heavyweight community loaders."""
    pattern = "**/*.md" if recursive else "*.md"
    return [
        Document(
            page_content=path.read_text(encoding="utf-8"),
            metadata={"source": str(path)},
        )
        for path in sorted(directory.glob(pattern))
        if path.is_file()
    ]


def _chunk_id(rel_source: str, chunk_index: int, content: str) -> str:
    """Stable source-and-position-aware chunk id; duplicate text never aliases."""
    identity = f"{rel_source}\0{chunk_index}\0{content}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _corpus_generation(rows: list[dict], model_name: str) -> str:
    """Deterministic generation id covering model, content, ids, and provenance."""
    canonical = json.dumps(
        {"embedding_model": model_name, "rows": rows},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def _acquire_activation_lock(connection) -> None:
    """Serialize corpus activation across every API worker.

    ``pg_advisory_xact_lock`` is transaction-scoped, so it is held until the
    enclosing transaction commits or rolls back. It MUST be the first statement
    of the activation transaction: two concurrent rebuilds then cannot
    interleave their upsert, stale-row deletion, or state-marker writes and
    leave a mixed-generation corpus behind.
    """
    connection.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": INGEST_ADVISORY_LOCK_ID},
    )


def _replace_corpus(rows: list[dict]) -> int:
    """Embed fully, then atomically activate all current rows and remove stale ones."""
    if not rows:
        raise ValueError("No Markdown chunks found; refusing to replace the corpus.")

    generation = _corpus_generation(rows, settings.embedding_model)
    vectors = get_embeddings().embed_documents([row["content"] for row in rows])
    if len(vectors) != len(rows) or not vectors or not vectors[0]:
        raise RuntimeError("Embedding model returned incomplete corpus vectors.")
    vector_size = len(vectors[0])
    if any(len(vector) != vector_size for vector in vectors):
        raise RuntimeError("Embedding model returned inconsistent vector dimensions.")

    # No database mutation occurs until every embedding is available. Table
    # existence is prepared outside the lock (idempotent schema setup); the
    # activation below is serialized by a transaction-scoped advisory lock and
    # commits once, so readers see either the previous or the new generation.
    ensure_vector_table(vector_size)
    params = [
        {
            "chunk_id": row["id"],
            "content": row["content"],
            "embedding": _vector_literal(vector),
            "metadata": json.dumps(row["metadata"], ensure_ascii=False),
            "generation": generation,
        }
        for row, vector in zip(rows, vectors, strict=True)
    ]
    with get_engine().begin() as conn:
        _acquire_activation_lock(conn)
        conn.execute(
            text(
                f"INSERT INTO {VECTOR_TABLE} "
                f"({VECTOR_ID_COLUMN}, content, embedding, "
                f"{VECTOR_METADATA_COLUMN}, {VECTOR_GENERATION_COLUMN}) "
                "VALUES (:chunk_id, :content, CAST(:embedding AS vector), "
                "CAST(:metadata AS JSON), :generation) "
                f"ON CONFLICT ({VECTOR_ID_COLUMN}) DO UPDATE SET "
                "content = EXCLUDED.content, embedding = EXCLUDED.embedding, "
                f"{VECTOR_METADATA_COLUMN} = EXCLUDED.{VECTOR_METADATA_COLUMN}, "
                f"{VECTOR_GENERATION_COLUMN} = EXCLUDED.{VECTOR_GENERATION_COLUMN}"
            ),
            params,
        )
        conn.execute(
            text(
                f"DELETE FROM {VECTOR_TABLE} "
                f"WHERE {VECTOR_GENERATION_COLUMN} IS DISTINCT FROM :generation"
            ),
            {"generation": generation},
        )
        record_corpus_state(
            model_name=settings.embedding_model,
            generation=generation,
            chunk_count=len(rows),
            connection=conn,
        )
        # FTS lives in the same transaction as the rows it indexes. A missing
        # column would silently degrade evaluation to vector-only, so a failure
        # rolls the whole activation back (fail closed) instead of committing a
        # corpus that cannot be searched textually.
        ensure_fts_index(connection=conn)
    return len(rows)


def ingest(data_dir: Path | None = None) -> int:
    """Reconcile the vector table atomically with all current Markdown sources."""
    configured = (data_dir or data_dir_path()).resolve()
    data_root = _data_root()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    rows: list[dict] = []
    source_positions: dict[str, int] = {}

    for directory in _plan_directories(configured):
        if not directory.is_dir():
            logger.warning("Ingest directory not found; skipping: %s", directory)
            continue
        docs = _load_markdown_documents(
            directory, recursive=directory == data_root
        )
        for chunk in splitter.split_documents(docs):
            rel_source = _relative_source(
                Path(chunk.metadata["source"]), data_root
            )
            chunk_index = source_positions.get(rel_source, 0)
            source_positions[rel_source] = chunk_index + 1
            metadata = {
                **_chunk_metadata(rel_source),
                "chunk_index": chunk_index,
            }
            rows.append(
                {
                    "id": _chunk_id(rel_source, chunk_index, chunk.page_content),
                    "content": chunk.page_content,
                    "metadata": metadata,
                }
            )

    return _replace_corpus(rows)
