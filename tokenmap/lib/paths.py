"""Platform-specific data paths for AI coding tools."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path


def _home() -> Path:
    return Path.home()


def claude_paths() -> list[str]:
    """Return candidate directories for Claude Code data."""
    dirs: list[str] = []
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_dir:
        dirs.append(env_dir)
    home = _home()
    dirs.append(str(home / ".claude"))
    dirs.append(str(home / ".config" / "claude"))
    return [d for d in dirs if os.path.isdir(d)]


@dataclass
class CodexPaths:
    base: str
    sessions: str
    db: str


def codex_paths() -> CodexPaths:
    """Return paths for Codex CLI data."""
    home = _home()
    base = os.environ.get("CODEX_HOME") or str(home / ".codex")
    return CodexPaths(
        base=base,
        sessions=os.path.join(base, "sessions"),
        db=os.path.join(base, "state_5.sqlite"),
    )


@dataclass
class OpencodePaths:
    base: str
    db: str
    messages: str
    sessions: str


def opencode_paths() -> OpencodePaths:
    """Return paths for OpenCode data."""
    home = _home()
    base = os.environ.get("OPENCODE_DATA_DIR") or str(home / ".local" / "share" / "opencode")
    return OpencodePaths(
        base=base,
        db=os.path.join(base, "opencode.db"),
        messages=os.path.join(base, "storage", "message"),
        sessions=os.path.join(base, "storage", "session"),
    )


def cursor_state_paths() -> list[str]:
    """Return candidate paths for Cursor's state.vscdb."""
    env_path = os.environ.get("CURSOR_STATE_DB_PATH")
    if env_path:
        return [env_path] if os.path.isfile(env_path) else []

    paths: list[str] = []
    env_config = os.environ.get("CURSOR_CONFIG_DIR")
    if env_config:
        paths.append(os.path.join(env_config, "User", "globalStorage", "state.vscdb"))

    home = _home()
    plat = sys.platform
    if plat == "darwin":
        paths.append(str(home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"))
    elif plat == "win32":
        appdata = os.environ.get("APPDATA", "")
        paths.append(os.path.join(appdata, "Cursor", "User", "globalStorage", "state.vscdb"))
    else:
        paths.append(str(home / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"))

    return [p for p in paths if os.path.isfile(p)]
