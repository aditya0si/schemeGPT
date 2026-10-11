"""SchemeGPT's own binding of the spine's seams.

The single place that names concrete seam implementations. It is deliberately
explicit -- one module-level :data:`spine` built from the production callables,
no discovery and no registration -- so the next client writes its own binding
next to its own modules instead of reaching into SchemeGPT's.

``/query`` and ``/query/stream`` are routed through :data:`spine`; the answer
seam it binds is the existing :func:`app.rag.answer`, so the kill switch,
provider breaker and every degradation tier behave exactly as before.
"""

from __future__ import annotations

from app.core.seams import Spine
from app.guardrails.middleware import answer_with_pii_protection
from app.ops import ops
from app.quotes import validate_quotes
from app.rag import answer, get_llm
from app.stream import stream_answer


def build_scheme_spine() -> Spine:
    """Bind each seam to the SchemeGPT module that implements it."""
    return Spine(
        gate=ops.gate,
        router=get_llm,
        answerer=answer,
        validator=validate_quotes,
        egress=answer_with_pii_protection,
        stream=stream_answer,
    )


spine = build_scheme_spine()
