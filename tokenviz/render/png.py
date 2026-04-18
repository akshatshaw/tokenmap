"""PNG conversion for tokenviz — converts SVG to PNG using CairoSVG."""

from __future__ import annotations

from pathlib import Path


def svg_to_png(
    svg_string: str,
    output_path: str | None = None,
    background: str = "#1a1a2e",
    width: int = 4000,
) -> bytes:
    """Convert an SVG string to PNG.

    Args:
        svg_string: SVG content as a string.
        output_path: Optional path to write the PNG file.
        background: Background color (hex string).
        width: Target width for the output image.

    Returns:
        PNG data as bytes.
    """
    import cairosvg

    png_data = cairosvg.svg2png(
        bytestring=svg_string.encode("utf-8"),
        output_width=width,
        background_color=background,
    )

    if output_path:
        Path(output_path).write_bytes(png_data)

    return png_data
