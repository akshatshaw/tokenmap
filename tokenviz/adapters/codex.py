"""Codex CLI adapter for tokenviz.

Reads data from JSONL session files and SQLite database.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Optional

from tokenviz.lib.concurrency import pool_map_sync
from tokenviz.lib.db_snapshot import open_db
from tokenviz.lib.jsonl_stream import stream_jsonl
from tokenviz.lib.paths import codex_paths
from tokenviz.types import AdapterResult, DayData


def _find_jsonl_files(directory: str, year_filter: Optional[int]) -> list[str]:
    """Find all .jsonl files under the sessions directory."""
    if not os.path.isdir(directory):
        return []

    files: list[str] = []

    def walk(current: str) -> None:
        try:
            for entry in os.scandir(current):
                if entry.is_dir():
                    walk(entry.path)
                elif entry.name.endswith(".jsonl"):
                    files.append(entry.path)
        except PermissionError:
            pass

    if year_filter:
        year_dir = os.path.join(directory, str(year_filter))
        if os.path.isdir(year_dir):
            walk(year_dir)
    else:
        walk(directory)

    return files


def _date_from_path(file_path: str) -> Optional[str]:
    """Extract date from a session file path like .../sessions/2025/01/15/..."""
    match = re.search(r"sessions[/\\](\d{4})[/\\](\d{2})[/\\](\d{2})[/\\]", file_path)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _as_record(value: object) -> Optional[dict]:
    """Safely cast to dict."""
    return value if isinstance(value, dict) else None


def _normalize_event(raw: object) -> tuple[Optional[str], Optional[dict]]:
    """Normalize event structure."""
    obj = _as_record(raw)
    if not obj:
        return None, None

    payload = _as_record(obj.get("payload"))
    if obj.get("type") == "event_msg" and payload and isinstance(payload.get("type"), str):
        return payload["type"], payload

    event_type = obj.get("type")
    return (event_type if isinstance(event_type, str) else None), payload


def _parse_token_usage(payload: Optional[dict]) -> Optional[dict]:
    """Extract total_token_usage from payload."""
    if not payload:
        return None
    info = _as_record(payload.get("info"))
    return _as_record(info.get("total_token_usage")) if info else None


def _parse_last_token_usage(payload: Optional[dict]) -> Optional[dict]:
    """Extract last_token_usage from payload."""
    if not payload:
        return None
    info = _as_record(payload.get("info"))
    return _as_record(info.get("last_token_usage")) if info else None


def _subtract_usage(current: dict, previous: Optional[dict]) -> dict:
    """Compute delta between two token usage snapshots."""
    if not previous:
        return current
    return {
        "input_tokens": max(0, (current.get("input_tokens", 0) or 0) - (previous.get("input_tokens", 0) or 0)),
        "cached_input_tokens": max(0, (current.get("cached_input_tokens", 0) or 0) - (previous.get("cached_input_tokens", 0) or 0)),
        "cache_read_input_tokens": max(0, (current.get("cache_read_input_tokens", 0) or 0) - (previous.get("cache_read_input_tokens", 0) or 0)),
        "output_tokens": max(0, (current.get("output_tokens", 0) or 0) - (previous.get("output_tokens", 0) or 0)),
        "reasoning_output_tokens": max(0, (current.get("reasoning_output_tokens", 0) or 0) - (previous.get("reasoning_output_tokens", 0) or 0)),
    }


def _parse_timestamp(value: object) -> Optional[datetime]:
    """Parse a timestamp value (string or number) to datetime."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        ms = value * 1000 if value < 1_000_000_000_000 else value
        try:
            return datetime.fromtimestamp(ms / 1000)
        except (ValueError, OSError):
            return None

    if isinstance(value, str):
        value_stripped = value.strip()
        if not value_stripped:
            return None
        try:
            numeric = float(value_stripped)
            ms = numeric * 1000 if numeric < 1_000_000_000_000 else numeric
            return datetime.fromtimestamp(ms / 1000)
        except (ValueError, OSError):
            pass
        try:
            return datetime.fromisoformat(value_stripped.replace("Z", "+00:00"))
        except ValueError:
            return None

    return None


def _parse_session_file(file_path: str) -> dict:
    """Parse a single Codex session JSONL file."""
    previous_totals: Optional[dict] = None
    sum_input = 0
    sum_cached = 0
    sum_output = 0
    model: Optional[str] = None

    def pre_filter(line: str) -> bool:
        return '"token_count"' in line or '"turn_context"' in line

    for raw in stream_jsonl(file_path, pre_filter):
        event_type, payload = _normalize_event(raw)
        if event_type == "token_count":
            total_usage = _parse_token_usage(payload)
            last_usage = _parse_last_token_usage(payload)

            delta: Optional[dict] = None

            if total_usage:
                rolled_back = (
                    previous_totals is not None
                    and (
                        (total_usage.get("input_tokens", 0) or 0) < (previous_totals.get("input_tokens", 0) or 0)
                        or (total_usage.get("cached_input_tokens", 0) or 0) < (previous_totals.get("cached_input_tokens", 0) or 0)
                        or (total_usage.get("output_tokens", 0) or 0) < (previous_totals.get("output_tokens", 0) or 0)
                    )
                )

                if rolled_back:
                    delta = last_usage if last_usage else total_usage
                else:
                    delta = _subtract_usage(total_usage, previous_totals)
                previous_totals = total_usage
            elif last_usage:
                delta = last_usage
                if previous_totals:
                    previous_totals = {
                        k: (previous_totals.get(k, 0) or 0) + (last_usage.get(k, 0) or 0)
                        for k in ("input_tokens", "cached_input_tokens", "cache_read_input_tokens", "output_tokens", "reasoning_output_tokens")
                    }
                else:
                    previous_totals = dict(last_usage)

            if delta:
                sum_input += delta.get("input_tokens", 0) or 0
                sum_cached += (delta.get("cached_input_tokens", 0) or delta.get("cache_read_input_tokens", 0) or 0)
                sum_output += (delta.get("output_tokens", 0) or 0) + (delta.get("reasoning_output_tokens", 0) or 0)

        elif event_type == "turn_context" and payload and isinstance(payload.get("model"), str):
            model = payload["model"]

    return {
        "input_tokens": sum_input,
        "cached_tokens": sum_cached,
        "output_tokens": sum_output,
        "model": model,
    }


