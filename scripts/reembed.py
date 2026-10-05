"""Atomically rebuild SchemeGPT vectors after corpus or model changes.

Usage:
    python scripts/reembed.py

The ingestion pipeline computes every embedding before opening its replacement
transaction. Existing rows remain active if embedding or database work fails;
there is no pre-emptive table drop.
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app.ingest as ingestion  # noqa: E402
from app.config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help=argparse.SUPPRESS,  # accepted for backward-compatible automation
    )
    parser.parse_args(argv)

    chunks = ingestion.ingest()
    print(
        f"Atomically rebuilt '{settings.embedding_model}' corpus "
        f"with {chunks} chunks. Restart the API to clear cached retrievers."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
