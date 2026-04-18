"""Core data types for tokenviz."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelTokenDetail:
    """Per-model token breakdown for cost calculation."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class DayData:
    """Token usage data for a single day."""

    date: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    sessions: int = 0
    messages: int = 0
    tool_calls: int = 0
    models: dict[str, int] = field(default_factory=dict)


@dataclass
class AdapterResult:
    """Result from a single tool adapter."""

    tool: str = ""
    days: list[DayData] = field(default_factory=list)
    hour_counts: dict[str, int] = field(default_factory=dict)
    total_sessions: int = 0
    total_messages: int = 0
    first_session_date: Optional[str] = None
    model_usage: dict[str, int] = field(default_factory=dict)
    detailed_model_usage: dict[str, ModelTokenDetail] = field(default_factory=dict)
    avg_session_seconds: float = 0.0


@dataclass
class AggregatedData:
    """Aggregated data from one or more adapters."""

    days: list[DayData] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    hour_counts: dict[str, int] = field(default_factory=dict)
    total_sessions: int = 0
    total_messages: int = 0
    first_session_date: Optional[str] = None
    model_usage: dict[str, int] = field(default_factory=dict)
    detailed_model_usage: dict[str, ModelTokenDetail] = field(default_factory=dict)
    avg_session_seconds: float = 0.0


@dataclass
class Stats:
    """Computed statistics from aggregated data."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    most_used_model: Optional[dict[str, object]] = None  # {"name": str, "tokens": int}
    recent_model: Optional[dict[str, object]] = None
    current_streak: int = 0
    longest_streak: int = 0
    total_sessions: int = 0
    total_messages: int = 0
    peak_hour: Optional[dict[str, object]] = None  # {"hour": str, "count": int}
    busiest_day: Optional[str] = None
    dow_counts: list[int] = field(default_factory=lambda: [0] * 7)
    avg_session_minutes: int = 0


@dataclass
class ToolCapabilities:
    """What features a tool adapter supports."""

    has_avg_session: bool = False
    has_peak_hour: bool = False


@dataclass
class ToolPanel:
    """A complete panel for rendering a single tool."""

    tool: str = ""
    data: AggregatedData = field(default_factory=AggregatedData)
    stats: Stats = field(default_factory=Stats)
    capabilities: ToolCapabilities = field(default_factory=ToolCapabilities)


@dataclass
class Theme:
    """Color theme for rendering."""

    bg: str = "#ffffff"
    text: str = "#24292f"
    label: str = "#57606a"
    empty: str = "#ebedf0"
    scale: list[str] = field(default_factory=lambda: ["#9be9a8", "#40c463", "#30a14e", "#216e39"])


@dataclass
class DisplayStats:
    """Pre-formatted stats for display."""

    input_total: str = "0"
    output_total: str = "0"
    grand_total: str = "0"
    top_model: str = "N/A"
    top_model_tokens: int = 0
    recent_model_name: str = "N/A"
    recent_model_tokens: int = 0
    longest_streak: int = 0
    current_streak: int = 0
    peak_hour: str = "N/A"
    busiest_day: str = "N/A"
    avg_session: str = "N/A"


@dataclass
class GridCell:
    """A single cell in the heatmap grid."""

    date: str = ""
    tokens: int = 0


@dataclass
class GridResult:
    """Result of building a heatmap grid."""

    grid: list[list[GridCell]] = field(default_factory=lambda: [[] for _ in range(7)])
    week_months: list[int] = field(default_factory=list)
    max_tokens: int = 0
    num_weeks: int = 0


@dataclass
class RenderOptions:
    """Options for rendering output."""

    theme: str = "green"
    user: Optional[str] = None
    year: Optional[int] = None
    show_cost: bool = False
