"""Tests for tokenviz.aggregator module."""

from unittest.mock import patch

from tokenviz.aggregator import aggregate_multi
from tokenviz.types import AdapterResult, DayData


def _mock_result(tool: str) -> AdapterResult:
    return AdapterResult(
        tool=tool,
        days=[
            DayData(date="2025-01-01", input_tokens=1000, output_tokens=500,
                    models={"gpt-4o": 1500}),
            DayData(date="2025-01-02", input_tokens=2000, output_tokens=800,
                    models={"gpt-4o": 2800}),
        ],
        hour_counts={"14": 5, "15": 3},
        total_sessions=2,
        total_messages=4,
        first_session_date="2025-01-01",
        model_usage={"gpt-4o": 4300},
    )


class TestAggregateMulti:
    @patch("tokenviz.adapters.claude.detect", return_value=True)
    @patch("tokenviz.adapters.claude.load", return_value=_mock_result("claude"))
    @patch("tokenviz.adapters.codex.detect", return_value=False)
    @patch("tokenviz.adapters.opencode.detect", return_value=False)
    @patch("tokenviz.adapters.cursor.detect", return_value=False)
    def test_auto_detect(self, *mocks):
        panels = aggregate_multi()
        assert len(panels) == 1
        assert panels[0].tool == "claude"
        assert panels[0].stats.total_tokens > 0

    @patch("tokenviz.adapters.claude.load", return_value=_mock_result("claude"))
    def test_explicit_tool(self, mock_load):
        panels = aggregate_multi(tools=["claude"])
        assert len(panels) == 1
        assert panels[0].tool == "claude"

    def test_unknown_tool_raises(self):
        try:
            aggregate_multi(tools=["unknown_tool"])
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unknown tool" in str(e)

    @patch("tokenviz.adapters.claude.detect", return_value=False)
    @patch("tokenviz.adapters.codex.detect", return_value=False)
    @patch("tokenviz.adapters.opencode.detect", return_value=False)
    @patch("tokenviz.adapters.cursor.detect", return_value=False)
    def test_no_tools_detected(self, *mocks):
        panels = aggregate_multi()
        assert len(panels) == 0
