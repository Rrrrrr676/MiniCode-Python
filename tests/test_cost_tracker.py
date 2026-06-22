from __future__ import annotations

import pytest

from minicode.providers.cost import calculate_cost


def test_calculate_cost_returns_float_for_known_model() -> None:
    cost = calculate_cost(
        "gpt-4o",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
    )

    assert isinstance(cost, float)
    assert cost == pytest.approx(16.25)


def test_calculate_cost_handles_unknown_custom_model() -> None:
    cost = calculate_cost(
        "deepseek-v4-flash",
        input_tokens=123,
        output_tokens=45,
    )

    assert isinstance(cost, float)
    assert cost == pytest.approx(0.001044)
