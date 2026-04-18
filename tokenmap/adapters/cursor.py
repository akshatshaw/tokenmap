"""Cursor adapter for tokenmap.

Reads data from Cursor's API (via access token) or local SQLite state DB.
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Optional

from tokenmap.lib.db_snapshot import open_db
from tokenmap.lib.debug import debug
from tokenmap.lib.paths import cursor_state_paths
from tokenmap.types import AdapterResult, DayData


def detect() -> bool:
    return len(cursor_state_paths()) > 0


def _decode_jwt_payload(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1].replace("-", "+").replace("_", "/")
        # Add padding
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.b64decode(payload).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return None


def _extract_access_token(db_path: str) -> Optional[str]:
    try:
        debug(f"cursor: opening DB {db_path}")
        db = open_db(db_path)
        try:
            result = db.exec(
                "SELECT value FROM ItemTable WHERE key = 'cursorAuth/accessToken'"
            )
            if result and result[0]["values"]:
                token = result[0]["values"][0][0]
                token = str(token) if token else None
                debug(f"cursor: access token {'found' if token else 'is empty'}")
                return token
            debug("cursor: no access token row found")
            return None
        finally:
            db.close()
    except Exception as e:
        debug(f"cursor: failed to read access token: {e}")
        return None


def _fetch_usage_csv(access_token: str) -> Optional[str]:
    """Fetch usage CSV from Cursor API."""
    try:
        import httpx
    except ImportError:
        debug("cursor: httpx not installed, skipping API fetch")
        return None

    url = "https://cursor.com/api/dashboard/export-usage-events-csv?strategy=tokens"
    jwt_payload = _decode_jwt_payload(access_token)
    sub = jwt_payload.get("sub", "").strip() if jwt_payload else None

    cookie_values = [access_token]
    if sub:
        cookie_values.append(f"{sub}::{access_token}")

    strategies: list[tuple[str, dict[str, str]]] = []
    seen: set[str] = set()

    def add(label: str, headers: dict[str, str]) -> None:
        key = json.dumps(headers, sort_keys=True)
        if key in seen:
            return
        seen.add(key)
        strategies.append((label, headers))

    add("bearer", {"Authorization": f"Bearer {access_token}"})
    for cv in cookie_values:
        add("cookie", {"Cookie": f"WorkosCursorSessionToken={cv}"})
        from urllib.parse import quote
        add("cookie-encoded", {"Cookie": f"WorkosCursorSessionToken={quote(cv)}"})
        add("bearer+cookie", {
            "Authorization": f"Bearer {access_token}",
            "Cookie": f"WorkosCursorSessionToken={cv}",
        })
        add("bearer+cookie-encoded", {
            "Authorization": f"Bearer {access_token}",
            "Cookie": f"WorkosCursorSessionToken={quote(cv)}",
        })

    debug(f"cursor: trying {len(strategies)} auth strategies")
    for label, headers in strategies:
        try:
            debug(f"cursor: trying strategy '{label}'")
            with httpx.Client(timeout=10) as client:
                resp = client.get(url, headers={**headers, "Accept": "text/csv"})
            debug(f"cursor: strategy '{label}' -> HTTP {resp.status_code}")
            if resp.is_success:
                text = resp.text
                first_line = text.split("\n")[0] if text else ""
                has_comma = "," in first_line
                has_known = bool(re.search(
                    r"\b(Date|Model|Tokens|Total Tokens|Output Tokens)\b",
                    first_line,
                ))
                if has_comma and has_known:
                    line_count = len([l for l in text.split("\n") if l.strip()])
                    debug(f"cursor: API returned valid CSV ({line_count} lines)")
                    return text
                debug(f"cursor: response is not valid CSV")
        except Exception as e:
            debug(f"cursor: strategy '{label}' failed: {e}")

    debug("cursor: all API strategies failed")
    return None


def _parse_csv_line(line: str) -> list[str]:
    fields: list[str] = []
    current = ""
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            if in_quotes and i + 1 < len(line) and line[i + 1] == '"':
                current += '"'
                continue
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            fields.append(current.strip())
            current = ""
        else:
            current += ch
    fields.append(current.strip())
    return fields


class _DayEntry:
    __slots__ = ("inp", "out", "cr", "sessions", "messages", "models")

    def __init__(self) -> None:
        self.inp = 0
        self.out = 0
        self.cr = 0
        self.sessions = 0
        self.messages = 0
        self.models: dict[str, int] = {}


def _parse_csv(csv: str, year_filter: Optional[int]) -> tuple[list[DayData], dict[str, int], dict[str, int]]:
    lines = csv.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [l for l in lines if l.strip()]
    if len(lines) < 2:
        return [], {}, {}

    header = _parse_csv_line(lines[0])
    col = {name: idx for idx, name in enumerate(header)}

    day_map: dict[str, _DayEntry] = {}
    model_usage: dict[str, int] = {}

    for i in range(1, len(lines)):
        cols = _parse_csv_line(lines[i])
        if len(cols) < len(header):
            continue
        raw_date = cols[col.get("Date", -1)] if "Date" in col else ""
        if not raw_date:
            continue
        date_str = raw_date[:10]
        if year_filter and not date_str.startswith(str(year_filter)):
            continue

        raw_model = cols[col.get("Model", -1)] if "Model" in col else "unknown"
        raw_model = re.sub(r"^(?:[a-z]{2}\.)?(?:anthropic|amazon|google|meta|mistral|openai)\.", "", raw_model, flags=re.I)
        raw_model = re.sub(r"-\d{8}$", "", raw_model)
        raw_model = re.sub(r"-v\d+:\d+$", "", raw_model)

        def num(key: str) -> int:
            idx = col.get(key, -1)
            return int(cols[idx] or "0") if idx >= 0 and idx < len(cols) else 0

        inp = num("Input (w/o Cache Write)") or num("Input (w/ Cache Write)")
        out = num("Output Tokens")
        cr = num("Cache Read")

        if inp == 0 and out == 0 and "Tokens" in col:
            total = num("Tokens")
            inp = round(total * 0.7)
            out = round(total * 0.3)

        raw_total = num("Total Tokens")
        total_tokens = raw_total if raw_total > 0 else (inp + out + cr)

        if date_str not in day_map:
            day_map[date_str] = _DayEntry()
        day = day_map[date_str]
        day.inp += inp
        day.out += out
        day.cr += cr
        day.messages += 1
        day.models[raw_model] = day.models.get(raw_model, 0) + total_tokens
        model_usage[raw_model] = model_usage.get(raw_model, 0) + total_tokens

    for day in day_map.values():
        day.sessions = 1

    days = sorted([
        DayData(date=ds, input_tokens=v.inp, output_tokens=v.out,
                cache_read_tokens=v.cr, sessions=v.sessions, messages=v.messages,
                tool_calls=0, models=dict(v.models))
        for ds, v in day_map.items()
    ], key=lambda x: x.date)

    return days, model_usage, {}


def _load_local_stats(db_path: str, year_filter: Optional[int]) -> Optional[tuple[list[DayData], dict[str, int]]]:
    try:
        debug(f"cursor: loading local stats from {db_path}")
        db = open_db(db_path)
        try:
            result = db.exec(
                "SELECT key, value FROM ItemTable WHERE key LIKE 'aiCodeTracking.dailyStats.v1.5.%'"
            )
            if not result or not result[0]["values"]:
                debug("cursor: no local dailyStats rows found")
                return None
            debug(f"cursor: found {len(result[0]['values'])} local dailyStats rows")

            days: list[DayData] = []
            for row in result[0]["values"]:
                value = row[1]
                if not value:
                    continue
                try:
                    data = json.loads(str(value))
                    date_str = data.get("date")
                    if not date_str:
                        continue
                    if year_filter and not date_str.startswith(str(year_filter)):
                        continue
                    total_lines = (data.get("tabAcceptedLines", 0) or 0) + (data.get("composerAcceptedLines", 0) or 0)
                    pseudo_tokens = total_lines * 50
                    days.append(DayData(
                        date=date_str,
                        input_tokens=round(pseudo_tokens * 0.7),
                        output_tokens=round(pseudo_tokens * 0.3),
                        cache_read_tokens=0, sessions=1,
                        messages=1 if total_lines > 0 else 0,
                        tool_calls=0, models={},
                    ))
                except (json.JSONDecodeError, TypeError):
                    pass

            days.sort(key=lambda d: d.date)
            debug(f"cursor: local stats produced {len(days)} days")
            return days, {}
        finally:
            db.close()
    except Exception as e:
        debug(f"cursor: loadLocalStats failed: {e}")
        return None


def _load_hourly_distribution() -> dict[str, int]:
    from pathlib import Path
    db_path = str(Path.home() / ".cursor" / "ai-tracking" / "ai-code-tracking.db")
    if not os.path.isfile(db_path):
        debug(f"cursor: hourly DB not found at {db_path}")
        return {}
    try:
        db = open_db(db_path)
        try:
            result = db.exec(
                "SELECT CAST(strftime('%H', datetime(timestamp / 1000, 'unixepoch', 'localtime')) AS INTEGER) AS hour, "
                "COUNT(*) AS cnt FROM ai_code_hashes GROUP BY hour"
            )
            hour_counts: dict[str, int] = {}
            if result:
                for row in result[0]["values"]:
                    hour_counts[str(row[0])] = int(row[1])
            return hour_counts
        finally:
            db.close()
    except Exception as e:
        debug(f"cursor: loadHourlyDistribution failed: {e}")
        return {}


def load(year_filter: Optional[int] = None) -> Optional[AdapterResult]:
    db_paths = cursor_state_paths()
    debug(f"cursor: state DB paths: {db_paths if db_paths else '(none found)'}")
    if not db_paths:
        return None

    days: list[DayData] = []
    model_usage: dict[str, int] = {}
    hour_counts: dict[str, int] = {}
    used_api = False

    for db_path in db_paths:
        token = _extract_access_token(db_path)
        if not token:
            continue
        csv = _fetch_usage_csv(token)
        if csv:
            days, model_usage, hour_counts = _parse_csv(csv, year_filter)
            used_api = True
            break

    if not used_api or not days:
        for db_path in db_paths:
            local = _load_local_stats(db_path, year_filter)
            if local and local[0]:
                days, model_usage = local
                break

    if not days:
        return None

    supplemental = _load_hourly_distribution()
    hour_counts = {**supplemental, **hour_counts}

    total_sessions = sum(d.sessions for d in days)
    total_messages = sum(d.messages for d in days)
    first_date = min(d.date for d in days) if days else None

    return AdapterResult(
        tool="cursor", days=days, hour_counts=hour_counts,
        total_sessions=total_sessions, total_messages=total_messages,
        first_session_date=first_date, model_usage=model_usage,
        avg_session_seconds=0,
    )
