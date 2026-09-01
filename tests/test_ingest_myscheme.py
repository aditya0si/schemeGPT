"""Unit tests for myScheme import ingestion metadata and directory planning."""

import pytest

from app import ingest


def test_plan_directories_includes_myscheme(tmp_path, monkeypatch):
    """data/myscheme is ingested alongside schemes/ and states/ without
    any .env edit, and is skipped when absent."""
    (tmp_path / "schemes").mkdir()
    (tmp_path / "states").mkdir()
    (tmp_path / "myscheme").mkdir()
    monkeypatch.setattr(ingest, "_data_root", lambda: tmp_path)

    plan = ingest._plan_directories(tmp_path / "schemes")
    resolved = {p.name for p in plan}
    assert resolved == {"schemes", "states", "myscheme"}

    # Without the myscheme directory the plan is unchanged.
    (tmp_path / "myscheme").rmdir()
    plan = ingest._plan_directories(tmp_path / "schemes")
    assert {p.name for p in plan} == {"schemes", "states"}


def test_chunk_metadata_tags_myscheme_imports():
    """Chunks from data/myscheme carry honest import provenance."""
    meta = ingest._chunk_metadata("myscheme/pm-kisan-like.md")
    assert meta["source"] == "myscheme/pm-kisan-like.md"
    assert meta["data_status"] == "myscheme_import"
    assert meta["jurisdiction"] == "myscheme_import"


def test_chunk_metadata_states_and_schemes_unchanged():
    assert ingest._chunk_metadata("states/karnataka.md")["data_status"] in (
        "directory_seed",
        None,
    )
    central = ingest._chunk_metadata("schemes/pm-kisan.md")
    assert central["jurisdiction"] == "central"
