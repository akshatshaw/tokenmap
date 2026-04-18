"""CLI entry point for tokenmap."""

from __future__ import annotations

import os
import sys
from datetime import datetime

import click

from tokenmap.aggregator import aggregate_multi
from tokenmap.clipboard import copy_image_to_clipboard
from tokenmap.lib.debug import set_verbose
from tokenmap.render.shared import compute_global_totals
from tokenmap.render.terminal import render_terminal
from tokenmap.render.svg import render_svg
from tokenmap.render.png import svg_to_png
from tokenmap.themes import get_all_theme_names, get_bg_color
from tokenmap.types import RenderOptions


def _get_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%Y%m%d_%H%M%S")


def _confirm_save(file_path: str) -> bool:
    try:
        answer = input(f"Save to {file_path}? (y/n) ")
        return answer.strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


@click.command("tokenmap")
@click.option("--claude", "use_claude", is_flag=True, help="Include Claude Code data")
@click.option("--codex", "use_codex", is_flag=True, help="Include Codex data")
@click.option("--opencode", "use_opencode", is_flag=True, help="Include OpenCode data")
@click.option("--cursor", "use_cursor", is_flag=True, help="Include Cursor data")
@click.option("--user", default=None, help="Username to display")
@click.option("--theme", default="green", help="Color theme (see --list-themes)")
@click.option("--export", "export_fmt", default="png", help="Export format: png, svg")
@click.option("--no-export", is_flag=True, help="Skip file export")
@click.option("--out", default=None, help="Custom output file path")
@click.option("--copy", "do_copy", is_flag=True, help="Copy image to clipboard")
@click.option("--year", default=None, type=int, help="Filter to specific year")
@click.option("--json", "as_json", is_flag=True, help="Output raw stats as JSON")
@click.option("--list-themes", is_flag=True, help="Show all available themes")
@click.option("--verbose", is_flag=True, help="Show debug output")
@click.option("--cost", "show_cost", is_flag=True, help="Show estimated cost breakdown by model")
@click.version_option(version="0.1.1", prog_name="tokenmap")
def main(
    use_claude: bool,
    use_codex: bool,
    use_opencode: bool,
    use_cursor: bool,
    user: str | None,
    theme: str,
    export_fmt: str,
    no_export: bool,
    out: str | None,
    do_copy: bool,
    year: int | None,
    as_json: bool,
    list_themes: bool,
    verbose: bool,
    show_cost: bool,
) -> None:
    """Shareable heatmap of your AI coding tool usage."""
    try:
        if list_themes:
            click.echo("Available themes:\n")
            for name in get_all_theme_names():
                marker = " (default)" if name == "green" else ""
                click.echo(f"  {name}{marker}")
            return

        theme_names = get_all_theme_names()
        if theme not in theme_names:
            click.echo(f"Unknown theme: {theme}. Available: {', '.join(theme_names)}", err=True)
            sys.exit(1)

        fmt = None if no_export else export_fmt
        if fmt and fmt not in ("png", "svg"):
            click.echo(f"Unknown export format: {fmt}. Supported: png, svg", err=True)
            sys.exit(1)

        if verbose:
            set_verbose(True)

        tools: list[str] = []
        if use_claude:
            tools.append("claude")
        if use_codex:
            tools.append("codex")
        if use_opencode:
            tools.append("opencode")
        if use_cursor:
            tools.append("cursor")

        panels = aggregate_multi(
            tools=tools if tools else None,
            year=year,
        )

        if not panels:
            click.echo("No AI coding tool data found. Supported: Claude Code, Codex, OpenCode, Cursor.", err=True)
            sys.exit(1)

        if as_json:
            import json
            import dataclasses

            def _serialize(obj: object) -> object:
                if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                    return dataclasses.asdict(obj)
                return str(obj)

            click.echo(json.dumps(
                [dataclasses.asdict(p) for p in panels],
                indent=2,
                default=_serialize,
            ))
            return

        render_opts = RenderOptions(theme=theme, user=user, year=year, show_cost=show_cost)
        render_terminal(panels, render_opts)

        if fmt:
            svg = render_svg(panels, render_opts)
            ts = _get_timestamp()

            if fmt == "svg":
                out_path = out or f"tokenmap_{ts}.svg"
                abs_path = os.path.abspath(out_path)
                if not _confirm_save(abs_path):
                    click.echo("Skipped saving.")
                    return
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(svg)
                click.echo(f"\nSaved to {abs_path}")
            else:
                out_path = out or f"tokenmap_{ts}.png"
                abs_path = os.path.abspath(out_path)
                if not _confirm_save(abs_path):
                    click.echo("Skipped saving.")
                    return
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
