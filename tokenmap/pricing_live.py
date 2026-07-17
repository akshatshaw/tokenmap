"""Live model pricing fetched from LiteLLM's public pricing catalog.

Anthropic and OpenAI publish no machine-readable pricing API, so the de facto
community source is LiteLLM's maintained catalog on GitHub. The fetch is a
single GET of a public static JSON file — no user data is sent anywhere.

Results are cached on disk (24h TTL) so at most one network request is made
per day. Any failure (offline, timeout, bad payload) falls back silently to
the stale cache if present, else to the hardcoded table in tokenmap.pricing.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from tokenmap.lib.debug import debug
from tokenmap.pricing import ModelPricing

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
CACHE_TTL_SECONDS = 24 * 60 * 60
FETCH_TIMEOUT_SECONDS = 10

# Providers whose entries map onto tokenmap's pricing keys.
_PROVIDERS = {"anthropic", "openai"}

_memo: dict[str, ModelPricing] | None = None


def _cache_path() -> Path:
    base = os.environ.get("TOKENMAP_CACHE_DIR")
    if base:
        return Path(base) / "pricing.json"
    return Path.home() / ".cache" / "tokenmap" / "pricing.json"


def _read_cache(path: Path, max_age: float | None) -> dict | None:
    try:
        if max_age is not None and time.time() - path.stat().st_mtime > max_age:
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_cache(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError as e:
        debug(f"pricing cache write failed: {e}")


def _fetch() -> dict | None:
    try:
        import httpx
    except ImportError:
        return None
    try:
        resp = httpx.get(
            LITELLM_PRICING_URL,
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as e:
        debug(f"live pricing fetch failed: {e}")
        return None


def _parse(raw: dict) -> dict[str, ModelPricing]:
    """Convert LiteLLM per-token costs into per-million ModelPricing entries."""
    table: dict[str, ModelPricing] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("litellm_provider") not in _PROVIDERS:
            continue
        inp = entry.get("input_cost_per_token")
        out = entry.get("output_cost_per_token")
        if not isinstance(inp, (int, float)) or not isinstance(out, (int, float)):
            continue
        cache_read = entry.get("cache_read_input_token_cost") or 0.0
        cache_write = entry.get("cache_creation_input_token_cost") or 0.0
        if not isinstance(cache_read, (int, float)):
            cache_read = 0.0
        if not isinstance(cache_write, (int, float)):
            cache_write = 0.0

        # LiteLLM keys may be provider-prefixed ("anthropic/claude-..."):
        # normalize to the bare model name tokenmap adapters report.
        key = name.rsplit("/", 1)[-1]
        pricing = ModelPricing(
            input_per_m=inp * 1_000_000,
            output_per_m=out * 1_000_000,
            cache_read_per_m=cache_read * 1_000_000,
            cache_write_per_m=cache_write * 1_000_000,
        )
        # Bare keys win over prefixed duplicates so first-seen bare stays.
        if key not in table or key == name:
            table[key] = pricing
    return table


def load_live_pricing(force_refresh: bool = False) -> dict[str, ModelPricing]:
    """Return the live pricing table, fetching/caching as needed.

    Never raises: returns {} when no data is available.
    """
    global _memo
    if _memo is not None and not force_refresh:
        return _memo

    cache = _cache_path()
    raw = None if force_refresh else _read_cache(cache, max_age=CACHE_TTL_SECONDS)
    if raw is None:
        raw = _fetch()
        if raw is not None:
            _write_cache(cache, raw)
        else:
            # Offline: a stale cache beats no data.
            raw = _read_cache(cache, max_age=None)

    _memo = _parse(raw) if raw else {}
    debug(f"live pricing loaded: {len(_memo)} models")
    return _memo
