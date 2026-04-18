"""OpenCode adapter for tokenmap."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from tokenmap.lib.concurrency import pool_map_sync
from tokenmap.lib.db_snapshot import open_db
from tokenmap.lib.paths import opencode_paths
from tokenmap.types import AdapterResult, DayData

MAX_BYTES = int(os.environ.get("BRAGGRID_MAX_RECORD_BYTES", "67108864"))


class _ParsedMessage:
    __slots__ = ("id", "input_tokens", "output_tokens", "cache_read_tokens",
                 "cache_write_tokens", "model", "timestamp")

    def __init__(self) -> None:
        self.id: Optional[str] = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.model: Optional[str] = None
        self.timestamp: Optional[float] = None


def _parse_message_data(data: dict) -> Optional[_ParsedMessage]:
    if not data:
        return None
    tokens = data.get("tokens", {}) or {}
    inp = int(tokens.get("input", 0) or 0)
    out = int(tokens.get("output", 0) or 0)
    cache = tokens.get("cache", {}) or {}
    cr = int(cache.get("read", 0) or 0)
    cw = int(cache.get("write", 0) or 0)
    if inp + out + cr + cw == 0:
        return None
    msg = _ParsedMessage()
    msg.input_tokens = inp
    msg.output_tokens = out
    msg.cache_read_tokens = cr
    msg.cache_write_tokens = cw
    msg.model = data.get("modelID") or None
    time_info = data.get("time", {}) or {}
    created = time_info.get("created")
    msg.timestamp = float(created) if created else None
    return msg


def _load_from_db(db_path: str) -> list[_ParsedMessage]:
    db = open_db(db_path)
    messages: list[_ParsedMessage] = []
    try:
        result = db.exec("SELECT id, data FROM message ORDER BY time_created ASC")
        if not result:
            return messages
        seen_ids: set[str] = set()
        for row in result[0]["values"]:
            msg_id = row[0]
            raw_data = row[1]
            if not raw_data:
                continue
            if msg_id and str(msg_id) in seen_ids:
                continue
            raw = str(raw_data)
            if len(raw.encode("utf-8")) > MAX_BYTES:
                continue
            try:
                data = json.loads(raw)
                parsed = _parse_message_data(data)
                if parsed:
                    parsed.id = str(msg_id) if msg_id else None
                    messages.append(parsed)
                    if msg_id:
                        seen_ids.add(str(msg_id))
            except (json.JSONDecodeError, TypeError):
                pass
    finally:
        db.close()
    return messages


def _load_from_files(messages_dir: str) -> list[_ParsedMessage]:
    if not os.path.isdir(messages_dir):
        return []
    files: list[str] = []
    for root, _dirs, filenames in os.walk(messages_dir):
        for f in filenames:
            if f.endswith(".json"):
                files.append(os.path.join(root, f))

    def parse_file(fp: str) -> Optional[_ParsedMessage]:
        try:
            if os.path.getsize(fp) > MAX_BYTES:
                return None
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _parse_message_data(data)
        except (json.JSONDecodeError, OSError):
            return None

    results = pool_map_sync(files, parse_file)
    return [r for r in results if r is not None]


def _load_session_timing(sessions_dir: str) -> tuple[list[float], Optional[str]]:
    durations: list[float] = []
    first_date: Optional[str] = None
    if not os.path.isdir(sessions_dir):
        return durations, first_date
    for root, _dirs, filenames in os.walk(sessions_dir):
        for f in filenames:
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                time_info = data.get("time", {}) or {}
                created = time_info.get("created")
                updated = time_info.get("updated")
                if created:
                    d = datetime.fromtimestamp(float(created))
                    ds = d.strftime("%Y-%m-%d")
                    if first_date is None or ds < first_date:
                        first_date = ds
                    if updated:
                        end = datetime.fromtimestamp(float(updated))
                        dur = end.timestamp() - d.timestamp()
                        if dur > 0:
                            durations.append(dur)
            except (json.JSONDecodeError, OSError, ValueError, TypeError):
                pass
    return durations, first_date


def detect() -> bool:
    paths = opencode_paths()
    return os.path.isfile(paths.db) or os.path.isdir(paths.messages)


def load(year_filter: Optional[int] = None) -> Optional[AdapterResult]:
    paths = opencode_paths()
    messages: list[_ParsedMessage] = []
    if os.path.isfile(paths.db):
        try:
            messages = _load_from_db(paths.db)
        except Exception:
            messages = _load_from_files(paths.messages)
    else:
        messages = _load_from_files(paths.messages)

    if not messages:
        return None

    day_map: dict[str, dict] = {}
    hour_counts: dict[str, int] = {}
    model_usage: dict[str, int] = {}
    total_messages = 0
    seen: set[str] = set()

    for msg in messages:
        if msg.id and msg.id in seen:
            continue
        if msg.id:
            seen.add(msg.id)
        if msg.timestamp is None:
            continue
        try:
            d = datetime.fromtimestamp(msg.timestamp)
        except (ValueError, OSError):
            continue
        date_str = d.strftime("%Y-%m-%d")
        if year_filter and not date_str.startswith(str(year_filter)):
            continue
        if date_str not in day_map:
            day_map[date_str] = {"inp": 0, "out": 0, "cr": 0, "msgs": 0, "models": {}}
        day = day_map[date_str]
        day["inp"] += msg.input_tokens
        day["out"] += msg.output_tokens
        day["cr"] += msg.cache_read_tokens
        day["msgs"] += 1
        total_messages += 1
        if msg.model:
            ttl = msg.input_tokens + msg.output_tokens + msg.cache_read_tokens
            day["models"][msg.model] = day["models"].get(msg.model, 0) + ttl
            model_usage[msg.model] = model_usage.get(msg.model, 0) + ttl
        h = str(d.hour)
        hour_counts[h] = hour_counts.get(h, 0) + 1

    if not day_map:
        return None

    durations, session_first = _load_session_timing(paths.sessions)
    first_date: Optional[str] = min(day_map.keys())
    if session_first and (first_date is None or session_first < first_date):
        first_date = session_first

    days = sorted([
        DayData(date=ds, input_tokens=v["inp"], output_tokens=v["out"],
                cache_read_tokens=v["cr"], sessions=1, messages=v["msgs"],
                tool_calls=0, models=dict(v["models"]))
        for ds, v in day_map.items()
    ], key=lambda x: x.date)

    avg_ss = sum(durations) / len(durations) if durations else 0
    return AdapterResult(
        tool="opencode", days=days, hour_counts=hour_counts,
        total_sessions=len(day_map), total_messages=total_messages,
        first_session_date=first_date, model_usage=model_usage,
        avg_session_seconds=avg_ss,
    )
