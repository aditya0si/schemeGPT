"""Reversible, request-scoped tokenisation of detected PII (Phase 6b).

The recognizers in :mod:`app.guardrails.recognizers` find identifiers; this
module *replaces* them so the redacted text can safely leave the box to a
hosted model, then puts the originals back in the answer the citizen sees.

Lifecycle (the one that matters)
--------------------------------
Construct exactly one :class:`Vault` per request, use it for that request only,
and drop it when the request ends::

    vault = Vault()
    redacted_question, _ = vault.tokenize(question)
    answer = generate(redacted_question)        # provider never sees the PII
    answer = vault.restore(answer)              # citizen sees the real values

Guarantees this module holds to:

* **Fresh mapping per request.** A new ``Vault`` starts empty. The same value
  maps to the same placeholder *within* one vault (deterministic), and the
  placeholder carries a per-vault random nonce, so the same value maps to a
  *different* placeholder, and therefore to nothing reusable, in any other
  request.
* **Never persisted, logged, cached, or returned.** The mapping is in-memory
  only. ``repr``/``str`` are redacted so an accidental log of the object, or a
  diagnostic that formats it, cannot spill the originals. Callers must never put
  the mapping (or the ``Vault``) into a response field or an exception message.
* **Original spans only.** A placeholder stands in for the exact character slice
  the recognizer matched -- including the user's own casing -- so redaction and
  restoration are exact.
* **Safe, single-pass restore.** Restoring text that contains no placeholders is
  a no-op; a placeholder that is only partially present (a truncated token the
  model mangled) is left untouched because only complete, well-formed
  placeholders are ever substituted.
"""

from __future__ import annotations

import re
import secrets

from app.guardrails.recognizers import find_all

# The per-vault nonce is 8 hex characters, so two requests that tokenise the
# same identifier never produce the same placeholder string.
_NONCE_BYTES = 4
_PLACEHOLDER_TEMPLATE = "[[PII:{nonce}:{kind}:{index}]]"
_PLACEHOLDER_RE = re.compile(r"\[\[PII:[0-9a-f]{8}:[A-Z_]+:\d+\]\]")

# Public handle for the complete-placeholder grammar. The streaming redactor
# (``app.guardrails.stream``) uses it to take a snapshot of the placeholders a
# question produced *before* generation, so it can restore exactly those and
# leave placeholders minted later for streamed identifiers redacted.
PLACEHOLDER_RE = _PLACEHOLDER_RE


class Vault:
    """A single request's reversible PII mapping.

    Not thread-shared: build one per request. See the module docstring for the
    lifecycle and the storage guarantees.
    """

    def __init__(self, nonce: str | None = None) -> None:
        self._nonce = nonce or secrets.token_hex(_NONCE_BYTES)
        self._value_to_placeholder: dict[str, str] = {}
        self._placeholder_to_value: dict[str, str] = {}
        self._kind_counts: dict[str, int] = {}

    # -- tokenise ---------------------------------------------------------
    def tokenize(self, text: str) -> tuple[str, "Vault"]:
        """Replace every detected PII span in ``text`` with a placeholder.

        Returns ``(redacted_text, self)``. The returned object *is* the mapping
        handle for :meth:`restore`; keep it on the stack for the request and
        never persist or return it. Text with no detected PII is returned
        unchanged (byte-identical).
        """
        if not text:
            return text, self
        matches = find_all(text)
        if not matches:
            return text, self

        parts: list[str] = []
        cursor = 0
        for match in matches:
            parts.append(text[cursor : match.start])
            parts.append(self._placeholder_for(match))
            cursor = match.end
        parts.append(text[cursor:])
        return "".join(parts), self

    def _placeholder_for(self, match) -> str:
        """Stable placeholder for a match's exact text within this vault."""
        existing = self._value_to_placeholder.get(match.text)
        if existing is not None:
            return existing
        kind = match.kind.upper()
        index = self._kind_counts.get(kind, 0) + 1
        self._kind_counts[kind] = index
        placeholder = _PLACEHOLDER_TEMPLATE.format(
            nonce=self._nonce, kind=kind, index=index
        )
        self._value_to_placeholder[match.text] = placeholder
        self._placeholder_to_value[placeholder] = match.text
        return placeholder

    # -- restore ----------------------------------------------------------
    def restore(self, text: str) -> str:
        """Put this vault's originals back, in a single non-overlapping pass.

        Only complete placeholders belonging to *this* vault are substituted;
        anything else in the text -- including a foreign request's placeholders
        or a truncated placeholder -- is left exactly as it was. Safe on text
        with no placeholders (returns it unchanged).
        """
        if not text or not self._placeholder_to_value:
            return text
        return _PLACEHOLDER_RE.sub(
            lambda match: self._placeholder_to_value.get(
                match.group(0), match.group(0)
            ),
            text,
        )

    # -- introspection / lifecycle ---------------------------------------
    @property
    def has_matches(self) -> bool:
        """True when this request contained at least one detected identifier."""
        return bool(self._placeholder_to_value)

    def __len__(self) -> int:
        return len(self._placeholder_to_value)

    def clear(self) -> None:
        """Drop the mapping now (also happens on context-manager exit)."""
        self._value_to_placeholder.clear()
        self._placeholder_to_value.clear()
        self._kind_counts.clear()

    def __enter__(self) -> "Vault":
        return self

    def __exit__(self, *_exc_info) -> bool:
        self.clear()
        return False

    def __repr__(self) -> str:
        # Deliberately opaque: neither the values, the placeholders, nor the
        # nonce should ever reach a log line.
        return "<Vault: mapping withheld>"

    __str__ = __repr__


def tokenize(text: str, vault: Vault | None = None) -> tuple[str, Vault]:
    """Module-level convenience: tokenise with a fresh (or given) ``Vault``."""
    vault = vault if vault is not None else Vault()
    return vault.tokenize(text)


def restore(text: str, mapping: Vault) -> str:
    """Module-level convenience: restore using a mapping returned by tokenize."""
    return mapping.restore(text)
