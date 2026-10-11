"""Deterministic temporal ("answer as of a date") quality gate for SchemeGPT.

Phase 8 / track 1, **Task 3**. This is the regression gate for the as-of answer
path built in Task 2. Like the retrieval gate it needs no LLM, no provider and
no network: :func:`app.temporal_answer.temporal_answer` is a pure function of the
committed dated-claims artifact, and the golden set is **derived** from that same
artifact by ``scripts/generate_temporal_golden.py``.

Metrics
-------
Every metric below is a **consistency floor**, not a quality estimate. The
answer is a pure function of a frozen artifact, so a correct implementation
scores exactly 1.000 (or exactly 0.000 for era-mixing) and any deviation is a
bug. There is deliberately no "quality" number here: the golden set is derived
from the artifact the function reads, so it cannot estimate generalisation to
unseen temporal questions -- it can only prove the artifact is obeyed. The
honest floor for a consistency metric *is* its exact value.

* ``as_of_accuracy``        -- the value in force is the artifact's governing
  claim (greatest ``effective_from <= as_of``).
* ``boundary_accuracy``     -- inclusive on the effective date, exclusive the day
  before (the ``effective_date`` and ``day_before`` cases only).
* ``supersession_accuracy`` -- the answer names the right replacement *and* its
  date, or correctly states the latest value is still in force with no invented
  successor.
* ``era_mixing_rate``       -- share of cases whose payload presents a value from
  an interval that does not contain ``as_of`` as the in-force value. Target 0.
* ``refusal_accuracy``      -- pre-range, unmatched and artifact-missing cases
  all refuse honestly and never substitute a current/latest value.
* ``invariance``            -- with ``--check-default-mode`` the ordinary
  retrieval gate still reports its frozen numbers; otherwise not measured.

Era-mixing, precisely
---------------------
A payload is **era-mixed** when it presents, as the answer for the requested
date, a value whose declared effective interval does not contain ``as_of``:

* an answer payload is era-mixed when the amount in its "*value in force ... is
  ₹X*" clause is not the governing claim's value (this is the failure mode of
  serving today's value for a past date, or a past value for today); and
* a refusal payload is era-mixed when it presents *any* in-force amount at all,
  i.e. when it substitutes a value instead of refusing.

A payload that honestly refuses a case which expected an answer is an as-of
miss, not an era-mix: no wrong-era value was presented as current.

Usage::

    ./.venv/Scripts/python.exe -m eval.temporal_gate
    ./.venv/Scripts/python.exe -m eval.temporal_gate --check-default-mode
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import app.temporal_answer as temporal_answer_mod
from app.temporal_answer import temporal_answer

EVAL_DIR = Path(__file__).resolve().parent
ROOT_DIR = EVAL_DIR.parent
GOLDEN_FILE = EVAL_DIR / "fixtures" / "temporal_golden.jsonl"
RESULTS_FILE = EVAL_DIR / "results" / "temporal_scores.json"
REPORT_FILE = EVAL_DIR / "results" / "temporal_report.md"

# Consistency floors. These are exact because the answer is a pure function of
# the artifact; they are not fitted to a measured score.
AS_OF_ACCURACY_FLOOR = 1.0
BOUNDARY_ACCURACY_FLOOR = 1.0
SUPERSESSION_ACCURACY_FLOOR = 1.0
REFUSAL_ACCURACY_FLOOR = 1.0
INVARIANCE_FLOOR = 1.0
# Era-mixing is a rate to be minimised; its ceiling is zero.
ERA_MIXING_CEILING = 0.0

BOUNDARY_KINDS = ("effective_date", "day_before")

# The frozen retrieval-gate numbers the as-of feature must not perturb (R4).
RETRIEVAL_EXPECTED = {
    "labelled_cases": 16,
    "completed_cases": 16,
    "error_count": 0,
    "hit_rate_at_k": 0.875,
    "mrr_at_k": 0.796875,
}

# Parsing the payload. The in-force clause is language-specific; the refusal
# markers cover every fail-closed branch.
_IN_FORCE_RE = re.compile(r"the value in force for .*? is \u20b9\s*([\d,]+)")
_IN_FORCE_HI_RE = re.compile(r"\u0932\u093e\u0917\u0942 \u092e\u093e\u0928 \u20b9\s*([\d,]+)")
_AMOUNT_RE = re.compile(r"\u20b9\s*([\d,]+)")
_REFUSAL_MARKERS = (
    "current or latest value has been substituted",
    "\u092a\u094d\u0930\u0924\u093f\u0938\u094d\u0925\u093e\u092a\u093f\u0924 \u0928\u0939\u0940\u0902 \u0915\u093f\u092f\u093e \u0917\u092f\u093e",
)
_NO_SUCCESSOR_MARKER = "most recent declared value"
_SUPERSEDED_MARKER = "took over"


def _amount(value: int) -> str:
    return f"\u20b9{value:,}"


def _presented_value(answer: str) -> int | None:
    """The amount the payload presents as the value in force, or ``None``."""
    for pattern in (_IN_FORCE_RE, _IN_FORCE_HI_RE):
        match = pattern.search(answer)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _amounts(answer: str) -> list[int]:
    return [int(raw.replace(",", "")) for raw in _AMOUNT_RE.findall(answer)]


def _is_refusal(answer: str) -> bool:
    lowered = answer.casefold()
    return any(marker.casefold() in lowered for marker in _REFUSAL_MARKERS)


def load_golden(path: Path | None = None) -> tuple[dict, list[dict]]:
    """Load the JSONL golden set into ``(header, records)``."""
    fixture = Path(path) if path is not None else GOLDEN_FILE
    if not fixture.is_file():
        raise FileNotFoundError(f"golden set not found: {fixture.as_posix()}")
    header: dict = {}
    records: list[dict] = []
    for line_number, line in enumerate(
        fixture.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{fixture.as_posix()}:{line_number}: invalid JSON: {exc}"
            ) from exc
        if obj.get("type") == "header":
            header = obj
            continue
        for key in ("id", "kind", "question", "as_of", "expect"):
            if key not in obj:
                raise ValueError(
                    f"{fixture.as_posix()}:{line_number}: missing key {key!r}"
                )
        records.append(obj)
    if not records:
        raise ValueError(f"{fixture.as_posix()} has zero cases")
    return header, records


def _artifact_missing_probe() -> dict:
    """Exercise the missing-artifact branch as a synthetic refusal case."""
    missing = Path("no/such/temporal_claims.jsonl")
    original = temporal_answer_mod.claims_fixture_path
    temporal_answer_mod.claims_fixture_path = lambda: missing
    try:
        temporal_answer_mod._load_claims_from.cache_clear()
        payload = temporal_answer("fadcs", "2021-01-01", "en")
    finally:
        temporal_answer_mod.claims_fixture_path = original
        temporal_answer_mod._load_claims_from.cache_clear()
    return {
        "id": "artifact_missing#refuse",
        "kind": "artifact_missing",
        "source": None,
        "question": "fadcs",
        "as_of": "2021-01-01",
        "expect": "refuse",
        "refusal_reason": "missing",
        "_payload": payload,
    }


def evaluate_case(record: dict, answer_fn=temporal_answer) -> dict:
    """Evaluate one golden record against the as-of answer function."""
    payload = record.get("_payload") or answer_fn(
        record["question"], record["as_of"], "en"
    )
    answer = payload.get("answer", "") or ""
    sources = payload.get("sources") or []
    presented = _presented_value(answer)
    answered = presented is not None
    mode_ok = payload.get("mode") == temporal_answer_mod.AS_OF_MODE
    refusal_marker = _is_refusal(answer)

    expected_value = record.get("expected_value")
    successor_value = record.get("successor_value")
    successor_date = record.get("successor_effective_from")

    as_of_correct = None
    boundary_correct = None
    supersession_correct = None
    refusal_correct = None

    if record["expect"] == "answer":
        as_of_correct = answered and presented == expected_value
        if record["kind"] in BOUNDARY_KINDS:
            boundary_correct = as_of_correct
        if successor_value is None:
            supersession_correct = (
                as_of_correct
                and _NO_SUCCESSOR_MARKER in answer.casefold()
                and _SUPERSEDED_MARKER not in answer.casefold()
                and set(_amounts(answer)) <= {expected_value}
            )
        else:
            supersession_correct = (
                as_of_correct
                and _amount(successor_value) in answer
                and str(successor_date) in answer
                and _SUPERSEDED_MARKER in answer.casefold()
            )
        era_mixed = answered and presented != expected_value
    else:
        refusal_correct = (
            not answered and not sources and mode_ok and refusal_marker
        )
        era_mixed = answered or bool(sources)

    return {
        "id": record["id"],
        "kind": record["kind"],
        "source": record.get("source"),
        "as_of": record["as_of"],
        "expect": record["expect"],
        "presented_value": presented,
        "answered": answered,
        "as_of_correct": as_of_correct,
        "boundary_correct": boundary_correct,
        "supersession_correct": supersession_correct,
        "refusal_correct": refusal_correct,
        "era_mixed": era_mixed,
    }


def _rate(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def evaluate(records: list[dict], answer_fn=temporal_answer) -> dict:
    """Score every golden case plus the artifact-missing probe."""
    probe = _artifact_missing_probe()
    evaluated = list(records) + [probe]
    rows = [evaluate_case(record, answer_fn) for record in evaluated]

    answer_rows = [row for row in rows if row["expect"] == "answer"]
    refusal_rows = [row for row in rows if row["expect"] == "refuse"]
    boundary_rows = [row for row in rows if row["kind"] in BOUNDARY_KINDS]
    era_mixed = sum(1 for row in rows if row["era_mixed"])

    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1

    return {
        "cases": len(rows),
        "golden_cases": len(records),
        "kinds": kinds,
        "counts": {
            "answer_expected": len(answer_rows),
            "refusal_expected": len(refusal_rows),
            "boundary_cases": len(boundary_rows),
            "supersession_cases": len(answer_rows),
            "era_mixing_cases": len(rows),
        },
        "as_of_accuracy": _rate(rows, "as_of_correct"),
        "boundary_accuracy": _rate(rows, "boundary_correct"),
        "supersession_accuracy": _rate(rows, "supersession_correct"),
        "era_mixing_rate": era_mixed / len(rows) if rows else None,
        "era_mixing_count": era_mixed,
        "refusal_accuracy": _rate(rows, "refusal_correct"),
        "rows": rows,
    }


def check_default_mode_retrieval() -> dict:
    """Re-run the retrieval gate and compare against the frozen numbers (R4)."""
    from eval import retrieval_gate

    scratch = ROOT_DIR / "var" / "temporal_default_mode_scores.json"
    try:
        summary, failures = retrieval_gate.run(output=scratch)
    except Exception as exc:  # DB unavailable / no generation recorded
        return {
            "metric": 0.0,
            "passed": False,
            "expected": dict(RETRIEVAL_EXPECTED),
            "observed": None,
            "gate_failures": [f"{type(exc).__name__}: {exc}"],
        }
    observed = {name: summary.get(name) for name in RETRIEVAL_EXPECTED}
    passed = observed == RETRIEVAL_EXPECTED and not failures
    return {
        "metric": 1.0 if passed else 0.0,
        "passed": passed,
        "expected": dict(RETRIEVAL_EXPECTED),
        "observed": observed,
        "gate_failures": list(failures),
    }


def gate_failures(summary: dict) -> list[str]:
    """Return every breached floor, including coverage and invariance."""
    failures: list[str] = []
    cases = int(summary.get("cases") or 0)
    if cases == 0:
        failures.append("coverage: golden set has no cases")
    if not summary.get("counts", {}).get("refusal_expected"):
        failures.append("coverage: golden set has no refusal cases")
    for name, floor in (
        ("as_of_accuracy", AS_OF_ACCURACY_FLOOR),
        ("boundary_accuracy", BOUNDARY_ACCURACY_FLOOR),
        ("supersession_accuracy", SUPERSESSION_ACCURACY_FLOOR),
        ("refusal_accuracy", REFUSAL_ACCURACY_FLOOR),
    ):
        value = summary.get(name)
        if value is None:
            failures.append(f"{name}: missing")
        elif float(value) < floor:
            failures.append(f"{name}: {float(value):.3f} < {floor:.3f}")
    era_mixing = summary.get("era_mixing_rate")
    if era_mixing is None:
        failures.append("era_mixing_rate: missing")
    elif float(era_mixing) > ERA_MIXING_CEILING:
        failures.append(
            f"era_mixing_rate: {float(era_mixing):.3f} > {ERA_MIXING_CEILING:.3f}"
        )
    invariance = summary.get("invariance")
    if invariance is not None and float(invariance) < INVARIANCE_FLOOR:
        failures.append(
            f"invariance: {float(invariance):.3f} < {INVARIANCE_FLOOR:.3f}"
        )
    return failures


def _fmt(value) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def _write_report(summary: dict, report: Path, check_default_mode: bool) -> None:
    provenance = summary.get("provenance", {})
    counts = summary.get("counts", {})
    kinds = summary.get("kinds", {})
    lines: list[str] = []
    lines.append("# SchemeGPT Temporal (As-Of) Gate Report")
    lines.append("")
    lines.append(
        "Deterministic, keyless, offline. The as-of answer is a pure function "
        "of the committed dated-claims artifact, so every temporal metric is a "
        "**consistency floor**, not a quality estimate."
    )
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(
        f"- Golden set: `{summary['fixture']}` "
        f"({summary['golden_cases']} derived cases + 1 artifact-missing probe)"
    )
    lines.append(
        f"- Artifact: `{provenance.get('artifact', 'n/a')}` "
        f"({provenance.get('artifact_claims', '?')} claims, "
        f"{provenance.get('ladders', '?')} ladders, "
        f"{provenance.get('artifact_documents', '?')} documents)"
    )
    lines.append(
        "- Generator: `scripts/generate_temporal_golden.py` (regenerate with "
        "`./.venv/Scripts/python.exe scripts/generate_temporal_golden.py`)"
    )
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value | Floor | Verdict |")
    lines.append("| --- | ---: | ---: | --- |")
    checks = (
        ("as_of_accuracy", AS_OF_ACCURACY_FLOOR, "floor", ">="),
        ("boundary_accuracy", BOUNDARY_ACCURACY_FLOOR, "floor", ">="),
        ("supersession_accuracy", SUPERSESSION_ACCURACY_FLOOR, "floor", ">="),
        ("era_mixing_rate", ERA_MIXING_CEILING, "ceiling", "<="),
        ("refusal_accuracy", REFUSAL_ACCURACY_FLOOR, "floor", ">="),
        ("invariance", INVARIANCE_FLOOR, "floor", ">="),
    )
    for name, floor, _kind, direction in checks:
        value = summary.get(name)
        if value is None:
            verdict = "not measured"
        elif direction == ">=":
            verdict = "pass" if float(value) >= floor else "FAIL"
        else:
            verdict = "pass" if float(value) <= floor else "FAIL"
        lines.append(f"| `{name}` | {_fmt(value)} | {floor:.3f} | {verdict} |")
    lines.append("")
    lines.append("## Consistency floors vs quality estimates")
    lines.append("")
    lines.append(
        "- `as_of_accuracy`, `boundary_accuracy`, `supersession_accuracy` and "
        "`refusal_accuracy` are **consistency floors**: the answer is a pure "
        "function of the frozen artifact, so the honest floor is exactly "
        "1.000. `era_mixing_rate` is a consistency **ceiling** of exactly 0.000."
    )
    lines.append(
        "- There is no quality-estimate metric. The golden set is derived from "
        "the same artifact the function reads, so it cannot estimate "
        "generalisation to unseen temporal questions; it proves the artifact "
        "is obeyed, and the honest value of that proof is exact."
    )
    lines.append(
        "- `invariance` is a consistency floor tied to the retrieval gate's "
        "frozen numbers; it is only measured under `--check-default-mode` "
        "(which needs the database)."
    )
    lines.append("")
    lines.append("## Case coverage")
    lines.append("")
    lines.append(
        f"- Answer-expected: {counts.get('answer_expected', 0)}; "
        f"refusal-expected: {counts.get('refusal_expected', 0)}; "
        f"boundary: {counts.get('boundary_cases', 0)}; "
        f"supersession: {counts.get('supersession_cases', 0)}; "
        f"era-mixing denominator: {counts.get('era_mixing_cases', 0)}"
    )
    lines.append("")
    lines.append("| Kind | Cases |")
    lines.append("| --- | ---: |")
    for kind in sorted(kinds):
        lines.append(f"| `{kind}` | {kinds[kind]} |")
    lines.append("")
    lines.append("## Era-mixing definition")
    lines.append("")
    lines.append(
        "A payload is era-mixed when it presents, as the answer for the "
        "requested date, a value whose declared effective interval does not "
        "contain `as_of`: an answer is era-mixed when the amount in its "
        "\"*value in force ... is*\" clause is not the governing claim's value; "
        "a refusal is era-mixed when it presents any in-force amount instead of "
        "refusing. An honest refusal of a case that expected an answer is an "
        "as-of miss, not an era-mix."
    )
    lines.append("")
    lines.append("## Invariance")
    lines.append("")
    retrieval = summary.get("retrieval")
    if not check_default_mode or retrieval is None:
        lines.append(
            "Not measured in this invocation. Run "
            "`python -m eval.temporal_gate --check-default-mode` (requires the "
            "database) to re-run the retrieval gate and assert its frozen "
            "numbers:"
        )
        lines.append("")
        lines.append(
            "- Frozen expectation: "
            f"{RETRIEVAL_EXPECTED['completed_cases']}/"
            f"{RETRIEVAL_EXPECTED['labelled_cases']} complete, "
            f"hit@4 {RETRIEVAL_EXPECTED['hit_rate_at_k']}, "
            f"mrr@4 {RETRIEVAL_EXPECTED['mrr_at_k']}"
        )
    else:
        observed = retrieval.get("observed")
        lines.append(
            f"- Retrieval gate re-run: `{observed}`"
        )
        lines.append(f"- Frozen expectation: `{retrieval.get('expected')}`")
        lines.append(
            f"- Result: {'pass' if retrieval.get('passed') else 'FAIL'}"
        )
        if retrieval.get("gate_failures"):
            lines.append(f"- Retrieval gate failures: {retrieval['gate_failures']}")
    lines.append("")
    failures = summary.get("gate", {}).get("failures", [])
    lines.append("## Gate verdict")
    lines.append("")
    if failures:
        lines.append(f"**FAILED** ({len(failures)} floor breach(es)):")
        lines.append("")
        for failure in failures:
            lines.append(f"- {failure}")
    else:
        lines.append("**PASSED** -- every measured consistency floor is met.")
    lines.append("")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    golden: Path | None = None,
    output: Path | None = None,
    report: Path | None = None,
    check_default_mode: bool = False,
    answer_fn=temporal_answer,
) -> tuple[dict, list[str]]:
    # Resolve module constants at CALL time, never bind them as default
    # arguments, so redirecting them (tests, tooling) writes where intended.
    golden = Path(golden) if golden is not None else GOLDEN_FILE
    output = Path(output) if output is not None else RESULTS_FILE
    report = Path(report) if report is not None else REPORT_FILE

    header, records = load_golden(golden)
    summary = evaluate(records, answer_fn=answer_fn)
    try:
        summary["fixture"] = golden.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        summary["fixture"] = golden.as_posix()
    summary["provenance"] = header

    if check_default_mode:
        retrieval = check_default_mode_retrieval()
        summary["retrieval"] = retrieval
        summary["invariance"] = retrieval["metric"]
    else:
        summary["retrieval"] = None
        summary["invariance"] = None

    failures = gate_failures(summary)
    summary["gate"] = {
        "passed": not failures,
        "failures": failures,
        "floors": {
            "as_of_accuracy": AS_OF_ACCURACY_FLOOR,
            "boundary_accuracy": BOUNDARY_ACCURACY_FLOOR,
            "supersession_accuracy": SUPERSESSION_ACCURACY_FLOOR,
            "era_mixing_rate": ERA_MIXING_CEILING,
            "refusal_accuracy": REFUSAL_ACCURACY_FLOOR,
            "invariance": INVARIANCE_FLOOR,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_report(summary, report, check_default_mode)
    return summary, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the deterministic as-of answer path without an "
        "LLM key."
    )
    parser.add_argument("--golden", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--check-default-mode",
        action="store_true",
        help="also re-run the retrieval gate and assert its frozen numbers "
        "(requires the database; not used in the keyless CI job)",
    )
    args = parser.parse_args(argv)

    try:
        summary, failures = run(
            golden=args.golden,
            output=args.output,
            report=args.report,
            check_default_mode=args.check_default_mode,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"TEMPORAL GATE FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "Temporal gate: "
        f"{summary['golden_cases']} golden cases (+1 probe), "
        f"as_of={summary['as_of_accuracy']}, "
        f"boundary={summary['boundary_accuracy']}, "
        f"supersession={summary['supersession_accuracy']}, "
        f"era_mixing={summary['era_mixing_rate']}, "
        f"refusal={summary['refusal_accuracy']}, "
        f"invariance={summary['invariance']}"
    )
    if failures:
        for failure in failures:
            print(f"TEMPORAL GATE FAILED: {failure}")
        return 1
    print(
        "Gate passed. Results: "
        f"{(Path(args.output) if args.output else RESULTS_FILE).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
