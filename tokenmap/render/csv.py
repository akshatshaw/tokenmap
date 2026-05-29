"""CSV exporter for tokenmap — one row per (day, tool) with token + cost columns."""

from __future__ import annotations

import csv
import io
from typing import Optional

from tokenmap.pricing import _calculate_model_cost
from tokenmap.types import DayData, ModelTokenDetail, RenderOptions, ToolPanel

CSV_HEADER = [
    "date", "tool", "input_tokens", "output_tokens",
    "cache_read_tokens", "total_tokens", "est_cost_usd",
]


def _estimate_day_cost(day: DayData) -> float:
    """Estimate a day's cost.

    Per-model input/output/cache splits aren't stored per day, so we distribute
    the day's aggregate splits across that day's models in proportion to each
    model's token share, then price each slice. Falls back to default pricing
    when no per-model breakdown is available.
    """
    day_total = sum(day.models.values())
    if day_total <= 0:
        detail = ModelTokenDetail(
            input_tokens=day.input_tokens,
            output_tokens=day.output_tokens,
            cache_read_tokens=day.cache_read_tokens,
        )
        return _calculate_model_cost("", detail).total_cost

    cost = 0.0
    for model, model_tokens in day.models.items():
        ratio = model_tokens / day_total
        detail = ModelTokenDetail(
            input_tokens=round(day.input_tokens * ratio),
            output_tokens=round(day.output_tokens * ratio),
            cache_read_tokens=round(day.cache_read_tokens * ratio),
        )
        cost += _calculate_model_cost(model, detail).total_cost
    return cost


def render_csv(panels: list[ToolPanel], opts: Optional[RenderOptions] = None) -> str:
    """Render panels as CSV text: one row per day per tool, sorted by date."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for panel in panels:
        for day in sorted(panel.data.days, key=lambda d: d.date):
            total = (day.input_tokens or 0) + (day.output_tokens or 0) + (day.cache_read_tokens or 0)
            cost = _estimate_day_cost(day)
            writer.writerow([
                day.date, panel.tool,
                day.input_tokens, day.output_tokens, day.cache_read_tokens,
                total, f"{cost:.4f}",
            ])
    return buf.getvalue()
