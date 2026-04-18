"""tokenviz — GitHub-style contribution heatmap for AI coding tool usage."""

__version__ = "0.1.0"

from tokenviz.aggregator import aggregate_multi
from tokenviz.stats import compute_stats, format_tokens
from tokenviz.render.terminal import render_terminal
from tokenviz.render.svg import render_svg
from tokenviz.pricing import compute_cost_summary, format_cost
from tokenviz.themes import get_theme, get_all_theme_names

__all__ = [
    "__version__",
    "aggregate_multi",
    "compute_stats",
    "format_tokens",
    "render_terminal",
    "render_svg",
    "compute_cost_summary",
    "format_cost",
    "get_theme",
    "get_all_theme_names",
]
