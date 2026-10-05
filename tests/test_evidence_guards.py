"""Guards for the repository's frozen evidence.

* ``test_evidence_manifest_matches_committed_bytes`` fails when a tracked
  evidence file drifts from ``evidence/manifest.json``.
* ``test_manifest_covers_every_tracked_evidence_file`` fails when the tracked
  set changes.
* ``test_evidence_paths_have_no_unexpected_files`` fails when a scratch file is
  dropped into a guarded directory.
* ``test_published_retrieval_figures_appear_in_readme`` re-derives the
  published hit/mrr/case/floor figures from the committed evidence and checks
  the exact literals are present in ``README.md``.
* The redirect tests prove the module constants -- not import-time default
  arguments -- decide where a writer lands.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools import evidence_manifest as em

README = em.ROOT / "README.md"
GATE_MD = em.ROOT / "docs" / "evidence" / "RETRIEVAL-GATE.md"


def _load_manifest() -> dict[str, str]:
    if not em.MANIFEST_FILE.is_file():
        return {"<evidence/manifest.json is missing>": ""}
    return em.read_manifest()


MANIFEST = _load_manifest()


@pytest.mark.parametrize("relpath", sorted(MANIFEST))
def test_evidence_manifest_matches_committed_bytes(relpath):
    declared = MANIFEST[relpath]
    actual = em.compute_manifest().get(relpath)
    assert actual == declared, (
        f"{relpath} drifted from the frozen evidence manifest "
        f"({declared} -> {actual}). If the measurement genuinely changed, "
        f"rebaseline deliberately with `{em.REBASELINE_COMMAND}` and commit the "
        f"diff; never edit a published number to silence this guard."
    )


def test_manifest_covers_every_tracked_evidence_file():
    declared = set(em.read_manifest())
    actual = set(em.tracked_files())
    assert declared == actual, (
        f"tracked evidence files and the manifest disagree "
        f"(missing from manifest: {sorted(actual - declared)}; "
        f"stale in manifest: {sorted(declared - actual)}). "
        f"Rebaseline with `{em.REBASELINE_COMMAND}`."
    )


def test_evidence_paths_have_no_unexpected_files():
    unexpected = em.unexpected_files()
    assert unexpected == [], (
        "untracked files appeared under a guarded evidence path: "
        f"{unexpected}. Remove them, or commit/ignore them deliberately."
    )


def _gate_table(text: str) -> dict[str, str]:
    table: dict[str, str] = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0]:
            table[cells[0]] = cells[1]
    return table


def test_published_retrieval_figures_appear_in_readme():
    table = _gate_table(GATE_MD.read_text(encoding="utf-8"))
    hit = table["Hit@4"]
    mrr = table["MRR@4"]
    cases = table["Cases completed"]
    hit_floor = table["Hit@4 floor"]
    mrr_floor = table["MRR@4 floor"]

    # The frozen record must encode the verified measurement. 2026-10-06: the
    # lexical tie-break was made deterministic, which removed the plan-dependent
    # 0.875 and produced a reproducible 0.8125 below the Hit@4 floor.
    assert (hit, mrr, cases) == ("0.8125", "0.75", "16/16")
    assert (hit_floor, mrr_floor) == ("0.85", "0.60")

    # ...and README must quote those exact characters.
    readme = README.read_text(encoding="utf-8")
    for literal in (hit, mrr, cases, hit_floor, mrr_floor):
        assert literal in readme, (
            f"README.md no longer quotes the published literal {literal!r} "
            f"derived from docs/evidence/RETRIEVAL-GATE.md"
        )


def _sixteen_labelled_cases() -> list[dict]:
    return [
        {"id": f"case-{index}", "question": f"q{index}", "expected_sources": ["schemes/a.md"]}
        for index in range(16)
    ]


def test_retrieval_gate_default_output_reads_constant_at_call_time(monkeypatch):
    import app.db as db
    import app.rag as rag
    from eval import retrieval_gate

    monkeypatch.setattr(db, "read_corpus_generation", lambda: "gen-evidence")
    monkeypatch.setattr(
        rag, "get_retriever", lambda corpus_generation=None: _Retriever()
    )
    monkeypatch.setattr(
        retrieval_gate, "_load_questions", lambda limit: _sixteen_labelled_cases()
    )

    summary, failures = retrieval_gate.run()

    assert failures == []
    assert retrieval_gate.RESULTS_FILE.is_file(), (
        "run() with no explicit output must write to the module-level "
        "RESULTS_FILE read at call time (the conftest fixture redirects it "
        "into tmp_path)"
    )
    assert summary["completed_cases"] == 16


def test_run_eval_writers_read_constants_at_call_time():
    from eval import run_eval

    run_eval.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_eval._write_scores([], {}, "2026-10-05T00:00:00+00:00", 0, None)

    assert run_eval.SCORES_FILE.is_file()
    assert run_eval.SCORES_FILE.parent == run_eval.RESULTS_DIR


class _Retriever:
    def invoke(self, question):
        return [SimpleNamespace(metadata={"source": "schemes/a.md"})]
