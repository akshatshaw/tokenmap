"""Tests for tokenviz.pricing module."""

from tokenviz.pricing import get_pricing, format_cost, compute_cost_summary, DEFAULT_PRICING
from tokenviz.types import ModelTokenDetail


class TestGetPricing:
    def test_exact_match(self):
        p = get_pricing("gpt-4o")
        assert p.input_per_m == 2.5
        assert p.output_per_m == 10

    def test_prefix_match(self):
        # "claude-opus-4-6-20260101" should match "claude-opus-4-6"
        p = get_pricing("claude-opus-4-6-20260101")
        assert p.input_per_m == 5
        assert p.output_per_m == 25

    def test_substring_match(self):
        # "anthropic/claude-3-5-sonnet" should match via substring
        p = get_pricing("anthropic/claude-3-5-sonnet-20241022")
        assert p.input_per_m == 3

    def test_unknown_model_returns_default(self):
        p = get_pricing("totally-unknown-model")
        assert p.input_per_m == DEFAULT_PRICING.input_per_m
        assert p.output_per_m == DEFAULT_PRICING.output_per_m


class TestFormatCost:
    def test_zero(self):
        assert format_cost(0) == "$0.00"

    def test_small(self):
        assert format_cost(0.05) == "$0.05"

    def test_medium(self):
        assert format_cost(5.50) == "$5.50"

    def test_large(self):
        assert format_cost(150) == "$150"

    def test_thousands(self):
        assert format_cost(2500) == "$2.5K"

    def test_very_small(self):
        assert format_cost(0.005) == "$0.005"


class TestComputeCostSummary:
    def test_empty(self):
        summary = compute_cost_summary({})
        assert summary.total_cost == 0
        assert len(summary.model_costs) == 0

    def test_single_model(self):
        detail = {"gpt-4o": ModelTokenDetail(input_tokens=1_000_000, output_tokens=500_000)}
        summary = compute_cost_summary(detail)
        assert summary.total_cost > 0
        assert len(summary.model_costs) == 1
        mc = summary.model_costs[0]
        assert mc.model == "gpt-4o"
        # input: 1M * 2.5/M = 2.5, output: 0.5M * 10/M = 5.0
        assert abs(mc.input_cost - 2.5) < 0.01
        assert abs(mc.output_cost - 5.0) < 0.01

    def test_sorted_by_cost_descending(self):
        detail = {
            "gpt-4o-mini": ModelTokenDetail(input_tokens=100_000),
            "gpt-4o": ModelTokenDetail(input_tokens=1_000_000, output_tokens=1_000_000),
        }
        summary = compute_cost_summary(detail)
        assert len(summary.model_costs) == 2
        assert summary.model_costs[0].total_cost >= summary.model_costs[1].total_cost
