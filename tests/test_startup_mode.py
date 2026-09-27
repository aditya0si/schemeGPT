from unittest.mock import MagicMock

import pytest

from app import main


@pytest.mark.anyio
async def test_demo_startup_does_not_load_embedding_model(monkeypatch):
    monkeypatch.setattr(main.profiles, "init_table", MagicMock())
    monkeypatch.setattr(main, "count_vectors", lambda: 0)
    ingest = MagicMock()
    monkeypatch.setattr(main.ingest, "ingest", ingest)
    ensure_fts = MagicMock()
    monkeypatch.setattr("app.db.ensure_fts_index", ensure_fts)
    monkeypatch.setattr(main.settings, "enable_auto_ingest", False)

    async with main.lifespan(main.app):
        pass

    ingest.assert_not_called()
    ensure_fts.assert_not_called()


@pytest.mark.anyio
async def test_live_startup_ingests_empty_store(monkeypatch):
    monkeypatch.setattr(main.profiles, "init_table", MagicMock())
    monkeypatch.setattr(main, "count_vectors", lambda: 0)
    ingest = MagicMock()
    monkeypatch.setattr(main.ingest, "ingest", ingest)
    ensure_fts = MagicMock()
    monkeypatch.setattr("app.db.ensure_fts_index", ensure_fts)
    monkeypatch.setattr(main.settings, "enable_auto_ingest", True)

    async with main.lifespan(main.app):
        pass

    ingest.assert_called_once_with()
    ensure_fts.assert_called_once_with()