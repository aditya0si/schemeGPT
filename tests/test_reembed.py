"""Safe re-embedding command contracts."""

from scripts import reembed


def test_reembed_uses_atomic_ingestion_without_preemptive_drop(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("app.ingest.ingest", lambda: calls.append("ingest") or 42)

    result = reembed.main([])

    assert result == 0
    assert calls == ["ingest"]
    assert "atomically rebuilt" in capsys.readouterr().out.casefold()
