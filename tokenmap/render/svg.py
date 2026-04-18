"""SVG renderer for tokenmap — generates SVG heatmap images."""

from __future__ import annotations

import math
from datetime import datetime

from tokenmap.themes import get_theme
from tokenmap.stats import format_tokens
from tokenmap.pricing import compute_cost_summary, format_cost
from tokenmap.render.shared import (
    MONTH_NAMES, DAY_LABELS, TOOL_COLORS,
    build_grid, extract_display_stats, compute_global_totals,
)
from tokenmap.types import GridResult, RenderOptions, Theme, ToolPanel

CELL_SIZE = 11
CELL_GAP = 2
CELL_RADIUS = 3
MARGIN_LEFT = 60
MARGIN_RIGHT = 20
PANEL_GAP = 20
BOTTOM_PAD = 10
HEATMAP_GAMMA = 0.7

TOOL_DISPLAY_NAMES = {
    "claude": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
    "cursor": "Cursor",
}


def _escape_xml(s: str) -> str:
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def _get_cell_color(tokens: int, max_tokens: int, theme: Theme) -> str:
    if not tokens or tokens <= 0:
        return theme.empty
    if max_tokens <= 0:
        return theme.empty
    scaled = math.pow(tokens / max_tokens, HEATMAP_GAMMA)
    index = math.ceil(scaled * (len(theme.scale) - 1))
    return theme.scale[min(max(index, 0), len(theme.scale) - 1)]


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "\u2026"


