"""CLI entry point for tokenmap."""

from __future__ import annotations

import os
import sys
from datetime import datetime

import click

from tokenmap.aggregator import aggregate_multi, filter_panel_by_model
from tokenmap.clipboard import copy_image_to_clipboard
from tokenmap.lib.debug import set_verbose
from tokenmap.render.csv import render_csv
from tokenmap.render.terminal import render_terminal
from tokenmap.render.svg import render_svg
from tokenmap.render.png import svg_to_png
from tokenmap.themes import get_all_theme_names, get_bg_color
from tokenmap.types import DateRange, RenderOptions

DEFAULT_THEME = "dark-green"


def _get_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%Y%m%d_%H%M%S")


def _confirm_save(file_path: str) -> bool:
    try:
        answer = input(f"Save to {file_path}? (y/n) ")
        return answer.strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _validate_date(value: str, flag: str) -> str:
    """Validate a YYYY-MM-DD date string, exiting with an error if malformed."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        click.echo(f"Invalid {flag} date: {value!r}. Expected YYYY-MM-DD.", err=True)
        sys.exit(1)
    return value


def _infer_format(path: str) -> str:
    """Infer an export format from an output path's extension (default png)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".svg":
        return "svg"
    if ext == ".csv":
        return "csv"
    return "png"


@click.command("tokenmap")
@click.option("--claude/--no-claude", "use_claude", default=True,
              help="Include Claude Code data (default: on)")
@click.option("--codex", "use_codex", is_flag=True, help="Include Codex data")
@click.option("--opencode", "use_opencode", is_flag=True, help="Include OpenCode data")
@click.option("--cursor", "use_cursor", is_flag=True, help="Include Cursor data")
@click.option("--user", default=None, help="Username to display")
@click.option("--theme", default=DEFAULT_THEME, help="Color theme (see --list-themes)")
@click.option("--export", "export_fmt", type=click.Choice(["png", "svg", "csv"]),
              default=None, help="Write an output file in this format (default: terminal only)")
@click.option("--no-export", is_flag=True, help="Force terminal-only output (overrides --export/--out)")
@click.option("--out", default=None, help="Custom output file path (implies export; format inferred from extension)")
@click.option("--copy", "do_copy", is_flag=True, help="Copy PNG to clipboard (implies PNG export)")
@click.option("--year", default=None, type=int, help="Filter to a specific year")
@click.option("--since", default=None, help="Start date, inclusive (YYYY-MM-DD)")
@click.option("--until", default=None, help="End date, inclusive (YYYY-MM-DD)")
@click.option("--model", "model_filter", default=None, help="Filter to models matching this name (substring)")
@click.option("--json", "as_json", is_flag=True, help="Output raw stats as JSON")
@click.option("--list-themes", is_flag=True, help="Show all available themes")
@click.option("--verbose", is_flag=True, help="Show debug output")
@click.option("--cost/--no-cost", "show_cost", default=True,
              help="Show estimated cost breakdown by model (default: on)")
@click.option("--live-pricing/--no-live-pricing", "live_pricing", default=True,
              help="Fetch current model pricing from LiteLLM's public catalog, "
                   "cached 24h (default: on; falls back to built-in table offline)")
