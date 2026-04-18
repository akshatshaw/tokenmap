"""Tests for tokenviz.render.shared module."""

from tokenviz.render.shared import (
    build_grid, extract_display_stats, compute_global_totals,
)
from tokenviz.types import AggregatedData, DayData, Stats, ToolPanel, ToolCapabilities


class TestBuildGrid:
    def test_grid_has_7_rows(self):
        data = AggregatedData(days=[
            DayData(date="2025-06-15", input_tokens=100, output_tokens=50),
        ])
        result = build_grid(data)
        assert len(result.grid) == 7

    def test_max_tokens_tracked(self):
        data = AggregatedData(days=[
            DayData(date="2025-06-15", input_tokens=100, output_tokens=50),
            DayData(date="2025-06-16", input_tokens=500, output_tokens=200),
        ])
        result = build_grid(data)
        assert result.max_tokens == 700  # 500 + 200

    def test_year_filter(self):
        data = AggregatedData(days=[
            DayData(date="2025-06-15", input_tokens=100, output_tokens=50),
        ])
        result = build_grid(data, year=2025)
        assert result.num_weeks > 0

    def test_empty_data(self):
        data = AggregatedData()
        result = build_grid(data)
        assert result.max_tokens == 0
        assert result.num_weeks > 0


class TestExtractDisplayStats:
    def test_basic(self):
        stats = Stats(
            input_tokens=1500,
            output_tokens=500,
            total_tokens=2000,
            most_used_model={"name": "gpt-4o", "tokens": 1500},
            recent_model={"name": "claude-sonnet-4", "tokens": 300},
            current_streak=5,
            longest_streak=10,
            avg_session_minutes=25,
        )
        ds = extract_display_stats(stats)
        assert ds.input_total == "1.5K"
        assert ds.output_total == "500"
        assert ds.grand_total == "2.0K"
        assert ds.top_model == "gpt-4o"
        assert ds.current_streak == 5
        assert ds.avg_session == "25 min"

    def test_no_model(self):
        stats = Stats()
        ds = extract_display_stats(stats)
        assert ds.top_model == "N/A"
        assert ds.avg_session == "N/A"


class TestComputeGlobalTotals:
    def test_single_panel(self):
        panel = ToolPanel(
            tool="test",
            stats=Stats(input_tokens=1000, output_tokens=500),
        )
        totals = compute_global_totals([panel])
        assert totals["input_total"] == "1.0K"
        assert totals["output_total"] == "500"
        assert totals["grand_total"] == "1.5K"

    def test_multiple_panels(self):
        panels = [
            ToolPanel(tool="a", stats=Stats(input_tokens=1000, output_tokens=500)),
            ToolPanel(tool="b", stats=Stats(input_tokens=2000, output_tokens=1000)),
        ]
        totals = compute_global_totals(panels)
        assert totals["input_total"] == "3.0K"
        assert totals["output_total"] == "1.5K"
        assert totals["grand_total"] == "4.5K"
