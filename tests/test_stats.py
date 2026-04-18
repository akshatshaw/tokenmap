"""Tests for tokenmap.stats module."""

from tokenmap.stats import format_tokens, compute_stats
from tokenmap.types import AggregatedData, DayData


class TestFormatTokens:
    def test_zero(self):
        assert format_tokens(0) == "0"

    def test_hundreds(self):
        assert format_tokens(500) == "500"

    def test_thousands(self):
        assert format_tokens(1500) == "1.5K"

    def test_millions(self):
        assert format_tokens(2_500_000) == "2.5M"

    def test_billions(self):
        assert format_tokens(3_000_000_000) == "3.0B"

    def test_exact_thousand(self):
        assert format_tokens(1000) == "1.0K"

    def test_exact_million(self):
        assert format_tokens(1_000_000) == "1.0M"


class TestComputeStats:
    def test_empty_data(self):
        data = AggregatedData()
        stats = compute_stats(data)
        assert stats.total_tokens == 0
        assert stats.most_used_model is None
        assert stats.current_streak == 0
        assert stats.longest_streak == 0

    def test_basic_token_count(self):
        data = AggregatedData(
            days=[
                DayData(date="2025-01-01", input_tokens=1000, output_tokens=500, cache_read_tokens=200),
                DayData(date="2025-01-02", input_tokens=2000, output_tokens=800, cache_read_tokens=300),
            ],
        )
        stats = compute_stats(data)
        # effective_input = (1000+2000) + (200+300) = 3500
        # total = effective_input + output = 3500 + 1300 = 4800
        assert stats.input_tokens == 3500
        assert stats.output_tokens == 1300
        assert stats.total_tokens == 4800

    def test_model_usage(self):
        data = AggregatedData(
            days=[
                DayData(date="2025-01-01", input_tokens=100, output_tokens=50,
                        models={"gpt-4o": 150, "claude-sonnet-4": 50}),
                DayData(date="2025-01-02", input_tokens=200, output_tokens=100,
                        models={"gpt-4o": 300}),
            ],
        )
        stats = compute_stats(data)
        assert stats.most_used_model is not None
        assert stats.most_used_model["name"] == "gpt-4o"
        assert stats.most_used_model["tokens"] == 450

    def test_peak_hour(self):
        data = AggregatedData(
            days=[DayData(date="2025-01-01", input_tokens=100, output_tokens=50)],
            hour_counts={"14": 10, "9": 5, "22": 3},
        )
        stats = compute_stats(data)
        assert stats.peak_hour is not None
        assert stats.peak_hour["hour"] == "2:00 PM"
        assert stats.peak_hour["count"] == 10

    def test_busiest_day(self):
        # Monday is 2025-01-06
        data = AggregatedData(
            days=[
                DayData(date="2025-01-06", input_tokens=5000, output_tokens=2000),  # Monday
                DayData(date="2025-01-07", input_tokens=100, output_tokens=50),    # Tuesday
            ],
        )
        stats = compute_stats(data)
        assert stats.busiest_day == "Monday"

    def test_avg_session_minutes(self):
        data = AggregatedData(
            days=[DayData(date="2025-01-01", input_tokens=100, output_tokens=50)],
            avg_session_seconds=1800,  # 30 minutes
        )
        stats = compute_stats(data)
        assert stats.avg_session_minutes == 30
