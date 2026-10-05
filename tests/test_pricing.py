"""Unit tests for the per-model price table and cost arithmetic.

Cost is money: these tests pin exact values, and pin the deliberate
``None``-for-unknown contract (never a silent ``0.0``).
"""

import pytest

from app import pricing


@pytest.fixture(autouse=True)
def _reset_unpriced():
    with pricing._lock:
        pricing._unpriced.clear()
    yield


def test_known_model_exact_arithmetic():
    # openai/gpt-oss-120b: $0.15 in / $0.60 out per 1M tokens.
    assert pricing.cost_for("openai/gpt-oss-120b", 1_000_000, 1_000_000) == pytest.approx(
        0.75
    )
    assert pricing.cost_for("openai/gpt-oss-120b", 2_000_000, 0) == pytest.approx(0.30)
    assert pricing.cost_for("openai/gpt-oss-120b", 0, 2_000_000) == pytest.approx(1.20)


def test_fast_model_exact_arithmetic():
    # openai/gpt-oss-20b: $0.075 in / $0.30 out per 1M tokens.
    assert pricing.cost_for("openai/gpt-oss-20b", 1_000_000, 1_000_000) == pytest.approx(
        0.375
    )
    assert pricing.cost_for("openai/gpt-oss-20b", 4_000_000, 0) == pytest.approx(0.30)


def test_fractional_tokens_scale_linearly():
    assert pricing.cost_for("openai/gpt-oss-120b", 1000, 500) == pytest.approx(
        1000 / 1_000_000 * 0.15 + 500 / 1_000_000 * 0.60
    )


def test_unknown_model_returns_none_and_is_recorded():
    assert pricing.cost_for("acme/unknown-model", 100, 100) is None
    assert "acme/unknown-model" in pricing.unpriced_models()


def test_zero_tokens_on_known_model_is_zero_not_none():
    result = pricing.cost_for("openai/gpt-oss-120b", 0, 0)
    assert result is not None
    assert result == 0.0


def test_prices_cover_the_configured_models():
    from app.config import settings

    assert settings.groq_model in pricing.PRICES
    assert settings.groq_fast_model in pricing.PRICES


def test_every_price_entry_has_a_non_empty_source():
    for model, price in pricing.PRICES.items():
        assert isinstance(price.source, str), model
        assert price.source.strip(), model


def test_no_price_is_negative():
    for price in pricing.PRICES.values():
        assert price.input_per_1m >= 0
        assert price.output_per_1m >= 0


def test_unpriced_models_is_a_read_only_view():
    pricing.cost_for("acme/other", 1, 1)
    view = pricing.unpriced_models()
    view.add("mutation/attempt")
    assert "mutation/attempt" not in pricing.unpriced_models()
