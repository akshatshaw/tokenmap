"""Terminal renderer for tokenmap — uses Rich for colored output."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from tokenmap.themes import get_theme, is_dark
from tokenmap.stats import format_tokens
from tokenmap.pricing import compute_cost_summary, format_cost
from tokenmap.render.shared import (
    MONTH_NAMES, DAY_LABELS, TOOL_COLORS,
    build_grid, extract_display_stats, compute_global_totals,
)
from tokenmap.types import RenderOptions, Theme, ToolPanel

BLOCK = "\u2588\u2588"
TERMINAL_DAY_LABELS = [l if l else "   " for l in DAY_LABELS]


def _get_cell_color(tokens: int, max_tokens: int, theme: Theme) -> str:
    if not tokens or tokens <= 0:
        return theme.empty
    if max_tokens <= 0:
        return theme.empty
    ratio = tokens / max_tokens
    if ratio <= 0.25:
        return theme.scale[0]
    if ratio <= 0.50:
        return theme.scale[1]
    if ratio <= 0.75:
        return theme.scale[2]
    return theme.scale[3]


def render_terminal(panels: list[ToolPanel], opts: RenderOptions | None = None) -> None:
    """Render heatmap panels to the terminal."""
    if opts is None:
        opts = RenderOptions()

    console = Console()
    theme_name = opts.theme or "green"
    theme = get_theme(theme_name)
    use_dark = is_dark(theme_name)
    is_multi = len(panels) > 1

    text_color = theme.text if use_dark else "white"
    label_color = theme.label if use_dark else "bright_black"

    lines: list[str] = []

    def txt(s: str) -> str:
        return f"[bold {text_color}]{s}[/]"

    def lbl(s: str) -> str:
        return f"[{label_color}]{s}[/]"

    def colored(s: str, color: str) -> str:
        return f"[{color}]{s}[/]"

    lines.append(txt(" tokenmap"))
    if opts.user:
        lines.append(lbl(f" @{opts.user}"))
    lines.append("")

    if is_multi:
        totals = compute_global_totals(panels)
        lines.append(lbl(f" {totals['input_total']} in / {totals['output_total']} out / {totals['grand_total']} total"))
        lines.append("")

    for p_idx, panel in enumerate(panels):
        ds = extract_display_stats(panel.stats)
        gr = build_grid(panel.data, opts.year)
        tool_color = TOOL_COLORS.get(panel.tool, TOOL_COLORS["other"])

        if is_multi:
            lines.append(
                colored(f" \u25cf {panel.tool.upper()}", f"bold {tool_color}")
                + lbl(f"  {ds.input_total} in / {ds.output_total} out")
            )
        else:
            lines.append(lbl(f" {ds.input_total} in / {ds.output_total} out / {ds.grand_total} total"))
        lines.append("")

        # Month labels (first panel only)
        if p_idx == 0:
            prefix_len = 5
            month_line = " " * prefix_len
            last_month = -1
            for w in range(gr.num_weeks):
                expected_pos = prefix_len + w * 2
                m = gr.week_months[w]
                if m != last_month:
                    if len(month_line) < expected_pos:
                        month_line += " " * (expected_pos - len(month_line))
                    month_line += MONTH_NAMES[m]
                    last_month = m
                else:
                    target_pos = expected_pos + 2
                    if len(month_line) < target_pos:
                        month_line += " " * (target_pos - len(month_line))
            lines.append(lbl(month_line))

        # Grid rows
        for row in range(7):
            line = lbl(TERMINAL_DAY_LABELS[row] + " ")
            for w in range(len(gr.grid[row])):
                cell = gr.grid[row][w]
                color = _get_cell_color(cell.tokens, gr.max_tokens, theme)
                line += colored(BLOCK, color)
            lines.append(line)
        lines.append("")

        # Legend
        legend = "     " + lbl("LESS ")
        legend += colored(BLOCK, theme.empty)
        for c in theme.scale:
            legend += colored(BLOCK, c)
        legend += lbl(" MORE")
        lines.append(legend)
        lines.append("")

        # Divider
        grid_width = 5 + gr.num_weeks * 2
        lines.append(lbl(f"[dim] {'─' * min(grid_width, 100)}[/dim]"))
        lines.append("")

        # Stats row 1
        COL = 26
        def stat_label(s: str) -> str:
            return lbl(s.ljust(COL))
        def stat_value(s: str) -> str:
            return txt(str(s).ljust(COL))
        def stat_sub(s: str) -> str:
            return lbl(s.ljust(COL))

        lines.append(
            " " + stat_label("MOST USED MODEL") + stat_label("RECENT (30D)")
            + stat_label("LONGEST STREAK") + stat_label("CURRENT STREAK")
        )
        lines.append(
            " " + stat_value(ds.top_model) + stat_value(ds.recent_model_name)
            + stat_value(f"{ds.longest_streak} days") + stat_value(f"{ds.current_streak} days")
        )
        lines.append(
            " " + stat_sub(f"({format_tokens(ds.top_model_tokens)} tokens)")
            + stat_sub(f"({format_tokens(ds.recent_model_tokens)} tokens)")
        )
        lines.append("")

        # Stats row 2
        row2_labels: list[str] = []
        row2_values: list[str] = []
        if panel.capabilities.has_peak_hour:
            row2_labels.append("PEAK HOUR")
            row2_values.append(ds.peak_hour)
        row2_labels.append("BUSIEST DAY")
        row2_values.append(ds.busiest_day)
        if panel.capabilities.has_avg_session and ds.avg_session != "N/A":
            row2_labels.append("AVG SESSION")
            row2_values.append(ds.avg_session)

        if row2_labels:
            lines.append(" " + "".join(stat_label(l) for l in row2_labels))
            lines.append(" " + "".join(stat_value(v) for v in row2_values))
        lines.append("")

        # Cost breakdown
        if opts.show_cost:
            cost_summary = compute_cost_summary(panel.data.detailed_model_usage)
            if cost_summary.model_costs:
                lines.append(lbl(f"[dim] {'─' * min(grid_width, 100)}[/dim]"))
                lines.append("")
                lines.append(txt("  💰 ESTIMATED COST"))
                lines.append("")

                MC = 30
                CC = 14
                lines.append(
                    "  " + lbl("MODEL".ljust(MC)) + lbl("INPUT".ljust(CC))
                    + lbl("OUTPUT".ljust(CC)) + lbl("CACHE READ".ljust(CC))
                    + lbl("CACHE WRITE".ljust(CC)) + lbl("TOTAL")
                )
                for mc in cost_summary.model_costs:
                    model_name = mc.model[:MC - 3] + "…" if len(mc.model) > MC - 2 else mc.model
                    lines.append(
                        "  " + colored(model_name.ljust(MC), text_color)
                        + colored(format_cost(mc.input_cost).ljust(CC), text_color)
                        + colored(format_cost(mc.output_cost).ljust(CC), text_color)
                        + colored(format_cost(mc.cache_read_cost).ljust(CC), text_color)
                        + colored(format_cost(mc.cache_write_cost).ljust(CC), text_color)
                        + txt(format_cost(mc.total_cost))
                    )
                lines.append("")
                lines.append(
                    "  " + lbl("TOTAL".ljust(MC)) + " " * (CC * 4)
                    + colored(f"[bold]{format_cost(cost_summary.total_cost)}[/bold]", "green")
                )
                lines.append("")
                lines.append(lbl("[dim]  * Estimates based on public API pricing. Actual costs may vary.[/dim]"))
                lines.append("")

        if p_idx < len(panels) - 1:
            lines.append("")

    console.print("\n".join(lines))
