"""Debug/verbose logging for tokenviz."""

_enabled: bool = False


def set_verbose(on: bool) -> None:
    """Enable or disable debug output."""
    global _enabled
    _enabled = on


def verbose() -> bool:
    """Return whether verbose mode is on."""
    return _enabled


def debug(msg: str) -> None:
    """Print a debug message to stderr if verbose mode is enabled."""
    if _enabled:
        import sys
        print(f"[debug] {msg}", file=sys.stderr)
