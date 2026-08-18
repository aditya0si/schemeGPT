"""Re-embed the vector store after changing the embedding model.

Deletes this collection's existing vectors and re-ingests every Markdown source
with the configured embedding model. Idempotent afterwards.

Usage:
    python scripts/reembed.py --yes
    python -m pip show --quiet sentence-transformers  # model downloads on demand

Requires a running database (docker compose up -d db). --yes is required:
deleting vectors is destructive-until-reingest and must be explicit.
"""

import argparse
import sys
from pathlib import Path

# Direct invocation (`python scripts/reembed.py`) must see the repo root.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import logging  # noqa: E402

from sqlalchemy import text  # noqa: E402

logging.basicConfig(level=logging.INFO)

from app.config import settings  # noqa: E402
from app.db import COLLECTION_NAME, get_engine  # noqa: E402


def _delete_collection_vectors() -> int:
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                "DELETE FROM langchain_pg_embedding "
                "WHERE collection_id IN ("
                "  SELECT c.uuid FROM langchain_pg_collection c WHERE c.name = :name"
                ")"
            ),
            {"name": COLLECTION_NAME},
        )
        return result.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes", action="store_true", help="confirm deletion of existing vectors"
    )
    args = parser.parse_args()
    if not args.yes:
        print(
            "This deletes the existing vector store so it can be re-embedded "
            "with the configured model. Refusing without --yes.",
            file=sys.stderr,
        )
        return 2

    deleted = _delete_collection_vectors()
    print(f"Deleted {deleted or 0} existing vector(s).")

    from app.ingest import ingest

    chunks = ingest()
    print(
        f"Re-ingested with embedding model '{settings.embedding_model}' "
        f"({chunks} chunks). Restart the API to clear the stale provenance warning."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
