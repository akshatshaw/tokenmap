"""Tests for tokenmap.pricing_live and its integration with get_pricing."""

import json
import os
import time

import pytest

import tokenmap.pricing as pricing
import tokenmap.pricing_live as pricing_live
from tokenmap.pricing import get_pricing, set_live_pricing

SAMPLE_CATALOG = {
    "sample_spec": {"description": "not a model"},
    "claude-fable-5": {
        "litellm_provider": "anthropic",
        "input_cost_per_token": 0.00001,
        "output_cost_per_token": 0.00005,
        "cache_read_input_token_cost": 0.000001,
        "cache_creation_input_token_cost": 0.0000125,
    },
    "anthropic/claude-sonnet-5": {
        "litellm_provider": "anthropic",
        "input_cost_per_token": 0.000003,
        "output_cost_per_token": 0.000015,
    },
    "gpt-5": {
        "litellm_provider": "openai",
        "input_cost_per_token": 0.00000125,
        "output_cost_per_token": 0.00001,
    },
    "gemini-something": {
        "litellm_provider": "vertex_ai",
        "input_cost_per_token": 0.000001,
        "output_cost_per_token": 0.000002,
    },
}


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    """Isolate cache dir and reset module-level memoization around each test."""
    monkeypatch.setenv("TOKENMAP_CACHE_DIR", str(tmp_path))
    pricing_live._memo = None
    set_live_pricing(False)
    yield
    pricing_live._memo = None
    set_live_pricing(False)


class TestParse:
    def test_converts_per_token_to_per_million(self):
        table = pricing_live._parse(SAMPLE_CATALOG)
        p = table["claude-fable-5"]
        assert p.input_per_m == pytest.approx(10)
        assert p.output_per_m == pytest.approx(50)
        assert p.cache_read_per_m == pytest.approx(1.0)
        assert p.cache_write_per_m == pytest.approx(12.5)

    def test_strips_provider_prefix(self):
        table = pricing_live._parse(SAMPLE_CATALOG)
        assert "claude-sonnet-5" in table
        assert "anthropic/claude-sonnet-5" not in table

    def test_missing_cache_costs_default_to_zero(self):
        table = pricing_live._parse(SAMPLE_CATALOG)
        assert table["claude-sonnet-5"].cache_read_per_m == 0.0

    def test_filters_non_target_providers_and_non_models(self):
        table = pricing_live._parse(SAMPLE_CATALOG)
        assert "gemini-something" not in table
        assert "sample_spec" not in table
        assert "gpt-5" in table


class TestLoadLivePricing:
    def test_fetch_writes_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pricing_live, "_fetch", lambda: SAMPLE_CATALOG)
        table = pricing_live.load_live_pricing()
        assert "claude-fable-5" in table
        assert (tmp_path / "pricing.json").is_file()

    def test_fresh_cache_skips_fetch(self, tmp_path, monkeypatch):
        (tmp_path / "pricing.json").write_text(json.dumps(SAMPLE_CATALOG))

        def boom():
            raise AssertionError("fetch should not be called with fresh cache")

        monkeypatch.setattr(pricing_live, "_fetch", boom)
        table = pricing_live.load_live_pricing()
        assert "claude-fable-5" in table

    def test_expired_cache_refetches(self, tmp_path, monkeypatch):
        cache = tmp_path / "pricing.json"
        cache.write_text(json.dumps({"stale": {}}))
        old = time.time() - pricing_live.CACHE_TTL_SECONDS - 60
        os.utime(cache, (old, old))
        monkeypatch.setattr(pricing_live, "_fetch", lambda: SAMPLE_CATALOG)
        table = pricing_live.load_live_pricing()
        assert "claude-fable-5" in table

    def test_offline_falls_back_to_stale_cache(self, tmp_path, monkeypatch):
        cache = tmp_path / "pricing.json"
        cache.write_text(json.dumps(SAMPLE_CATALOG))
        old = time.time() - pricing_live.CACHE_TTL_SECONDS - 60
        os.utime(cache, (old, old))
        monkeypatch.setattr(pricing_live, "_fetch", lambda: None)
        table = pricing_live.load_live_pricing()
        assert "claude-fable-5" in table

    def test_offline_no_cache_returns_empty(self, monkeypatch):
        monkeypatch.setattr(pricing_live, "_fetch", lambda: None)
        assert pricing_live.load_live_pricing() == {}


class TestGetPricingIntegration:
    def test_disabled_by_default_uses_hardcoded(self, monkeypatch):
        def boom():
            raise AssertionError("live pricing must not load when disabled")

        monkeypatch.setattr(pricing_live, "load_live_pricing", boom)
        p = get_pricing("claude-opus-4-8")
        assert p.input_per_m == 5

    def test_live_values_override_hardcoded(self, monkeypatch):
        live = {"claude-opus-4-8": pricing.ModelPricing(6, 30, 0.6, 7.5)}
        monkeypatch.setattr(pricing_live, "load_live_pricing", lambda: live)
        set_live_pricing(True)
        assert get_pricing("claude-opus-4-8").input_per_m == 6
        # And back off again restores the hardcoded table.
        set_live_pricing(False)
        assert get_pricing("claude-opus-4-8").input_per_m == 5

    def test_live_adds_unknown_models(self, monkeypatch):
        live = {"brand-new-model": pricing.ModelPricing(7, 21, 0, 0)}
        monkeypatch.setattr(pricing_live, "load_live_pricing", lambda: live)
        set_live_pricing(True)
        assert get_pricing("brand-new-model").input_per_m == 7

    def test_live_failure_falls_back_to_hardcoded(self, monkeypatch):
        def boom():
            raise RuntimeError("network down")

        monkeypatch.setattr(pricing_live, "load_live_pricing", boom)
        set_live_pricing(True)
        assert get_pricing("claude-opus-4-8").input_per_m == 5