@click.version_option(version="0.1.4", prog_name="tokenmap")
def main(
    use_claude: bool,
    use_codex: bool,
    use_opencode: bool,
    use_cursor: bool,
    user: str | None,
    theme: str,
    export_fmt: str | None,
    no_export: bool,
    out: str | None,
    do_copy: bool,
    year: int | None,
    since: str | None,
    until: str | None,
    model_filter: str | None,
    as_json: bool,
    list_themes: bool,
    verbose: bool,
    show_cost: bool,
    live_pricing: bool,
) -> None:
    """Shareable heatmap of your AI coding tool usage."""
    try:
        if list_themes:
            click.echo("Available themes:\n")
            for name in get_all_theme_names():
                marker = " (default)" if name == DEFAULT_THEME else ""
                click.echo(f"  {name}{marker}")
            return

        theme_names = get_all_theme_names()
        if theme not in theme_names:
            click.echo(f"Unknown theme: {theme}. Available: {', '.join(theme_names)}", err=True)
            sys.exit(1)

        # Build the date window. --since/--until win over --year (full-year sugar).
        since_s = _validate_date(since, "--since") if since else None
        until_s = _validate_date(until, "--until") if until else None
        if since_s and until_s and since_s > until_s:
            click.echo("--since must be on or before --until.", err=True)
            sys.exit(1)
        if since_s or until_s:
            date_range = DateRange(since=since_s, until=until_s)
        else:
            date_range = DateRange.from_year(year)

        # Resolve export format. Default is terminal-only; --export, --out, or
        # --copy opt into writing a file. --no-export forces terminal-only.
        if no_export:
            fmt: str | None = None
        elif export_fmt:
            fmt = export_fmt
        elif out:
            fmt = _infer_format(out)
        else:
            fmt = None
        if do_copy and fmt is None and not no_export:
            fmt = "png"

        if verbose:
            set_verbose(True)

        if live_pricing:
            from tokenmap.pricing import set_live_pricing
            set_live_pricing(True)

        # Tool selection:
        #   - Claude is included by default (--no-claude opts out).
        #   - Explicitly naming other tools (--codex/--opencode/--cursor) loads
        #     exactly those (plus Claude unless --no-claude).
        #   - With no other tool named, auto-detect whatever is installed; drop
        #     Claude from that set when --no-claude was passed.
        explicit_others = [
            name for name, on in (
                ("codex", use_codex),
                ("opencode", use_opencode),
                ("cursor", use_cursor),
            ) if on
        ]
        if explicit_others:
            selected = (["claude"] if use_claude else []) + explicit_others
            panels = aggregate_multi(tools=selected, date_range=date_range)
        else:
            panels = aggregate_multi(tools=None, date_range=date_range)
            if not use_claude:
                panels = [p for p in panels if p.tool != "claude"]

        if not panels:
            click.echo("No AI coding tool data found. Supported: Claude Code, Codex, OpenCode, Cursor.", err=True)
            sys.exit(1)

        if model_filter:
            filtered = [
                fp for p in panels
                if (fp := filter_panel_by_model(p, model_filter)) is not None
            ]
            if not filtered:
                click.echo(f"No usage found for a model matching '{model_filter}'.", err=True)
                sys.exit(1)
            panels = filtered

        render_opts = RenderOptions(
            theme=theme, user=user, year=year,
            show_cost=show_cost, date_range=date_range,
        )

        if as_json:
            import json
            import dataclasses

            def _serialize(obj: object) -> object:
                if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                    return dataclasses.asdict(obj)
                return str(obj)

            payload = json.dumps(
                [dataclasses.asdict(p) for p in panels],
                indent=2,
                default=_serialize,
            )
            if out:
                abs_path = os.path.abspath(out)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(payload)
                click.echo(f"Saved JSON to {abs_path}")
            else:
                click.echo(payload)
            return

        render_terminal(panels, render_opts)

        if fmt:
            ts = _get_timestamp()
            out_path = out or f"tokenmap_{ts}.{fmt}"
            abs_path = os.path.abspath(out_path)

            if fmt == "csv":
                content = render_csv(panels, render_opts)
                if not _confirm_save(abs_path):
                    click.echo("Skipped saving.")
                    return
                with open(out_path, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                click.echo(f"\nSaved to {abs_path}")
                return

            svg = render_svg(panels, render_opts)
            if not _confirm_save(abs_path):
                click.echo("Skipped saving.")
                return

            if fmt == "svg":
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(svg)
                click.echo(f"\nSaved to {abs_path}")
            else:
                svg_to_png(svg, out_path, background=get_bg_color(theme))
                click.echo(f"\nSaved to {abs_path}")

                if do_copy:
                    try:
                        copy_image_to_clipboard(abs_path)
                        click.echo("Copied to clipboard!")
                    except Exception:
                        click.echo("Could not copy to clipboard.", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if os.environ.get("DEBUG"):
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
