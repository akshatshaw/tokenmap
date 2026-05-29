"""Aggregator — loads data from adapters and returns ToolPanels."""

from __future__ import annotations

from typing import Optional

from tokenmap.adapters import claude, codex, opencode, cursor
from tokenmap.lib.debug import debug
from tokenmap.stats import compute_stats
from tokenmap.types import (
    AdapterResult, AggregatedData, DateRange, DayData, ToolCapabilities, ToolPanel,
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


def filter_panel_by_model(panel: ToolPanel, model: str) -> Optional[ToolPanel]:
    """Return a copy of ``panel`` restricted to models matching ``model``.

    Matching is case-insensitive substring (so ``--model opus`` keeps every Opus
    variant, ``--model claude-opus-4-7`` keeps just that one). Per-day
    input/output/cache_read totals are scaled to the matched models' share of
    each day's tokens, since the raw split isn't stored per model. Stats are
    recomputed from the filtered data. Returns ``None`` if nothing matches.
    """
    needle = model.lower()

    def matches(name: str) -> bool:
        return needle in name.lower()

    new_days: list[DayData] = []
    for day in panel.data.days:
        kept = {m: t for m, t in day.models.items() if matches(m)}
        if not kept:
            continue
        day_total = sum(day.models.values())
        ratio = (sum(kept.values()) / day_total) if day_total else 0.0
        new_days.append(DayData(
            date=day.date,
            input_tokens=round(day.input_tokens * ratio),
            output_tokens=round(day.output_tokens * ratio),
            cache_read_tokens=round(day.cache_read_tokens * ratio),
            sessions=day.sessions, messages=day.messages,
            tool_calls=day.tool_calls, models=kept,
        ))

    if not new_days:
        return None

    new_data = AggregatedData(
        days=new_days,
        sources=list(panel.data.sources),
        hour_counts=dict(panel.data.hour_counts),
        total_sessions=panel.data.total_sessions,
        total_messages=panel.data.total_messages,
        first_session_date=min(d.date for d in new_days),
        model_usage={m: t for m, t in panel.data.model_usage.items() if matches(m)},
        detailed_model_usage={
            m: t for m, t in panel.data.detailed_model_usage.items() if matches(m)
        },
        avg_session_seconds=panel.data.avg_session_seconds,
    )
    return ToolPanel(
        tool=panel.tool, data=new_data,
        stats=compute_stats(new_data), capabilities=panel.capabilities,
    )


def aggregate_multi(
    tools: Optional[list[str]] = None,
    year: Optional[int] = None,
    date_range: Optional[DateRange] = None,
) -> list[ToolPanel]:
    """Load data from each selected tool, returning a ToolPanel per tool.

    ``date_range`` takes precedence over ``year`` (which is kept as sugar for a
    full-year window). An unbounded range is passed to adapters as ``None`` so
    the unfiltered fast paths are preserved.
    """
    if date_range is None:
        date_range = DateRange.from_year(year)
    effective_range = None if date_range.is_unbounded else date_range

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
            result = adapter.load(effective_range)  # type: ignore[attr-defined]
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
