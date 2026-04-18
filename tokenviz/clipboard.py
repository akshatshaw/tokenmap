"""OS clipboard integration for tokenviz."""

from __future__ import annotations

import subprocess
import sys


def copy_image_to_clipboard(png_path: str) -> None:
    """Copy a PNG image to the system clipboard."""
    platform = sys.platform

    if platform == "darwin":
        safe_path = png_path.replace("'", "'\\''")
        subprocess.run(
            ["osascript", "-e",
             f"set the clipboard to (read (POSIX file '{safe_path}') as «class PNGf»)"],
            check=True, capture_output=True,
        )
    elif platform == "linux":
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", png_path],
            check=True, capture_output=True,
        )
    elif platform == "win32":
        safe_path = png_path.replace("'", "''")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Set-Clipboard -Path '{safe_path}'"],
            check=True, capture_output=True,
        )
    else:
        raise RuntimeError(f"Unsupported platform for clipboard copy: {platform}")