def _render_panel(
    parts: list[str], panel: ToolPanel, grid_result: GridResult,
    y_offset: int, grid_width: int, num_weeks: int, step: int,
    theme: Theme, is_multi: bool,
    show_month_labels: bool = True, show_cost: bool = False,
) -> int:
    ds = extract_display_stats(panel.stats)
    grid = grid_result.grid
    week_months = grid_result.week_months
    max_tokens = grid_result.max_tokens
    grid_height = 7 * step - CELL_GAP

    y = y_offset

    if is_multi:
        tool_color = TOOL_COLORS.get(panel.tool, TOOL_COLORS["other"])
        display_name = TOOL_DISPLAY_NAMES.get(panel.tool, panel.tool)
        dot_x = MARGIN_LEFT - 8
        parts.append(f'<circle cx="{dot_x}" cy="{y + 6}" r="4" fill="{tool_color}" />')
        parts.append(f'<text x="{MARGIN_LEFT}" y="{y + 10}" style="font-size: 13px; font-weight: 700; fill: {theme.text}; letter-spacing: 0.3px;" dominant-baseline="auto">{_escape_xml(display_name)}</text>')
        y += 32

    if show_month_labels:
        last_month = -1
        for w in range(num_weeks):
            m = week_months[w]
            if m != last_month:
                x = MARGIN_LEFT + w * step
                parts.append(f'<text x="{x}" y="{y}" class="label">{_escape_xml(MONTH_NAMES[m])}</text>')
                last_month = m
        y += 14

    for row in range(7):
        if DAY_LABELS[row]:
            label_y = y + row * step + CELL_SIZE // 2
            parts.append(f'<text x="{MARGIN_LEFT - 8}" y="{label_y}" class="label" text-anchor="end" dominant-baseline="middle">{_escape_xml(DAY_LABELS[row])}</text>')

    for row in range(7):
        for w in range(len(grid[row])):
            cell = grid[row][w]
            color = _get_cell_color(cell.tokens, max_tokens, theme)
            cx = MARGIN_LEFT + w * step
            cy = y + row * step
            parts.append(f'<rect x="{cx}" y="{cy}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="{CELL_RADIUS}" ry="{CELL_RADIUS}" fill="{color}"><title>{_escape_xml(cell.date)}: {cell.tokens:,} tokens</title></rect>')
    y += grid_height

    # Legend
    y += 12
    legend_x = MARGIN_LEFT
    legend_cy = y + CELL_SIZE // 2 + 1
    parts.append(f'<text x="{legend_x}" y="{legend_cy}" class="label" dominant-baseline="central">LESS</text>')
    legend_x += 35
    for color in [theme.empty] + theme.scale:
        parts.append(f'<rect x="{legend_x}" y="{y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="{CELL_RADIUS}" ry="{CELL_RADIUS}" fill="{color}" />')
        legend_x += step
    parts.append(f'<text x="{legend_x + 4}" y="{legend_cy}" class="label" dominant-baseline="central">MORE</text>')
    y += CELL_SIZE

    # Divider
    y += 10
    parts.append(f'<line x1="{MARGIN_LEFT}" y1="{y}" x2="{MARGIN_LEFT + grid_width}" y2="{y}" stroke="{theme.label}" stroke-opacity="0.15" stroke-width="1" />')
    y += 18

    # Stats
    col_width = grid_width / 4
    stats_row1 = [
        {"label": "MOST USED MODEL", "value": _truncate(ds.top_model, 20), "sub": f"{format_tokens(ds.top_model_tokens)} tokens"},
        {"label": "RECENT (30D)", "value": _truncate(ds.recent_model_name, 20), "sub": f"{format_tokens(ds.recent_model_tokens)} tokens"},
        {"label": "LONGEST STREAK", "value": f"{ds.longest_streak} days", "sub": ""},
        {"label": "CURRENT STREAK", "value": f"{ds.current_streak} days", "sub": ""},
    ]
    for i, s in enumerate(stats_row1):
        x = MARGIN_LEFT + i * col_width
        parts.append(f'<text x="{x}" y="{y}" class="small-label" dominant-baseline="hanging">{_escape_xml(s["label"])}</text>')
        parts.append(f'<text x="{x}" y="{y + 14}" class="value" dominant-baseline="hanging">{_escape_xml(s["value"])}</text>')
        if s["sub"]:
            parts.append(f'<text x="{x}" y="{y + 30}" class="stat-sub" dominant-baseline="hanging">{_escape_xml(s["sub"])}</text>')
    y += 46

    row2: list[dict[str, str]] = []
    if panel.capabilities.has_peak_hour:
        row2.append({"label": "PEAK HOUR", "value": ds.peak_hour})
    row2.append({"label": "BUSIEST DAY", "value": ds.busiest_day})
    if panel.capabilities.has_avg_session and ds.avg_session != "N/A":
        row2.append({"label": "AVG SESSION", "value": ds.avg_session})

    if row2:
        for i, s in enumerate(row2):
            x = MARGIN_LEFT + i * col_width
            parts.append(f'<text x="{x}" y="{y}" class="small-label" dominant-baseline="hanging">{_escape_xml(s["label"])}</text>')
            parts.append(f'<text x="{x}" y="{y + 14}" class="value" dominant-baseline="hanging">{_escape_xml(s["value"])}</text>')
        y += 30

    # Cost section
    if show_cost:
        cost_summary = compute_cost_summary(panel.data.detailed_model_usage)
        if cost_summary.model_costs:
            y += 10
            parts.append(f'<line x1="{MARGIN_LEFT}" y1="{y}" x2="{MARGIN_LEFT + grid_width}" y2="{y}" stroke="{theme.label}" stroke-opacity="0.15" stroke-width="1" />')
            y += 18
            icon_x = MARGIN_LEFT
            icon_cy = y + 7
            parts.append(f'<circle cx="{icon_x + 7}" cy="{icon_cy}" r="8" fill="#22C55E" opacity="0.9" />')
            parts.append(f'<text x="{icon_x + 7}" y="{icon_cy}" style="font-size: 11px; font-weight: 700; fill: #fff;" text-anchor="middle" dominant-baseline="central">$</text>')
            parts.append(f'<text x="{icon_x + 20}" y="{y}" style="font-size: 13px; font-weight: 700; fill: {theme.text};" dominant-baseline="hanging">Estimated Cost</text>')
            y += 24

            cost_cols = [
                ("MODEL", grid_width * 0.30), ("INPUT", grid_width * 0.14),
                ("OUTPUT", grid_width * 0.14), ("CACHE READ", grid_width * 0.14),
                ("CACHE WRITE", grid_width * 0.14), ("TOTAL", grid_width * 0.14),
            ]
            col_x = MARGIN_LEFT
            for label, width in cost_cols:
                parts.append(f'<text x="{col_x}" y="{y}" class="small-label" dominant-baseline="hanging">{_escape_xml(label)}</text>')
                col_x += width
            y += 16

            for mc in cost_summary.model_costs:
                col_x = MARGIN_LEFT
                parts.append(f'<text x="{col_x}" y="{y}" style="font-size: 11px; fill: {theme.text};" dominant-baseline="hanging">{_escape_xml(_truncate(mc.model, 25))}</text>')
                col_x += cost_cols[0][1]
                for val in [mc.input_cost, mc.output_cost, mc.cache_read_cost, mc.cache_write_cost]:
                    parts.append(f'<text x="{col_x}" y="{y}" style="font-size: 11px; fill: {theme.text};" dominant-baseline="hanging">{_escape_xml(format_cost(val))}</text>')
                    col_x += cost_cols[1][1]
                parts.append(f'<text x="{col_x}" y="{y}" style="font-size: 12px; font-weight: 700; fill: {theme.text};" dominant-baseline="hanging">{_escape_xml(format_cost(mc.total_cost))}</text>')
                y += 18

            y += 4
            parts.append(f'<line x1="{MARGIN_LEFT}" y1="{y}" x2="{MARGIN_LEFT + grid_width}" y2="{y}" stroke="{theme.label}" stroke-opacity="0.1" stroke-width="1" />')
            y += 10
            parts.append(f'<text x="{MARGIN_LEFT}" y="{y}" style="font-size: 12px; font-weight: 700; fill: {theme.text};" dominant-baseline="hanging">TOTAL</text>')
            total_x = MARGIN_LEFT + sum(w for _, w in cost_cols[:5])
            parts.append(f'<text x="{total_x}" y="{y}" style="font-size: 14px; font-weight: 700; fill: #22C55E;" dominant-baseline="hanging">{_escape_xml(format_cost(cost_summary.total_cost))}</text>')
            y += 20
            parts.append(f'<text x="{MARGIN_LEFT}" y="{y}" style="font-size: 8px; fill: {theme.label}; opacity: 0.6;" dominant-baseline="hanging">* Estimates based on public API pricing. Actual costs may vary.</text>')
            y += 14

    return y - y_offset


