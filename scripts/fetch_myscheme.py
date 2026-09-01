"""Fetch the myScheme corpus from the Apache-2.0 Hugging Face dataset
``shrijayan/gov_myscheme`` (723 scheme PDFs captured from myscheme.gov.in),
extract text, strip page chrome, and write one Markdown file per scheme into
``data/myscheme/`` for ingestion.

Why this source: myscheme.gov.in allows crawling in robots.txt but its Terms
of Use restrict scraping tools, so we do NOT scrape the live site. The
dataset is a published, licensed redistribution of the same public scheme
pages; every generated record links back to the official myScheme page.

Usage:
    python scripts/fetch_myscheme.py --limit 10     # smoke run
    python scripts/fetch_myscheme.py                # full corpus (~600 docs)

Dedup: the dataset ships duplicated files ("X.pdf" and "X copy.pdf") and some
near-identical scheme pages; slugs are deduplicated and exact duplicate text
is skipped via a content hash. Re-runs are incremental: files whose content
hash is unchanged are not rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "data" / "myscheme"
CACHE_DIR = ROOT_DIR / "data" / ".cache" / "myscheme_pdfs"

DATASET_TREE_API = (
    "https://huggingface.co/api/datasets/shrijayan/gov_myscheme/"
    "tree/main/text_data?limit=1000"
)
DATASET_RAW_URL = (
    "https://huggingface.co/datasets/shrijayan/gov_myscheme/resolve/main/"
)
USER_AGENT = "SchemeGPT-corpus-fetch/1.0 (research; hf dataset Apache-2.0)"

# Page chrome captured by the PDF printer, not scheme content. The footer
# repeats the header block ("... Share Check Eligibility Ministry Of ..."),
# so extraction is structural: content lives between the first ministry
# header block and the footer marker.
CHROME_NOISE = [
    r"Are\s+you\s+sure\s+you\s+want\s+to\s+sign\s+out\?\s*CancelSign\s+Out",
    r"You\s+need\s+to\s+sign\s+in\s+before\s+applying\s+for\s+schemes\s*CancelSign\s+In",
    r"It\s+seems\s+you\s+have\s+already\s+initiated\s+your\s+application"
    r"\s+earlier\.?\s*To\s+know\s+more\s+please\s+visit\s*CancelApply\s+Now",
    r"Something\s+went\s+wrong\.\s*Please\s+try\s+again\s+later\.Ok",
]
FOOTER_MARKERS = ["News and Updates", "Share Check Eligibility"]
SECTION_ORDER = [
    "Details",
    "Benefits",
    "Eligibility",
    "Application Process",
    "Documents Required",
    "Frequently Asked Questions",
    "Sources And References",
]
_SECTION_RE = re.compile(
    "|".join(re.escape(s) for s in SECTION_ORDER)
)


def _http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _list_dataset_files() -> list[str]:
    """All unique PDF filenames, paginating the HF tree API via Link headers.

    The dataset ships 'X.pdf' + 'X copy.pdf' duplicates; ' copy' files are
    dropped and the rest are sorted + deduplicated by name.
    """
    names: list[str] = []
    url: str | None = DATASET_TREE_API
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
            link = resp.headers.get("Link") or ""
        names.extend(
            entry["path"].split("/")[-1]
            for entry in payload
            if entry["path"].endswith(".pdf") and " copy" not in entry["path"]
        )
        next_url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part[part.find("<") + 1 : part.find(">")]
        url = next_url
    return sorted(set(names))


def _strip_title_suffix(title: str) -> str:
    """Drop the trailing page-tag (' - Studies', ' - Agriculture', ...)."""
    return re.sub(r"\s+-\s+[A-Za-z&+ ]{2,40}$", "", title).strip()


def _state_names() -> list[str]:
    """The 36 state/UT names from the curated directory, longest first."""
    catalog = json.loads(
        (ROOT_DIR / "data" / "india_states.json").read_text(encoding="utf-8")
    )
    records = catalog["records"] if isinstance(catalog, dict) else catalog
    names = [r["name"] for r in records]
    return sorted(names, key=len, reverse=True)


# Common cp1252-decoded-as-UTF-8 mojibake sequences from pypdf extraction.
# Targeted replacements only: these byte sequences never occur in legit text.
MOJIBAKE_MAP = {
    "â€™": "’",
    "â€˜": "‘",
    "â€œ": "“",
    "â€\x9d": "”",
    "â€​": "”",
    "â€": "”",
    "â€œ": "“",
    "â‚¹": "₹",
    "â€“": "–",
    "â€”": "—",
    "â€¦": "…",
    "â€¢": "•",
    "Â ": " ",
    "Â": "",
    "Ã©": "é",
    "Ã¨": "è",
    "Ã¤": "ä",
    "Ã¶": "ö",
    "Ã¼": "ü",
    "Ã±": "ñ",
}


def clean_text(raw: str) -> str:
    """Normalize PDF text: fix mojibake, tabs, and stray spacing."""
    text = raw.replace("ï»¿", " ").replace("\ufeff", " ").replace("\t", " ")
    for bad, good in MOJIBAKE_MAP.items():
        text = text.replace(bad, good)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_core(text: str, state_names: list[str]) -> dict | None:
    """Structural extraction, or None when the page layout is unrecognized.

    The myScheme page layout is: [title][nav chrome]...Check Eligibility
    <jurisdiction: 'Ministry Of <name>' or a state/UT name>[repeated title]
    [tags] <sections...> [footer repeat]. Content is everything from the
    first 'Check Eligibility' header block to the footer; the title comes
    from the page head before the chrome.
    """
    anchor = text.find("Check Eligibility")
    if anchor == -1:
        return None
    head = text[:anchor]
    for pattern in CHROME_NOISE:
        head = re.sub(pattern, " ", head)
    head = re.split(r"EngEnglish|Sign\s+In|Back\s", head)[0].strip(" -")
    title = _strip_title_suffix(head) if head else ""
    if len(title) < 4:
        return None

    core = text[anchor + len("Check Eligibility") :]
    # Cut the footer repeat: it re-announces 'Check Eligibility' + header.
    second = core.find("Check Eligibility")
    if second != -1:
        core = core[:second]
    for marker in FOOTER_MARKERS:
        idx = core.find(marker)
        if idx != -1:
            core = core[:idx]

    # Jurisdiction: an explicit ministry block or a known state/UT name.
    ministry = state = None
    ministry_match = re.match(r"\s*Ministry\s+Of\s+([A-Za-z&' ]{3,80})", core)
    if ministry_match:
        ministry = ministry_match.group(1).strip()
    else:
        prefix = core[:120]
        for name in state_names:
            if prefix.startswith(name):
                state = name
                break

    # The title repeats right after the jurisdiction block; drop it so the
    # first section body does not start with a duplicated headline.
    dedup_target = title[:24]
    if dedup_target and dedup_target in core[: len(title) + 320]:
        core = core.replace(dedup_target, "", 1)
    return {
        "title": title,
        "ministry": ministry,
        "state": state,
        "core": core.strip(),
    }


def split_sections(core: str) -> dict[str, str]:
    """Split the core content on the known section headers, in order."""
    matches = list(_SECTION_RE.finditer(core))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(core)
        body = core[match.end() : end].strip(" -\n")
        if body:
            sections[match.group(0)] = body
    return sections


def pdf_to_markdown(pdf_path: Path, slug: str, state_names: list[str]) -> str | None:
    """One PDF -> cleaned Markdown record, or None when unusable."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(pdf_path))
        raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        print(f"  skip {slug}: pdf parse failed ({type(exc).__name__})")
        return None

    text = clean_text(raw)
    extracted = extract_core(text, state_names)
    if extracted is None:
        print(f"  skip {slug}: unrecognized page layout")
        return None
    core = extracted["core"]
    if len(core) < 350:
        print(f"  skip {slug}: too little content after cleaning ({len(core)} chars)")
        return None

    sections = split_sections(core)
    official_url = f"https://www.myscheme.gov.in/schemes/{slug}"

    lines = [f"# {extracted['title']}", ""]
    if extracted["ministry"]:
        lines += [f"**Ministry:** {extracted['ministry']}", ""]
    if extracted["state"]:
        lines += [f"**State/UT:** {extracted['state']}", ""]
    lines += [
        "## Source",
        "",
        f"- **Official source:** {official_url}",
        "- **Origin:** myScheme national portal (dataset capture, "
        "Apache-2.0); verify on the official portal before applying.",
        "- **Data status:** myscheme_import",
        "",
        "## Jurisdiction",
        "",
    ]
    if extracted["state"]:
        lines.append(f"- **Jurisdiction:** {extracted['state']} (as listed on myScheme)")
    else:
        lines.append(
            "- **Jurisdiction:** central (as listed on myScheme)"
        )
    lines += [
        "This is an automated import, not a hand-verified record.",
        "",
    ]
    for section in SECTION_ORDER:
        if section in sections:
            header = "FAQs" if section == "Frequently Asked Questions" else section
            lines += [f"## {header}", "", sections[section], ""]
    # Pages with no recognizable headers: keep the raw core so nothing
    # content-bearing is silently dropped.
    if not sections:
        lines += ["## Details", "", core, ""]
    lines += [
        "## Disclaimer",
        "",
        "This record is an automated import from the myScheme portal and may "
        "be incomplete or outdated. It is not official advice; always verify "
        "eligibility and process on the official portal before applying.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=None, help="fetch only the first N schemes"
    )
    parser.add_argument(
        "--sleep", type=float, default=0.3, help="seconds between downloads"
    )
    args = parser.parse_args()

    try:
        import pypdf  # noqa: F401
    except ImportError:
        print("pypdf is required: pip install pypdf", file=sys.stderr)
        return 2

    names = _list_dataset_files()
    print(f"dataset lists {len(names)} unique PDFs")
    if args.limit:
        names = names[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    written = skipped_dupe = failed = 0
    seen_content: set[str] = set()
    state_names = _state_names()
    for i, name in enumerate(names, 1):
        slug = Path(name).stem
        out_path = OUT_DIR / f"{slug}.md"
        cache_path = CACHE_DIR / name
        try:
            if not cache_path.exists():
                data = _http_get(DATASET_RAW_URL + f"text_data/{name}", timeout=120)
                cache_path.write_bytes(data)
                time.sleep(args.sleep)
            else:
                data = cache_path.read_bytes()
        except Exception as exc:
            print(f"  skip {slug}: download failed ({type(exc).__name__})")
            failed += 1
            continue

        content_hash = hashlib.md5(data).hexdigest()
        if content_hash in seen_content:
            skipped_dupe += 1
            continue
        seen_content.add(content_hash)

        markdown = pdf_to_markdown(cache_path, slug, state_names)
        if markdown is None:
            failed += 1
            continue
        if out_path.exists() and out_path.read_text(encoding="utf-8") == markdown:
            continue  # incremental: unchanged
        out_path.write_text(markdown, encoding="utf-8")
        written += 1
        if i % 25 == 0:
            print(f"  progress {i}/{len(names)} (written={written})")

    print(
        f"done: {written} written, {skipped_dupe} exact duplicates skipped, "
        f"{failed} failed -> {OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
