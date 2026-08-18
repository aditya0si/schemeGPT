"""Structured quote extraction and verification for SchemeGPT answers.

The live RAG prompts ask the model to quote the exact policy statements it
relies on, in the form ``> <text> [<source>, <data_status>]``. Rather than
trusting that formatting blindly, SchemeGPT parses those lines and verifies
each quote against the retrieved context the answer was generated from. A
quote is *verified* only if its normalized text actually appears in a source,
or is within a tight similarity tolerance of some window of a source.

This is a pure-module (no DB, no LLM): run anywhere, unit-testable.
"""

import difflib
import re
from dataclasses import dataclass

# A quoted statement line: "> <text> [<source>, <data_status>]"
QUOTE_LINE_RE = re.compile(
    r"^\s*>\s*(?P<text>.+?)\s*\[(?P<source>[^\],]+)"
    r"(?:,\s*(?P<status>[a-z_]+))?\]\s*$"
)

# Match is considered verified when the shared-ratio is at least this.
SIMILARITY_THRESHOLD = 0.85
WINDOW_SIZE = 400
WINDOW_STEP = 50


@dataclass
class ParsedQuote:
    text: str
    source: str
    status: str | None


@dataclass
class VerifiedQuote:
    text: str
    source: str
    status: str | None
    verified: bool
    matched_source: str | None


def _norm(text: str) -> str:
    """Lowercase, then collapse punctuation/whitespace (keeps Unicode letters)."""
    return re.sub(r"[^0-9a-z\u0900-\u097f]+", " ", str(text).casefold()).strip()


def parse_quotes(answer_text: str) -> list[ParsedQuote]:
    """Extract all ``> ... [source, status]`` quote lines from an answer."""
    quotes: list[ParsedQuote] = []
    for line in (answer_text or "").splitlines():
        match = QUOTE_LINE_RE.match(line)
        if not match:
            continue
        quotes.append(
            ParsedQuote(
                text=match.group("text").strip(),
                source=match.group("source").strip(),
                status=match.group("status"),
            )
        )
    return quotes


def _windows(content: str):
    """Yield non-overlapping-by-step windows of normalized content."""
    norm = _norm(content)
    if not norm:
        return
    step = max(WINDOW_STEP, 1)
    for start in range(0, len(norm), step):
        yield norm[start:start + WINDOW_SIZE]


def _matches(q_norm: str, source_content: str) -> bool:
    """True if the normalized quote is contained in or closely matches a source."""
    if q_norm in _norm(source_content):
        return True
    # Fallback: sliding-window similarity for lightly rewritten quotes.
    best = 0.0
    for window in _windows(source_content):
        ratio = difflib.SequenceMatcher(None, q_norm, window).ratio()
        if ratio > best:
            best = ratio
        if best >= SIMILARITY_THRESHOLD:
            return True
    return False


def verify_quotes(
    parsed: list[ParsedQuote], sources: list[dict]
) -> list[VerifiedQuote]:
    """Check each parsed quote against the retrieved ``sources`` (list of dicts
    with at least ``source`` and ``content``). A quote sourced in-stream to a
    specific file is only accepted if that file's content actually contains it;
    other source names fall back to matching any retrieved source."""
    verified_out: list[VerifiedQuote] = []
    for quote in parsed:
        matched_source: str | None = None
        verified = False
        # Prefer the quoted source name if present among retrieved sources.
        exact = [
            src for src in sources
            if str(src.get("source", "")).split("/")[-1]
            == str(quote.source).split("/")[-1]
        ]
        candidates = exact or sources
        for src in candidates:
            if _matches(_norm(quote.text), str(src.get("content", ""))):
                verified = True
                matched_source = str(src.get("source", ""))
                break
        verified_out.append(
            VerifiedQuote(
                text=quote.text,
                source=quote.source,
                status=quote.status,
                verified=verified,
                matched_source=matched_source,
            )
        )
    return verified_out
