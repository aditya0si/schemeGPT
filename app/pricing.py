"""Per-model LLM list prices and pure USD cost arithmetic.

This is the objective function's price table: the router and the evaluation
gate need to reason about spend, so the numbers must be exact, honest, and
free of side effects. Nothing here touches the network at import or call time;
the table is a static, verified constant.

Prices (USD per 1,000,000 tokens), verified 2026-10-05 for Groq's
OpenAI-compatible API:

    openai/gpt-oss-120b   input $0.15   output $0.60
    openai/gpt-oss-20b    input $0.075  output $0.30

Provenance: three independent sources agree on these list prices (a table read
off Groq's own pricing page, checked 25 Sep 2026; a Groq pricing table dated
April 2026; and a per-model provider table listing Groq at $0.150 / $0.600).
The ``source`` field on each :class:`ModelPrice` records that provenance.

Honest caveats (deliberately NOT modelled here, so the ledger over-reports
real spend rather than guessing it down):

* Groq offers a 50% discount on prompt-cached input tokens. Cached calls are
  charged at the full input rate here, so a cache-heavy workload will look
  more expensive than the invoice.
* Groq offers a batch-API discount. Batched calls are charged at list here.
* All amounts are USD. No INR (or any other) conversion rate is invented.

Unknown models are never assigned a price. ``cost_for`` returns ``None`` and
:func:`unpriced_models` records the gap, because a silent ``0.0`` would
understate spend and hide the missing entry.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

_SOURCE = (
    "Groq published list price; verified 2026-10-05 against three independent "
    "sources that agree (Groq pricing page checked 2026-09-25; Groq pricing "
    "table dated 2026-04; per-model provider table $0.150/$0.600)"
)


@dataclass(frozen=True)
class ModelPrice:
    """A model's list price in USD per 1,000,000 tokens."""

    input_per_1m: float
    output_per_1m: float
    source: str


# Keys are exactly the model strings the application passes to
# ``observe_tokens`` (app/config.py defaults, not guessed).
PRICES: dict[str, ModelPrice] = {
    "openai/gpt-oss-120b": ModelPrice(
        input_per_1m=0.15, output_per_1m=0.60, source=_SOURCE
    ),
    "openai/gpt-oss-20b": ModelPrice(
        input_per_1m=0.075, output_per_1m=0.30, source=_SOURCE
    ),
}

_lock = threading.Lock()
_unpriced: set[str] = set()


def cost_for(
    model: str, prompt_tokens: int, completion_tokens: int
) -> float | None:
    """Return the exact USD cost for ``model``, or ``None`` if unpriced.

    A known model with zero tokens returns ``0.0`` (a real, chargeable model
    with no usage costs nothing). An unknown model returns ``None`` and is
    recorded in :func:`unpriced_models` -- never ``0.0``, which would hide the
    gap.
    """
    price = PRICES.get(model)
    if price is None:
        with _lock:
            _unpriced.add(model)
        return None
    return (
        prompt_tokens / 1_000_000 * price.input_per_1m
        + completion_tokens / 1_000_000 * price.output_per_1m
    )


def unpriced_models() -> set[str]:
    """A copy of the model names seen with no price entry (safe to mutate)."""
    with _lock:
        return set(_unpriced)
