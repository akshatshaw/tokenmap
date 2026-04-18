"""JSONL streaming reader for tokenviz."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Generator, Optional

MAX_BYTES = int(os.environ.get("BRAGGRID_MAX_RECORD_BYTES", "67108864"))


def stream_jsonl(
    file_path: str,
    pre_filter: Optional[Callable[[str], bool]] = None,
) -> Generator[Any, None, None]:
    """Stream and parse lines from a JSONL file.

    Args:
        file_path: Path to the JSONL file.
        pre_filter: Optional function — only parse lines where this returns True.

    Yields:
        Parsed JSON objects from qualifying lines.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                if len(line.encode("utf-8")) > MAX_BYTES:
                    print(
                        f"[tokenviz] Skipping oversized record: {file_path}:{line_num} (>{MAX_BYTES} bytes)",
                        file=sys.stderr,
                    )
                    continue
                if pre_filter and not pre_filter(line):
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass  # skip malformed lines
    except OSError:
        pass  # file not readable
