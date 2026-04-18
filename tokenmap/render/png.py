"""PNG conversion for tokenmap — converts SVG to PNG using CairoSVG."""

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
    import fitz
    import re

    # PyMuPDF requires CSS to be inline on the elements rather than a <style> block.
    # We parse the styles and inject them into the SVG string.
    from typing import Dict
    style_pattern = re.compile(r'\.([a-zA-Z0-9_-]+)\s*\{([^}]+)\}')
    styles: Dict[str, str] = {}
    for match in style_pattern.finditer(svg_string):
        class_name = match.group(1)
        rules = match.group(2).strip()
        
        inline_attrs = []
        for rule in rules.split(';'):
            rule = rule.strip()
            if not rule:
                continue
            key, val = rule.split(':', 1)
            val = val.strip().replace("'", "").replace('"', '')
            inline_attrs.append(f'{key.strip()}="{val}"')
            
        styles[class_name] = " ".join(inline_attrs)

    default_text_match = re.search(r'text\s*\{([^}]+)\}', svg_string)
    default_text_attrs = ""
    if default_text_match:
        rules = default_text_match.group(1).strip()
        attrs = []
        for rule in rules.split(';'):
            rule = rule.strip()
            if not rule:
                continue
            key, val = rule.split(':', 1)
            val = val.strip().replace("'", "").replace('"', '')
            attrs.append(f'{key.strip()}="{val}"')
        default_text_attrs = " ".join(attrs)

    # Inject
    out_svg = svg_string
    if default_text_attrs:
        out_svg = out_svg.replace('<text ', f'<text {default_text_attrs} ')
        
    for class_name, inline_attrs in styles.items():
        out_svg = out_svg.replace(f'class="{class_name}"', f'class="{class_name}" {inline_attrs} ')

    doc = fitz.open(stream=out_svg.encode("utf-8"), filetype="svg")
    page = doc.load_page(0)
    # Use a 3x scaling matrix for high-resolution (retina) PNG export
    mat = fitz.Matrix(3.0, 3.0)
    # Using alpha=False assumes white background (which matches the SVG rect).
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_data = pix.tobytes("png")

    if output_path:
        with open(output_path, "wb") as f:
            f.write(png_data)

    return png_data
