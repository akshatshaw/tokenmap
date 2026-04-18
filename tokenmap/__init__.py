"""tokenmap — GitHub-style contribution heatmap for AI coding tool usage."""

__version__ = "0.1.0"

from tokenmap.aggregator import aggregate_multi
from tokenmap.stats import compute_stats, format_tokens
from tokenmap.render.terminal import render_terminal
from tokenmap.render.svg import render_svg
from tokenmap.pricing import compute_cost_summary, format_cost
from tokenmap.themes import get_theme, get_all_theme_names

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
