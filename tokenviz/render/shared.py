"""Shared rendering utilities — grid building, display stats, constants."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from tokenviz.stats import format_tokens
from tokenviz.types import (
    AggregatedData, DisplayStats, GridCell, GridResult, Stats, ToolPanel,
)

TOOL_COLORS: dict[str, str] = {
    "claude": "#F97316",
    "codex": "#3B82F6",
    "opencode": "#10B981",
    "cursor": "#8B5CF6",
    "other": "#6B7280",
}

MONTH_NAMES: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

DAY_LABELS: list[str] = ["Mon", "", "Wed", "", "Fri", "", "Sun"]


def get_date_range(year: int | None = None) -> tuple[date, date]:
    """Get the start and end dates for the heatmap grid."""
    if year:
        start = date(year, 1, 1)
        dow = start.isoweekday()  # Mon=1..Sun=7
        monday_offset = 1 - dow
        start += timedelta(days=monday_offset)
        end = date(year, 12, 31)
        return start, end

    end = date.today()
    start = end - timedelta(days=364)
    dow = start.isoweekday()
    monday_offset = 1 - dow
    start += timedelta(days=monday_offset)
    return start, end


def build_grid(data: AggregatedData, year: int | None = None) -> GridResult:
    """Build the heatmap grid from aggregated data."""
    start, end = get_date_range(year)

    day_tokens: dict[str, int] = {}
    for day in data.days:
        total = (day.input_tokens or 0) + (day.output_tokens or 0)
        day_tokens[day.date] = total

    grid: list[list[GridCell]] = [[] for _ in range(7)]
    week_months: list[int] = []
    max_tokens = 0

    cursor = start
    current_week = 0
    last_week_tracked = -1

    while cursor <= end:
        date_str = cursor.isoformat()
        # Convert to row: Mon=0, Tue=1, ..., Sun=6
        iso_dow = cursor.isoweekday()  # Mon=1..Sun=7
        row = iso_dow - 1  # Mon=0..Sun=6

        tokens = day_tokens.get(date_str, 0)
        if tokens > max_tokens:
            max_tokens = tokens

        if row == 0 or current_week == 0:
            if last_week_tracked < current_week:
                week_months.append(cursor.month - 1)  # 0-indexed
                last_week_tracked = current_week

        grid[row].append(GridCell(date=date_str, tokens=tokens))
        cursor += timedelta(days=1)
        if row == 6:
            current_week += 1

    num_weeks = len(grid[0])
    while len(week_months) < num_weeks:
        week_months.append(week_months[-1] if week_months else 0)

    return GridResult(grid=grid, week_months=week_months, max_tokens=max_tokens, num_weeks=num_weeks)


def extract_display_stats(stats: Stats) -> DisplayStats:
    """Extract pre-formatted display stats."""
    return DisplayStats(
        input_total=format_tokens(stats.input_tokens or 0),
        output_total=format_tokens(stats.output_tokens or 0),
        grand_total=format_tokens(stats.total_tokens or 0),
        top_model=stats.most_used_model["name"] if stats.most_used_model else "N/A",
        top_model_tokens=int(stats.most_used_model["tokens"]) if stats.most_used_model else 0,
        recent_model_name=stats.recent_model["name"] if stats.recent_model else "N/A",
        recent_model_tokens=int(stats.recent_model["tokens"]) if stats.recent_model else 0,
        longest_streak=stats.longest_streak or 0,
        current_streak=stats.current_streak or 0,
        peak_hour=str(stats.peak_hour["hour"]) if stats.peak_hour else "N/A",
        busiest_day=stats.busiest_day or "N/A",
        avg_session=f"{stats.avg_session_minutes} min" if stats.avg_session_minutes else "N/A",
    )


def compute_global_totals(panels: list[ToolPanel]) -> dict[str, str]:
    """Compute global input/output/total across all panels."""
    inp = sum(p.stats.input_tokens or 0 for p in panels)
    out = sum(p.stats.output_tokens or 0 for p in panels)
    return {
        "input_total": format_tokens(inp),
        "output_total": format_tokens(out),
        "grand_total": format_tokens(inp + out),
    }
