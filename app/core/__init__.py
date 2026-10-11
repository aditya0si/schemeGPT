"""The SchemeGPT spine: seam contracts and this instance's binding.

:mod:`app.core.seams` holds the contracts (what each seam guarantees and what it
refuses). :mod:`app.core.scheme` holds SchemeGPT's own binding of those
contracts to its production modules. A second client supplies its own binding
next to its own modules instead of importing ``app.core.scheme``.
"""

from app.core.seams import (
    Answerer,
    Egress,
    ModelRouter,
    PolicyGate,
    Spine,
    StreamEgress,
    Validator,
)

__all__ = [
    "Answerer",
    "Egress",
    "ModelRouter",
    "PolicyGate",
    "Spine",
    "StreamEgress",
    "Validator",
]
