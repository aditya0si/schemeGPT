"""PII protection for the non-streaming answer path (Phase 6b).

This is the integration seam between the pure recognizers/vault and the
synchronous ``POST /query`` path. It is deliberately thin:

1. Detect identifiers in the inbound question and replace each with a
   request-scoped placeholder (:mod:`app.guardrails.vault`) *before* retrieval
   or generation, so the raw identifier never leaves the process to a hosted
   provider.
2. Run the normal answer pipeline with the redacted question. Every tier is
   untouched: the semantic cache, the retrieval-only degraded answer, the
   kill switch, and the provider circuit breaker all still behave exactly as
   before.
3. Restore the placeholders in the answer the citizen receives.

Cache decision (stated, not clever)
-----------------------------------
A request that carried PII **bypasses the semantic cache entirely** -- both the
lookup and the store -- via ``rag.answer(..., skip_cache=True)``. The alternative
(caching the redacted form and restoring per request) was rejected: it stores a
generated answer keyed by a redacted embedding and would have to guarantee that
the *same* placeholder nonce is restored by the *right* request, which is
exactly the cross-request footgun this phase exists to remove. Bypassing is the
obviously-correct choice: an answer containing a restored identifier is never
written anywhere it could be served to a different person. The cost is a cache
miss for PII-bearing questions, which is the right trade.

Scope
-----
Non-streaming only. The streaming path (``app/stream.py``) is Phase 6c and is
not touched here. Only the question is redacted; profile free-text fields are
not (see the evidence document's limitations).

The vault mapping is a local variable on this call's stack. It is never
returned, never logged, never persisted, and never placed in a response field.
"""

from __future__ import annotations

import logging
from typing import Any

from app import rag
from app.config import settings
from app.guardrails.vault import Vault
from app.schemas import ProfileData

logger = logging.getLogger(__name__)


def _restore_value(value: Any, vault: Vault) -> Any:
    """Recursively restore this request's placeholders in a result value.

    Only this vault's complete placeholders are substituted; everything else is
    returned unchanged. Used for the answer and any string-bearing field that
    could echo the (redacted) question.
    """
    if isinstance(value, str):
        return vault.restore(value)
    if isinstance(value, dict):
        return {key: _restore_value(item, vault) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_value(item, vault) for item in value]
    if isinstance(value, tuple):
        return tuple(_restore_value(item, vault) for item in value)
    return value


def answer_with_pii_protection(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
    as_of=None,
) -> dict:
    """Answer ``question`` with detected identifiers redacted on egress.

    With ``settings.enable_pii_vault`` false, this is a passthrough to
    :func:`app.rag.answer` (documented escape hatch). With it true and no PII
    detected, the call is also unchanged, so clean questions keep using the
    semantic cache.

    An ``as_of`` request is resolved deterministically from the committed
    claims artifact and never reaches a provider, so it needs no redaction; it
    is answered directly.
    """
    if as_of is not None:
        return rag.answer(question, language, profile, as_of=as_of)
    if not getattr(settings, "enable_pii_vault", True):
        return rag.answer(question, language, profile)

    vault = Vault()
    redacted_question, _ = vault.tokenize(question)
    if not vault.has_matches:
        # Nothing to protect: identical behaviour, cache included.
        return rag.answer(question, language, profile)

    result = rag.answer(redacted_question, language, profile, skip_cache=True)
    return _restore_value(result, vault)
