"""Aggregator — loads data from adapters and returns ToolPanels."""

from __future__ import annotations

from typing import Optional

from tokenmap.adapters import claude, codex, opencode, cursor
from tokenmap.lib.debug import debug
from tokenmap.stats import compute_stats
from tokenmap.types import (
    AdapterResult, AggregatedData, DayData, ToolCapabilities, ToolPanel,
)

_ADAPTERS: dict[str, object] = {
    "claude": claude,
    "codex": codex,
    "opencode": opencode,
    "cursor": cursor,
}

_CAPABILITIES: dict[str, ToolCapabilities] = {
    "claude": ToolCapabilities(has_avg_session=False, has_peak_hour=True),
    "codex": ToolCapabilities(has_avg_session=True, has_peak_hour=True),
    "opencode": ToolCapabilities(has_avg_session=True, has_peak_hour=True),
    "cursor": ToolCapabilities(has_avg_session=False, has_peak_hour=True),
}


def _resolve_model_tokens(value: object) -> int:
    """Resolve a model usage value to a plain token number."""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        return int(value.get("inputTokens", 0) or 0) + int(value.get("outputTokens", 0) or 0)
    return 0


def _to_aggregated_data(name: str, result: AdapterResult) -> AggregatedData:
    """Convert a single adapter result to AggregatedData."""
    days: list[DayData] = []
    for day in result.days:
        models: dict[str, int] = {}
        if day.models:
            for model, value in day.models.items():
                models[model] = _resolve_model_tokens(value)
        days.append(DayData(
            date=day.date, input_tokens=day.input_tokens,
            output_tokens=day.output_tokens, cache_read_tokens=day.cache_read_tokens,
            sessions=day.sessions, messages=day.messages,
            tool_calls=day.tool_calls, models=models,
        ))
    days.sort(key=lambda d: d.date)

    model_usage: dict[str, int] = {}
    if result.model_usage:
        for model, value in result.model_usage.items():
            model_usage[model] = _resolve_model_tokens(value)

    return AggregatedData(
        days=days, sources=[name],
        hour_counts=result.hour_counts or {},
        total_sessions=result.total_sessions or 0,
        total_messages=result.total_messages or 0,
        first_session_date=result.first_session_date,
        model_usage=model_usage,
        detailed_model_usage=result.detailed_model_usage or {},
        avg_session_seconds=result.avg_session_seconds or 0,
    )


def aggregate_multi(
    tools: Optional[list[str]] = None,
    year: Optional[int] = None,
) -> list[ToolPanel]:
    """Load data from each selected tool, returning a ToolPanel per tool."""
    if tools:
        for t in tools:
            if t not in _ADAPTERS:
                raise ValueError(f"Unknown tool: {t}. Valid: {', '.join(_ADAPTERS)}")
        adapter_names = list(tools)
    else:
        adapter_names = []
        for name, adapter in _ADAPTERS.items():
            found = adapter.detect()  # type: ignore[attr-defined]
            debug(f"{name}: detect() = {found}")
            if found:
                adapter_names.append(name)

    debug(f"Adapters to load: {', '.join(adapter_names) or '(none)'}")
    explicit = bool(tools)

    panels: list[ToolPanel] = []
    for name in adapter_names:
        adapter = _ADAPTERS[name]
        try:
            debug(f"{name}: loading...")
            result = adapter.load(year)  # type: ignore[attr-defined]
            if not result:
                debug(f"{name}: load() returned None")
                continue
            data = _to_aggregated_data(name, result)
            stats = compute_stats(data)
            debug(f"{name}: {len(result.days)} days, {stats.total_tokens} tokens")
            if not explicit and stats.total_tokens == 0:
                continue
            capabilities = _CAPABILITIES.get(name, ToolCapabilities())
            panels.append(ToolPanel(tool=name, data=data, stats=stats, capabilities=capabilities))
        except Exception as err:
            msg = str(err)
            debug(f"{name}: load() threw: {msg}")
            if explicit:
                import sys
                print(f"Error loading {name} data: {msg}", file=sys.stderr)

    return panels
