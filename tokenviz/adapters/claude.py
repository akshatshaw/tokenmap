"""Claude Code adapter for tokenviz.

Reads data from three possible sources:
1. JSONL conversation logs in ~/.claude/projects/
2. stats-cache.json
3. readout-cost-cache.json (fallback)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from tokenviz.lib.concurrency import pool_map_sync
from tokenviz.lib.paths import claude_paths
from tokenviz.types import AdapterResult, DayData, ModelTokenDetail

FILE_CONCURRENCY = int(os.environ.get("BRAGGRID_CONCURRENCY", "32"))


def _find_jsonl_files(directory: str) -> list[str]:
    """Recursively find all .jsonl files in a directory."""
    results: list[str] = []
    if not os.path.isdir(directory):
        return results
    try:
        for root, dirs, files in os.walk(directory):
            for f in files:
                if f.endswith(".jsonl"):
                    results.append(os.path.join(root, f))
    except PermissionError:
        pass
    return results


def _load_json(dirs: list[str], filename: str) -> Optional[dict]:
    """Load a JSON file from the first directory where it exists."""
    for d in dirs:
        fp = os.path.join(d, filename)
        if os.path.isfile(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
    return None


class _DayAccum:
    """Accumulator for a single day's data."""

    __slots__ = (
        "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
        "models", "hours", "sessions", "messages",
    )

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.models: dict[str, int] = {}
        self.hours: dict[int, int] = {}
        self.sessions: set[str] = set()
        self.messages = 0


class _ParsedRecord:
    """A parsed JSONL record ready for accumulation."""

    __slots__ = (
        "date", "input_tokens", "output_tokens", "cache_read_tokens",
        "cache_write_tokens", "model", "hour", "session_id",
    )

    def __init__(
        self, date: str, input_tokens: int, output_tokens: int,
        cache_read_tokens: int, cache_write_tokens: int,
        model: str, hour: int, session_id: Optional[str] = None,
    ) -> None:
        self.date = date
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens
        self.model = model
        self.hour = hour
        self.session_id = session_id


def _extract_hour(timestamp: str) -> int:
    """Extract the local hour from a timestamp string."""
    try:
        d = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return d.astimezone().hour
    except (ValueError, OSError):
        return 0


def _parse_lines(content: str, year_prefix: Optional[str]) -> dict[str, _ParsedRecord]:
    """Parse a JSONL file, keeping only the last streaming snapshot per requestId."""
    last_by_request: dict[str, _ParsedRecord] = {}
    anonymous_records: list[_ParsedRecord] = []

    for line in content.split("\n"):
        if '"usage"' not in line:
            continue

        try:
            record = json.loads(line)
            msg = record.get("message", {})
            usage = msg.get("usage")
            timestamp = record.get("timestamp")
            if not usage or not timestamp:
                continue

            model = msg.get("model")
            if not model or model == "<synthetic>":
                continue

            date_str = timestamp[:10]
            if year_prefix and not date_str.startswith(year_prefix):
                continue

            input_tokens = usage.get("input_tokens", 0) or 0
            cache_write_tokens = usage.get("cache_creation_input_tokens", 0) or 0
            output_tokens = usage.get("output_tokens", 0) or 0
            cache_read_tokens = usage.get("cache_read_input_tokens", 0) or 0

            if input_tokens + cache_write_tokens + output_tokens + cache_read_tokens == 0:
                continue

            parsed = _ParsedRecord(
                date=date_str,
                input_tokens=input_tokens + cache_write_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
                model=model,
                hour=_extract_hour(timestamp),
                session_id=record.get("sessionId"),
            )

            req_id = record.get("requestId", "")
            if req_id:
                last_by_request[req_id] = parsed
            else:
                anonymous_records.append(parsed)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # Combine keyed and anonymous records
    result = dict(last_by_request)
    for i, rec in enumerate(anonymous_records):
        result[f"_anon_{i}"] = rec
    return result


def _accumulate_records(
    records: dict[str, _ParsedRecord],
    day_map: dict[str, _DayAccum],
    seen_requests: set[str],
) -> None:
    """Accumulate parsed records, deduplicating across files."""
    for key, rec in records.items():
        if not key.startswith("_anon_") and key in seen_requests:
            continue
        if not key.startswith("_anon_"):
            seen_requests.add(key)

        entry = day_map.get(rec.date)
        if not entry:
            entry = _DayAccum()
            day_map[rec.date] = entry

        entry.input_tokens += rec.input_tokens
        entry.output_tokens += rec.output_tokens
        entry.cache_read_tokens += rec.cache_read_tokens
        entry.cache_write_tokens += rec.cache_write_tokens

        model_total = rec.input_tokens + rec.cache_read_tokens + rec.output_tokens
        entry.models[rec.model] = entry.models.get(rec.model, 0) + model_total
        entry.messages += 1
        entry.hours[rec.hour] = entry.hours.get(rec.hour, 0) + 1

        if rec.session_id:
            entry.sessions.add(rec.session_id)