class _DayEntry:
    __slots__ = ("input_tokens", "output_tokens", "cache_read_tokens", "sessions", "messages", "models")

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.sessions = 0
        self.messages = 0
        self.models: dict[str, int] = {}


def detect() -> bool:
    """Check if Codex CLI data is available."""
    paths = codex_paths()
    return os.path.isdir(paths.sessions) or os.path.isfile(paths.db)


def load(year_filter: Optional[int] = None) -> Optional[AdapterResult]:
    """Load Codex CLI usage data."""
    paths = codex_paths()
    jsonl_files = _find_jsonl_files(paths.sessions, year_filter)

    day_map: dict[str, _DayEntry] = {}
    hour_counts: dict[str, int] = {}
    model_usage: dict[str, int] = {}
    total_sessions = 0
    total_messages = 0
    first_date: Optional[str] = None
    session_durations: list[float] = []

    if jsonl_files:
        def parse_with_date(fp: str) -> dict:
            date_str = _date_from_path(fp)
            data = _parse_session_file(fp)
            data["date"] = date_str
            return data

        results = pool_map_sync(jsonl_files, parse_with_date)

        for r in results:
            date_str = r.get("date")
            if not date_str:
                continue
            if year_filter and not date_str.startswith(str(year_filter)):
                continue

            total_tokens = r["input_tokens"] + r["cached_tokens"] + r["output_tokens"]
            if total_tokens == 0 and not r["model"]:
                continue

            if date_str not in day_map:
                day_map[date_str] = _DayEntry()
            day = day_map[date_str]
            day.input_tokens += r["input_tokens"]
            day.output_tokens += r["output_tokens"]
            day.cache_read_tokens += r["cached_tokens"]
            day.sessions += 1
            day.messages += 1

            if r["model"]:
                day.models[r["model"]] = day.models.get(r["model"], 0) + total_tokens
                model_usage[r["model"]] = model_usage.get(r["model"], 0) + total_tokens

            total_sessions += 1
            total_messages += 1
            if first_date is None or date_str < first_date:
                first_date = date_str

        # Supplemental: SQLite for hour distribution + session timing
        if os.path.isfile(paths.db):
            try:
                db = open_db(paths.db)
                try:
                    try:
                        result = db.exec("SELECT created_at, updated_at, tokens_used FROM threads")
                    except Exception:
                        result = db.exec("SELECT created_at, last_active_at AS updated_at, tokens_used FROM threads")

                    if result:
                        for row in result[0]["values"]:
                            start = _parse_timestamp(row[0])
                            end = _parse_timestamp(row[1])
                            if start:
                                h = str(start.hour)
                                hour_counts[h] = hour_counts.get(h, 0) + 1
                            if start and end and end.timestamp() > start.timestamp():
                                session_durations.append((end.timestamp() - start.timestamp()))
                finally:
                    db.close()
            except Exception:
                pass

    elif os.path.isfile(paths.db):
        # Fallback: SQLite-only mode
        try:
            db = open_db(paths.db)
            try:
                try:
                    result = db.exec("SELECT created_at, updated_at, tokens_used FROM threads")
                except Exception:
                    result = db.exec("SELECT created_at, last_active_at AS updated_at, tokens_used FROM threads")

                if result:
                    for row in result[0]["values"]:
                        d = _parse_timestamp(row[0])
                        if not d:
                            continue
                        date_str = d.strftime("%Y-%m-%d")
                        if year_filter and not date_str.startswith(str(year_filter)):
                            continue

                        tokens = int(row[2] or 0)
                        if date_str not in day_map:
                            day_map[date_str] = _DayEntry()
                        day = day_map[date_str]
                        day.input_tokens += tokens
                        day.sessions += 1
                        day.messages += 1

                        total_sessions += 1
                        total_messages += 1
                        if first_date is None or date_str < first_date:
                            first_date = date_str

                        h = str(d.hour)
                        hour_counts[h] = hour_counts.get(h, 0) + 1

                        end = _parse_timestamp(row[1])
                        if end and end.timestamp() > d.timestamp():
                            session_durations.append(end.timestamp() - d.timestamp())
            finally:
                db.close()
        except Exception:
            return None
    else:
        return None

    if not day_map:
        return None

    days: list[DayData] = []
    for date_str, data in day_map.items():
        days.append(DayData(
            date=date_str,
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
            cache_read_tokens=data.cache_read_tokens,
            sessions=data.sessions,
            messages=data.messages,
            tool_calls=0,
            models=dict(data.models),
        ))
    days.sort(key=lambda d: d.date)

    avg_session_seconds = (
        sum(session_durations) / len(session_durations) if session_durations else 0
    )

    return AdapterResult(
        tool="codex",
        days=days,
        hour_counts=hour_counts,
        total_sessions=total_sessions,
        total_messages=total_messages,
        first_session_date=first_date,
        model_usage=model_usage,
        avg_session_seconds=avg_session_seconds,
    )
