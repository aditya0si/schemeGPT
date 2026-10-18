"""Guard the reader-facing portfolio surface of the Next.js app.

These are source-level guards for the parts of the slice that a Python test can
check deterministically without a browser:

* every ``data_status`` the backend can emit has a distinct, truthful label in
  ``web/components/SourceCard.tsx``, and an unknown status is never rendered as
  a neutral "Source";
* ``/evidence`` and ``/coverage`` exist, are linked from the shared header (one
  click from the homepage) and are *not* conditional on the API being
  configured — evidence must be visible on a live deployment, which is exactly
  where the old panel disappeared;
* coverage renders an explicit unavailable state rather than a blank page;
* the README's repo-relative links and images resolve (``tools/check_doc_links.py``).

The browser-level rendering of the same surfaces, including the keyboard path and
a narrow viewport, is exercised by ``web/e2e/journey.mjs``; these tests keep the
contract from drifting when nobody runs a browser.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SOURCE_CARD = WEB / "components" / "SourceCard.tsx"
CHROME = WEB / "components" / "Chrome.tsx"
EVIDENCE_PAGE = WEB / "app" / "evidence" / "page.tsx"
COVERAGE_PAGE = WEB / "app" / "coverage" / "page.tsx"
COVERAGE_LOADING = WEB / "app" / "coverage" / "loading.tsx"

# Statuses the backend can emit, established from the code that writes them.
_EXPECTED_BACKEND_STATUSES = {
    "sample_verified",
    "directory_seed",
    "myscheme_import",
    "unknown",
}
_STATUS_LITERAL_RE = re.compile(r'"([a-z][a-z0-9_]*)"')
_ENTRY_RE = re.compile(
    r"^\s{2}(?P<status>[a-z][a-z0-9_]*):\s*\{\s*\n\s*label:\s*\"(?P<label>[^\"]+)\"",
    re.MULTILINE,
)


def _load_doc_link_checker():
    spec = importlib.util.spec_from_file_location(
        "check_doc_links", ROOT / "tools" / "check_doc_links.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _label_map() -> dict[str, str]:
    text = SOURCE_CARD.read_text(encoding="utf-8")
    return {m.group("status"): m.group("label") for m in _ENTRY_RE.finditer(text)}


def _backend_statuses() -> set[str]:
    found: set[str] = set()
    for path in sorted((ROOT / "app").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "data_status" not in line:
                continue
            for literal in _STATUS_LITERAL_RE.findall(line):
                if literal == "data_status":
                    continue
                found.add(literal)
    return found


def test_backend_status_vocabulary_is_what_this_test_expects():
    """Guard the guard: if the status vocabulary moves, revisit the labels."""
    assert _backend_statuses() == _EXPECTED_BACKEND_STATUSES


def test_every_backend_status_has_a_distinct_reader_facing_label():
    labels = _label_map()
    missing = sorted(_EXPECTED_BACKEND_STATUSES - set(labels))
    assert missing == [], (
        f"SourceCard.tsx has no label for {missing}; an unmapped status must be a "
        f"test failure, not a fallback"
    )
    assert set(labels) == _EXPECTED_BACKEND_STATUSES, (
        "SourceCard.tsx labels a status the backend cannot emit: "
        f"{sorted(set(labels) - _EXPECTED_BACKEND_STATUSES)}"
    )
    values = list(labels.values())
    assert len(set(values)) == len(values), f"labels must be distinguishable: {labels}"
    assert set(values) == {
        "Verified",
        "Directory seed",
        "Imported · unverified",
        "Provenance unlabelled",
    }, f"labels changed unexpectedly: {labels}"


def test_source_card_never_falls_back_to_a_neutral_label():
    text = SOURCE_CARD.read_text(encoding="utf-8")
    assert 'label: "Source"' not in text, (
        "the neutral 'Source' fallback is exactly the defect this slice fixes: an "
        "imported or unrecognised record must say so"
    )
    assert "Unrecognised status" in text, (
        "an unknown data_status must render its raw value rather than nothing"
    )
    assert "no per-document source URL stored" in text, (
        "a source without a URL must say the URL is absent instead of implying one"
    )
    assert "no verification date on record" in text, (
        "a source without last_verified must say the date is absent"
    )


def test_header_links_the_evidence_and_coverage_routes():
    text = CHROME.read_text(encoding="utf-8")
    for route in ("/evidence", "/coverage"):
        assert f'href="{route}"' in text, f"the shared header does not link {route}"
    assert "<nav" in text and 'aria-label="Site"' in text


@pytest.mark.parametrize("path", [EVIDENCE_PAGE, COVERAGE_PAGE, COVERAGE_LOADING])
def test_route_files_exist_and_are_non_trivial(path: Path):
    assert path.exists(), f"{path.relative_to(ROOT)} is missing"
    assert len(path.read_text(encoding="utf-8")) > 400


def test_evidence_route_does_not_depend_on_the_api():
    text = EVIDENCE_PAGE.read_text(encoding="utf-8")
    for forbidden in ("apiConfigured", "API_URL", "fetch("):
        assert forbidden not in text, (
            f"/evidence must render its measured cards even when an API is "
            f"configured, asleep or absent; found {forbidden!r}"
        )
    assert "MetricsPanel" in text


def test_metrics_panel_is_shared_with_the_offline_state():
    metrics_panel = (WEB / "components" / "MetricsPanel.tsx").read_text(encoding="utf-8")
    offline = (WEB / "components" / "OfflinePanel.tsx").read_text(encoding="utf-8")
    assert "MetricsPanel" in offline, "the offline state must render the same panel"
    for runtime_key in ("mrrAt4Runtime", "mrrAt4Int8", "mrrAt4Int8Runtime"):
        assert runtime_key in metrics_panel, (
            f"the UI must show MRR@4 with its runtime label; {runtime_key} unused"
        )


def test_coverage_route_declares_all_three_states():
    text = COVERAGE_PAGE.read_text(encoding="utf-8")
    for testid in (
        "coverage-unconfigured",
        "coverage-unavailable",
        "coverage-report",
    ):
        assert testid in text, f"/coverage is missing its {testid} state"
    assert "coverage_note" in text, "/coverage must reproduce the API's own coverage note"
    assert "<a" in COVERAGE_PAGE.read_text(encoding="utf-8")


def test_readme_repo_relative_links_resolve():
    checker = _load_doc_link_checker()
    problems, _notes = checker.scan([ROOT / name for name in checker.DEFAULT_FILES])
    assert problems == [], "\n".join(problems)


def test_readme_hero_image_is_a_real_tracked_file():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "raw.githubusercontent.com/aditya0si/schemeGPT/main/docs/demo.png" not in text, (
        "the README must not point its hero image at a file that was never committed"
    )
    match = re.search(r"^!\[[^\]]*\]\((?P<src>[^)\s]+)\)", text, re.MULTILINE)
    assert match, "the README has no leading image"
    src = match.group("src")
    assert not src.startswith("http"), f"hero image must be a repo-relative asset, got {src}"
    asset = ROOT / src
    assert asset.exists(), f"hero image {src} is not committed"
    assert asset.stat().st_size > 20_000, f"{src} is too small to be a real screenshot"


def test_docs_do_not_instruct_against_a_dead_host():
    checker = _load_doc_link_checker()
    problems, _notes = checker.scan([ROOT / "README.md", ROOT / "docs" / "DEPLOY.md"])
    assert problems == [], "\n".join(problems)
    deploy = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    assert "## Superseded: the Fly.io path" in deploy, (
        "the superseded deployment path must stay documented as history"
    )
    assert "render.yaml" in deploy and "Dockerfile.render" in deploy, (
        "the runbook must describe the topology that actually works"
    )