def _parse_file(file_path: str, year_prefix: Optional[str]) -> dict[str, _ParsedRecord]:
    """Parse a single JSONL file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return _parse_lines(content, year_prefix)
    except OSError:
        return {}


def _load_from_jsonl(dirs: list[str], year_filter: Optional[int]) -> Optional[AdapterResult]:
    """Load data from JSONL conversation logs."""
    year_prefix = str(year_filter) if year_filter else None

    all_files: list[str] = []
    for d in dirs:
        projects_dir = os.path.join(d, "projects")
        if os.path.isdir(projects_dir):
            all_files.extend(_find_jsonl_files(projects_dir))

    if not all_files:
        return None

    # Parse files concurrently
    file_parsed = pool_map_sync(
        all_files,
        lambda fp: _parse_file(fp, year_prefix),
        FILE_CONCURRENCY,
    )

    # Accumulate into day_map, deduping requestIds across files
    day_map: dict[str, _DayAccum] = {}
    seen_requests: set[str] = set()
    for parsed in file_parsed:
        if parsed:
            _accumulate_records(parsed, day_map, seen_requests)

    if not day_map:
        return None

    days: list[DayData] = []
    hour_counts: dict[str, int] = {}
    model_usage: dict[str, int] = {}
    detailed_model_usage: dict[str, ModelTokenDetail] = {}
    total_sessions = 0
    total_messages = 0
    first_date: Optional[str] = None

    for date_str, entry in day_map.items():
        days.append(DayData(
            date=date_str,
            input_tokens=entry.input_tokens,
            output_tokens=entry.output_tokens,
            cache_read_tokens=entry.cache_read_tokens,
            sessions=len(entry.sessions),
            messages=entry.messages,
            tool_calls=0,
            models=dict(entry.models),
        ))

        total_sessions += len(entry.sessions)
        total_messages += entry.messages
        if first_date is None or date_str < first_date:
            first_date = date_str

        for hour_str, count in entry.hours.items():
            h = str(hour_str)
            hour_counts[h] = hour_counts.get(h, 0) + count
        for model, tokens in entry.models.items():
            model_usage[model] = model_usage.get(model, 0) + tokens

    # Build detailedModelUsage by proportional distribution
    for entry in day_map.values():
        day_total = entry.input_tokens + entry.output_tokens + entry.cache_read_tokens
        if day_total == 0:
            continue
        for model, model_total in entry.models.items():
            ratio = model_total / day_total
            if model not in detailed_model_usage:
                detailed_model_usage[model] = ModelTokenDetail()
            detail = detailed_model_usage[model]
            detail.input_tokens += round((entry.input_tokens - entry.cache_write_tokens) * ratio)
            detail.output_tokens += round(entry.output_tokens * ratio)
            detail.cache_read_tokens += round(entry.cache_read_tokens * ratio)
            detail.cache_write_tokens += round(entry.cache_write_tokens * ratio)

    return AdapterResult(
        tool="claude",
        days=days,
        hour_counts=hour_counts,
        total_sessions=total_sessions,
        total_messages=total_messages,
        first_session_date=first_date,
        model_usage=model_usage,
        detailed_model_usage=detailed_model_usage,
        avg_session_seconds=0,
    )


def _load_from_cache(dirs: list[str], year_filter: Optional[int]) -> Optional[AdapterResult]:
    """Load data from readout-cost-cache.json."""
    cost_cache = _load_json(dirs, "readout-cost-cache.json")
    if not cost_cache:
        return None

    cost_days = cost_cache.get("days")
    if not cost_days or not isinstance(cost_days, dict):
        return None

    days: list[DayData] = []
    model_usage: dict[str, int] = {}
    detailed_model_usage: dict[str, ModelTokenDetail] = {}
    first_date: Optional[str] = None

    for date_str, models in cost_days.items():
        if year_filter and not date_str.startswith(str(year_filter)):
            continue

        input_tokens = 0
        output_tokens = 0
        cache_read_tokens = 0
        day_models: dict[str, int] = {}

        for model_id, usage in models.items():
            inp = usage.get("input", 0) or 0
            out = usage.get("output", 0) or 0
            cache_read = usage.get("cacheRead", 0) or 0
            cache_write = usage.get("cacheWrite", 0) or 0
            input_tokens += inp + cache_write
            output_tokens += out
            cache_read_tokens += cache_read
            model_total = inp + cache_write + cache_read + out
            day_models[model_id] = day_models.get(model_id, 0) + model_total

        days.append(DayData(
            date=date_str, input_tokens=input_tokens, output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens, sessions=0, messages=0,
            tool_calls=0, models=day_models,
        ))
        if first_date is None or date_str < first_date:
            first_date = date_str

        for model, tokens in day_models.items():
            model_usage[model] = model_usage.get(model, 0) + tokens

        for model_id, usage in models.items():
            if model_id not in detailed_model_usage:
                detailed_model_usage[model_id] = ModelTokenDetail()
            detail = detailed_model_usage[model_id]
            detail.input_tokens += usage.get("input", 0) or 0
            detail.output_tokens += usage.get("output", 0) or 0
            detail.cache_read_tokens += usage.get("cacheRead", 0) or 0
            detail.cache_write_tokens += usage.get("cacheWrite", 0) or 0

    if not days:
        return None

    return AdapterResult(
        tool="claude", days=days, hour_counts={},
        total_sessions=0, total_messages=0,
        first_session_date=first_date,
        model_usage=model_usage,
        detailed_model_usage=detailed_model_usage,
        avg_session_seconds=0,
    )


def _load_from_stats_cache(dirs: list[str], year_filter: Optional[int]) -> Optional[AdapterResult]:
    """Load data from stats-cache.json."""
    raw = _load_json(dirs, "stats-cache.json")
    if not raw:
        return None

    stats_cache = raw.get("statsCache")
    if not stats_cache or not isinstance(stats_cache, dict):
        return None

    days: list[DayData] = []
    model_usage: dict[str, int] = {}
    detailed_model_usage: dict[str, ModelTokenDetail] = {}
    first_date: Optional[str] = None

    for date_str, entry in stats_cache.items():
        if year_filter and not date_str.startswith(str(year_filter)):
            continue
        models_data = entry.get("models")
        if not models_data:
            continue

        input_tokens = 0
        output_tokens = 0
        cache_read_tokens = 0
        day_models: dict[str, int] = {}

        for model_id, usage in models_data.items():
            inp = (usage.get("inputTokens", 0) or 0) + (usage.get("cacheCreationTokens", 0) or 0)
            out = usage.get("outputTokens", 0) or 0
            cache_read = usage.get("cacheReadTokens", 0) or 0
            input_tokens += inp
            output_tokens += out
            cache_read_tokens += cache_read
            model_total = inp + cache_read + out
            day_models[model_id] = day_models.get(model_id, 0) + model_total

            if model_id not in detailed_model_usage:
                detailed_model_usage[model_id] = ModelTokenDetail()
            detail = detailed_model_usage[model_id]
            detail.input_tokens += usage.get("inputTokens", 0) or 0
            detail.output_tokens += out
            detail.cache_read_tokens += cache_read
            detail.cache_write_tokens += usage.get("cacheCreationTokens", 0) or 0

        if input_tokens + output_tokens + cache_read_tokens == 0:
            continue

        days.append(DayData(
            date=date_str, input_tokens=input_tokens, output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens, sessions=0, messages=0,
            tool_calls=0, models=day_models,
        ))
        if first_date is None or date_str < first_date:
            first_date = date_str

        for model, tokens in day_models.items():
            model_usage[model] = model_usage.get(model, 0) + tokens

    if not days:
        return None

    return AdapterResult(
        tool="claude", days=days, hour_counts={},
        total_sessions=0, total_messages=0,
        first_session_date=first_date,
        model_usage=model_usage,
        detailed_model_usage=detailed_model_usage,
        avg_session_seconds=0,
    )


def _enrich_from_stats_cache(result: AdapterResult, dirs: list[str]) -> None:
    """Enrich detailedModelUsage from stats-cache.json's top-level modelUsage."""
    raw = _load_json(dirs, "stats-cache.json")
    if not raw:
        return

    model_usage = raw.get("modelUsage")
    if not model_usage or not isinstance(model_usage, dict):
        return

    enriched: dict[str, ModelTokenDetail] = {}
    for model, usage in model_usage.items():
        enriched[model] = ModelTokenDetail(
            input_tokens=usage.get("inputTokens", 0) or 0,
            output_tokens=usage.get("outputTokens", 0) or 0,
            cache_read_tokens=usage.get("cacheReadInputTokens", 0) or 0,
            cache_write_tokens=usage.get("cacheCreationInputTokens", 0) or 0,
        )

    if enriched:
        result.detailed_model_usage = enriched


def detect() -> bool:
    """Check if Claude Code data is available."""
    dirs = claude_paths()
    return any(
        os.path.isdir(os.path.join(d, "projects"))
        or os.path.isfile(os.path.join(d, "stats-cache.json"))
        or os.path.isfile(os.path.join(d, "readout-cost-cache.json"))
        for d in dirs
    )


def load(year_filter: Optional[int] = None) -> Optional[AdapterResult]:
    """Load Claude Code usage data."""
    dirs = claude_paths()
    if not dirs:
        return None

    jsonl_result = _load_from_jsonl(dirs, year_filter)
    if jsonl_result:
        _enrich_from_stats_cache(jsonl_result, dirs)
        return jsonl_result

    stats_cache_result = _load_from_stats_cache(dirs, year_filter)
    if stats_cache_result:
        return stats_cache_result

    return _load_from_cache(dirs, year_filter)