def render_svg(panels: list[ToolPanel], opts: RenderOptions | None = None) -> str:
    """Render panels as an SVG string."""
    if opts is None:
        opts = RenderOptions()

    theme = get_theme(opts.theme or "green")
    user = _truncate(opts.user, 24) if opts.user else None
    font_family = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    is_multi = len(panels) > 1
    show_cost = opts.show_cost

    step = CELL_SIZE + CELL_GAP
    panel_grids = [build_grid(p.data, opts.year) for p in panels]
    num_weeks = panel_grids[0].num_weeks
    grid_width = num_weeks * step - CELL_GAP
    total_width = MARGIN_LEFT + grid_width + MARGIN_RIGHT

    parts: list[str] = []

    parts.append(f"""<style>
    text {{ font-family: {font_family}; }}
    .title {{ font-size: 20px; font-weight: 700; fill: {theme.text}; }}
    .subtitle {{ font-size: 13px; fill: {theme.label}; }}
    .small-label {{ font-size: 9px; font-weight: 600; fill: {theme.label}; text-transform: uppercase; letter-spacing: 0.5px; }}
    .value {{ font-size: 14px; font-weight: 600; fill: {theme.text}; }}
    .label {{ font-size: 10px; fill: {theme.label}; }}
    .stat-sub {{ font-size: 10px; fill: {theme.label}; }}
    .metric-label {{ font-size: 9px; font-weight: 600; fill: {theme.label}; text-transform: uppercase; letter-spacing: 0.5px; }}
    .metric-value {{ font-size: 16px; font-weight: 700; fill: {theme.text}; }}
  </style>""")

    parts.append(f'<text x="{MARGIN_LEFT}" y="26" class="title" dominant-baseline="auto">{_escape_xml("tokenmap")}</text>')
    if user:
        parts.append(f'<text x="{MARGIN_LEFT}" y="44" class="subtitle" dominant-baseline="auto">@{_escape_xml(user)}</text>')
        y = 64
    else:
        y = 50

    if is_multi:
        totals = compute_global_totals(panels)
    else:
        ds = extract_display_stats(panels[0].stats)
        totals = {"input_total": ds.input_total, "output_total": ds.output_total, "grand_total": ds.grand_total}

    metric_col = grid_width / 3
    parts.append(f'<text x="{MARGIN_LEFT}" y="{y}" class="metric-label" dominant-baseline="hanging">INPUT</text>')
    parts.append(f'<text x="{MARGIN_LEFT}" y="{y + 13}" class="metric-value" dominant-baseline="hanging">{_escape_xml(totals["input_total"])}</text>')
    parts.append(f'<text x="{MARGIN_LEFT + metric_col}" y="{y}" class="metric-label" dominant-baseline="hanging">OUTPUT</text>')
    parts.append(f'<text x="{MARGIN_LEFT + metric_col}" y="{y + 13}" class="metric-value" dominant-baseline="hanging">{_escape_xml(totals["output_total"])}</text>')
    parts.append(f'<text x="{MARGIN_LEFT + metric_col * 2}" y="{y}" class="metric-label" dominant-baseline="hanging">TOTAL</text>')
    parts.append(f'<text x="{MARGIN_LEFT + metric_col * 2}" y="{y + 13}" class="metric-value" dominant-baseline="hanging">{_escape_xml(totals["grand_total"])}</text>')
    y += 42

    if is_multi:
        cols = 2
        col_w = grid_width / cols
        row_h = 32
        for i, p in enumerate(panels):
            ds = extract_display_stats(p.stats)
            tool_color = TOOL_COLORS.get(p.tool, TOOL_COLORS["other"])
            display_name = TOOL_DISPLAY_NAMES.get(p.tool, p.tool)
            col = i % cols
            row = i // cols
            x = MARGIN_LEFT + col * col_w
            row_y = y + row * row_h
            parts.append(f'<circle cx="{x + 4}" cy="{row_y + 5}" r="3.5" fill="{tool_color}" />')
            parts.append(f'<text x="{x + 14}" y="{row_y + 6}" style="font-size: 11px; font-weight: 600; fill: {theme.text};" dominant-baseline="middle">{_escape_xml(display_name)}</text>')
            parts.append(f'<text x="{x + 14}" y="{row_y + 20}" style="font-size: 9px; fill: {theme.label};">{_escape_xml(ds.input_total)} in / {_escape_xml(ds.output_total)} out / {_escape_xml(ds.grand_total)} total</text>')
        num_rows = math.ceil(len(panels) / cols)
        y += num_rows * row_h

    y += 6

    for i, panel in enumerate(panels):
        if i > 0:
            y += PANEL_GAP
        show_months = i == 0
        panel_height = _render_panel(parts, panel, panel_grids[i], y, grid_width, num_weeks, step, theme, is_multi, show_months, show_cost)
        y += panel_height

    y += BOTTOM_PAD
    now = datetime.now()
    generated_at = f"Generated at {now.strftime('%b %d, %Y %I:%M %p')}"
    parts.append(f'<text x="{MARGIN_LEFT + grid_width}" y="{y}" class="label" text-anchor="end" dominant-baseline="auto" opacity="0.5">{_escape_xml(generated_at)}</text>')
    y += 14

    total_height = y
    header = f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{total_height}" viewBox="0 0 {total_width} {total_height}">'
    bg = f'<rect x="-2" y="-2" width="{total_width + 4}" height="{total_height + 4}" rx="12" fill="{theme.bg}" />'

    return "\n".join([header, parts[0], bg] + parts[1:] + ["</svg>"])
