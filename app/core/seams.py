"""The seams of the SchemeGPT spine.

Five boundaries carry a request from intake to a citizen-visible answer:

1. **ingress** -- :class:`PolicyGate`: may provider work run at all?
2. **route**   -- :class:`ModelRouter`: which provider client serves the role?
3. **answer**  -- :class:`Answerer`: retrieve and generate one response.
4. **validate**-- :class:`Validator`: prove quoted text against its source.
5. **egress**  -- :class:`Egress` / :class:`StreamEgress`: protect identifiers
   on the way out, synchronously and over SSE.

Every seam is a ``typing.Protocol``: an implementation is anything structurally
shaped like it. There is no base class to inherit, no registry to populate, and
no container to resolve -- :class:`Spine` is a plain bundle a caller constructs
explicitly. This is a contract, not a framework.

Each docstring states the guarantee *and* what the seam deliberately does not
do, because a seam's value is the responsibility it refuses as much as the one
it takes. A protocol is checked structurally (``isinstance`` works because the
protocols are ``runtime_checkable``); the reference implementations are named in
:mod:`app.core.scheme`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.schemas import ProfileData

# The three values :class:`PolicyGate` may return. Rejections are not errors:
# both route the request to a retrieval-only or pre-made answer so the caller
# still returns HTTP 200.
GATE_OK = "ok"
GATE_KILL_SWITCH = "kill_switch"
GATE_BREAKER = "breaker"


@runtime_checkable
class PolicyGate(Protocol):
    """Ingress policy: may provider generation run for this request?

    Returns ``"ok"``, ``"kill_switch"`` or ``"breaker"``. The guarantee is that
    provider generation is attempted only on ``"ok"``; either refusal must send
    the request to a retrieval-only or labelled demo answer.

    It does NOT authenticate an operator, rate-limit, detect PII, retrieve
    documents, or touch HTTP. It is the operator/health switch, not an ACL.
    """

    def __call__(self) -> str: ...


@runtime_checkable
class ModelRouter(Protocol):
    """Route: return a provider client for a task role.

    ``role`` is ``"answer"``/``"agent"`` (the strong model) or ``"fast"`` (the
    cheap model used for normalization and routing); ``max_tokens`` bounds the
    generation. The returned object is a chat model already bound to the
    effective endpoint override and the configured timeout/retry bounds.

    It does NOT choose the degradation tier, retrieve, call the provider, or
    cache anything. Construction is cheap and fails fast when no credential is
    configured rather than deferring the failure to the first token.
    """

    def __call__(self, role: str = "answer", max_tokens: int = 1024) -> Any: ...


@runtime_checkable
class Answerer(Protocol):
    """Answer: retrieve, generate, and assemble exactly one response payload.

    Returns a dict carrying at least ``answer`` (str), ``sources`` (list of
    source dicts) and ``mode`` in ``{"live", "degraded", "demo"}``. The
    guarantee is that every input yields a valid, non-leaking payload: a
    provider or database failure degrades to a retrieval-only or pre-made
    answer instead of raising. Optional keys a caller may see include
    ``quotes``, ``steps``, ``notice``, ``language``, ``cached``,
    ``provider_error_type`` and ``provider_status_code``.

    It does NOT redact PII, stream, or shape an HTTP response -- that is the
    egress seam -- and it does not promise that every returned quote is
    verified; :class:`Validator` is the seam that proves that.
    """

    def __call__(
        self,
        question: str,
        language: str = "en",
        profile: ProfileData | None = None,
        *,
        skip_cache: bool = False,
    ) -> dict: ...


@runtime_checkable
class Validator(Protocol):
    """Validate: extract quote lines and verify them against their sources.

    Takes an answer's raw text and the retrieved source dicts and returns the
    verified-quote records (``VerifiedQuote``-shaped: ``text``, ``source``,
    ``status``, ``verified``, ``matched_source``). The guarantee is that a
    quote is marked verified only when its text is an exact normalised
    substring of the *specifically named* source and the declared status
    agrees; there is no fallback to a different source, which is what stops a
    hallucinated attribution from being labelled verified.

    It does NOT retrieve, generate, redact, or decide answer mode. It is a pure
    function, so the same seam scores archived answers offline.
    """

    def __call__(self, answer_text: str, sources: list[dict]) -> list: ...


@runtime_checkable
class Egress(Protocol):
    """Egress (synchronous): answer a request with identifiers protected.

    Detects identifiers in the question, runs the answer seam on the redacted
    text (bypassing the cache when PII was present), then restores the caller's
    own values in the response. The guarantee is that no detected identifier
    reaches a hosted provider and a restored value is never written anywhere it
    could be served to a different request.

    It does NOT stream, change the answer mode, or expose the vault mapping.
    """

    def __call__(
        self,
        question: str,
        language: str = "en",
        profile: ProfileData | None = None,
    ) -> dict: ...


@runtime_checkable
class StreamEgress(Protocol):
    """Egress (streaming): the same protection over an SSE token stream.

    Returns an async iterator of SSE-formatted ``str`` blocks
    (``sources`` -> ``token``* -> ``quotes``/``done``, terminal ``done`` or
    ``error``). Every outbound token passes through a bounded overlap buffer
    that restores pre-generation placeholders and redacts identifiers, so a
    value split across two chunks cannot leak.

    It does NOT buffer the whole answer, alter the event protocol, or emit a
    held tail after a mid-stream error or a client disconnect.
    """

    def __call__(
        self,
        question: str,
        language: str = "en",
        profile: ProfileData | None = None,
    ) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class Spine:
    """One implementation of each seam; the attach point for a client.

    A client constructs a ``Spine`` explicitly from its own callables and
    routes requests through :attr:`egress` / :attr:`stream`. There is no
    registry and no discovery: swapping a backend is rebinding a field, and a
    second client lives next to its own modules rather than importing
    SchemeGPT's binding.
    """

    gate: PolicyGate
    router: ModelRouter
    answerer: Answerer
    validator: Validator
    egress: Egress
    stream: StreamEgress
