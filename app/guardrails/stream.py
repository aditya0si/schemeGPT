"""Overlap-buffered PII redaction for the streaming answer path (Phase 6c).

Phase 6b protects the synchronous ``POST /query`` path. ``POST /query/stream``
is a separate egress path with a property the synchronous one does not have: an
identifier (or a placeholder) can be **split across two chunks**. Running a
recognizer over each chunk independently therefore misses
``...1234 1234`` | `` 1234...`` and emits the raw identifier. This module fixes
that with a bounded hold-back: only text that is far enough from the buffered
edge to be safe is emitted; a tail is held until more arrives (or the stream
ends), then transformed as one span.

Request-scoped by construction
-----------------------------
A :class:`StreamRedactor` is built around one :class:`~app.guardrails.vault.Vault`
for one request. It adds no mapping of its own. Two streams that overlap in time
hold two separate vaults, so neither can restore the other's placeholders.

Redact *and* restore, one pass
------------------------------
The same machinery runs both directions on every safe span:

1. restore the placeholders the inbound question produced *before* generation,
   so the citizen sees their own value;
2. redact any identifier found in the streamed text (defence in depth: a value
   the model echoed raw, or one lifted from a source excerpt);
3. restore the pre-generation placeholders again, because step 2 re-tokenises
   the values step 1 put back.

Placeholders minted in step 2 for identifiers that were *not* in the question
stay redacted: they are not in the pre-generation snapshot, so step 3 leaves
them alone.

The hold-back size and why
--------------------------
``HOLDBACK = 64`` characters. It is derived, not guessed. The longest **bounded**
match any recognizer can produce is the 15-character GSTIN
(``[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}``); Aadhaar is 14 in its 4-4-4
grouping, mobile 13 with ``+91 ``, IFSC 11, PAN 10. The longest placeholder is
``[[PII:`` (6) + 8 (nonce) + 1 + ``DEVANAGARI_DIGITS`` (17, the longest kind) + 1
+ index digits + ``]]`` (2) = 35 + index digits; a request's matches are bounded
by the 2000-character question cap, so the index is at most four digits and the
placeholder is at most 39. **64** is the next power of two above both 15 and 39,
leaving headroom: a bounded match or placeholder that is at most 64 characters
long can never be emitted half-formed.

Two recognizers are **unbounded** -- the UPI local part/handle
(``[A-Za-z0-9._-]*@...``) and the Devanagari-digit run (``[...]{4,}``) -- so no
finite hold-back covers them. They are handled separately: :meth:`_safe_end`
never emits into a trailing run of identifier-continuation characters, so an
open, not-yet-terminated candidate is retained whole until a delimiter arrives
or the stream ends. Holding a delimiter-free run is bounded by that run's
length, not by the whole stream; ordinary prose has whitespace, so streaming
latency is preserved.
"""

from __future__ import annotations

from app.guardrails.recognizers import find_all
from app.guardrails.vault import PLACEHOLDER_RE, Vault

# See the module docstring for the derivation. 64 = next power of two above the
# longest bounded recognizer match (GSTIN, 15) and the longest placeholder (39).
HOLDBACK = 64

# Characters that can sit *inside* an open identifier candidate: ASCII letters
# and digits, the UPI local-part punctuation, and Devanagari numerals. A
# trailing, unterminated run of these is never emitted, so an unbounded
# recognizer pattern (UPI, Devanagari run) cannot lose its prefix at a chunk
# boundary. Whitespace and brackets terminate a run, including the single space
# or hyphen inside an Aadhaar grouping -- that fixed 14-character form is
# covered by ``HOLDBACK``.
_CANDIDATE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._@+-"
    "\u0966\u0967\u0968\u0969\u096a\u096b\u096c\u096d\u096e\u096f"
)


class StreamRedactor:
    """Bounded overlap buffer that redacts/restores one request's token stream.

    Feed chunk text with :meth:`feed`; it returns the safe prefix to emit (which
    may be empty). Call :meth:`flush` exactly once when the stream completes to
    emit the held tail transformed as a whole. Call :meth:`discard` instead on
    any non-completion path (client disconnect, mid-stream error) so no held
    fragment is ever emitted.
    """

    def __init__(
        self,
        vault: Vault,
        pre_generation_placeholders=(),
        *,
        enabled: bool = True,
        holdback: int = HOLDBACK,
    ) -> None:
        self._vault = vault
        self._enabled = enabled
        self._holdback = max(0, holdback)
        self._pre_generation = frozenset(pre_generation_placeholders)
        self._buffer = ""

    @classmethod
    def for_question(
        cls, question: str, *, enabled: bool = True
    ) -> tuple["StreamRedactor", str]:
        """Build a redactor and return it with the redacted question.

        One fresh :class:`Vault` is created and used for both the question and
        the outbound stream -- a single request-scoped mapping, never two.
        """
        vault = Vault()
        redacted_question, _ = vault.tokenize(question)
        pre = PLACEHOLDER_RE.findall(redacted_question)
        return cls(vault, pre, enabled=enabled), redacted_question

    # -- lifecycle --------------------------------------------------------
    def feed(self, text: str) -> str:
        """Append a chunk and return the safe, transformed prefix to emit."""
        if not self._enabled:
            return text
        if text:
            self._buffer += text
        return self._drain(final=False)

    def flush(self) -> str:
        """Transform and return the held tail at normal end of stream."""
        if not self._enabled:
            return ""
        return self._drain(final=True)

    def discard(self) -> None:
        """Drop the held tail without emitting it (error / disconnect path)."""
        self._buffer = ""

    @property
    def has_pii(self) -> bool:
        """True when the inbound question carried at least one identifier."""
        return bool(self._pre_generation)

    @property
    def pending(self) -> str:
        """The held tail (test/introspection aid; never the vault mapping)."""
        return self._buffer

    # -- internals --------------------------------------------------------
    def _drain(self, final: bool) -> str:
        buffer = self._buffer
        if not buffer:
            return ""
        if final:
            safe_end = len(buffer)
        else:
            safe_end = self._safe_end(buffer)
            # A match the whole buffer already sees but that crosses the safe
            # edge must be held back entirely; emitting its start would be the
            # leak this module exists to prevent.
            for match in find_all(buffer):
                if match.end > safe_end:
                    safe_end = min(safe_end, match.start)
                    break
        segment = buffer[:safe_end]
        self._buffer = buffer[safe_end:]
        return self._transform(segment)

    def _safe_end(self, buffer: str) -> int:
        """Largest prefix length that cannot be extended into a match.

        Fixed hold-back first, then retain any trailing open candidate run so an
        unbounded recognizer (UPI, Devanagari run) is never split.
        """
        end = max(0, len(buffer) - self._holdback)
        run_start = len(buffer)
        while run_start > 0 and buffer[run_start - 1] in _CANDIDATE_CHARS:
            run_start -= 1
        if run_start < len(buffer):
            end = min(end, run_start)
        return end

    def _transform(self, text: str) -> str:
        if not text:
            return text
        restored = self._restore_pre_generation(text)
        redacted, _ = self._vault.tokenize(restored)
        return self._restore_pre_generation(redacted)

    def _restore_pre_generation(self, text: str) -> str:
        if not text or not self._pre_generation:
            return text
        return PLACEHOLDER_RE.sub(
            lambda match: (
                self._vault.restore(match.group(0))
                if match.group(0) in self._pre_generation
                else match.group(0)
            ),
            text,
        )
