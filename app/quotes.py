"""Structured quote extraction and source-bound verification.

The live RAG prompts ask the model to quote exact policy statements as
``> <text> [<source>, <data_status>]``. SchemeGPT parses those lines and only
marks a quote verified when the named retrieved source contains the text and
its declared status agrees with the retrieved provenance.
"""

import re
from dataclasses import dataclass

QUOTE_LINE_RE = re.compile(
    r"^\s*>\s*(?P<text>.+?)\s*\[(?P<source>[^\],]+)"
    r"(?:,\s*(?P<status>[a-z_]+))?\]\s*$"
)


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


def _source_id(value: str) -> str:
    """Return a stable, case-insensitive data-root-relative source identifier."""
    return str(value or "").replace("\\", "/").removeprefix("./").lstrip("/").casefold()


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


def _matches(q_norm: str, source_content: str) -> bool:
    """True only when the normalized quote is an exact source substring."""
    return bool(q_norm) and q_norm in _norm(source_content)


def verify_quotes(
    parsed: list[ParsedQuote], sources: list[dict]
) -> list[VerifiedQuote]:
    """Verify quote text and provenance against the specifically named source.

    There is intentionally no fallback to another retrieved source. Otherwise,
    a model could hallucinate a source name while quoting real text from a
    different document and SchemeGPT would incorrectly label it verified.
    """
    verified_out: list[VerifiedQuote] = []
    for quote in parsed:
        matched_source: str | None = None
        verified = False
        quoted_source = _source_id(quote.source)
        candidates = [
            src
            for src in sources
            if quote.status is not None
            and _source_id(str(src.get("source", ""))) == quoted_source
        ]
        for src in candidates:
            source_status = src.get("data_status")
            if (
                source_status is None
                or str(source_status).casefold() != quote.status.casefold()
            ):
                continue
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
