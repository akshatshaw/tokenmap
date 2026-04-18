"""Statistics computation for tokenviz."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from tokenviz.types import AggregatedData, Stats

WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def format_tokens(n: int) -> str:
    """Format a token count for human display (e.g. 1.5M, 200K)."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _format_hour(hour: int) -> str:
    """Format an hour (0-23) as 12-hour time string."""
    if hour == 0:
        return "12:00 AM"
    if hour == 12:
        return "12:00 PM"
    if hour < 12:
        return f"{hour}:00 AM"
    return f"{hour - 12}:00 PM"


def _compute_streaks(active_dates: set[str]) -> tuple[int, int]:
    """Compute current and longest streaks from a set of date strings.

    Returns:
        Tuple of (current_streak, longest_streak).
    """
    if not active_dates:
        return 0, 0

    # Current streak: count backward from today
    today = date.today()
    current_streak = 0
    for i in range(366 * 5):  # up to 5 years back
        d = today - timedelta(days=i)
        date_str = d.isoformat()
        if date_str in active_dates:
            current_streak += 1
        else:
            break

    # Longest streak: sort all dates and scan for max consecutive run
    sorted_dates = sorted(active_dates)
    longest_streak = 1
    run = 1
    for i in range(1, len(sorted_dates)):
        try:
            prev = date.fromisoformat(sorted_dates[i - 1])
            curr = date.fromisoformat(sorted_dates[i])
            diff_days = (curr - prev).days
            if diff_days == 1:
                run += 1
                if run > longest_streak:
                    longest_streak = run
            else:
                run = 1
        except ValueError:
            run = 1

    return current_streak, longest_streak


def compute_stats(data: AggregatedData) -> Stats:
    """Compute statistics from aggregated data."""
    days = data.days
    hour_counts = data.hour_counts
    total_sessions = data.total_sessions
    total_messages = data.total_messages
    avg_session_seconds = data.avg_session_seconds

    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    dow_counts = [0] * 7
    active_dates: set[str] = set()

    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)
    recent_cutoff = thirty_days_ago.strftime("%Y-%m-%d")
    all_time_model_tokens: dict[str, int] = {}
    recent_model_tokens: dict[str, int] = {}

    for day in days:
        input_tokens += day.input_tokens or 0
        output_tokens += day.output_tokens or 0
        cache_read_tokens += day.cache_read_tokens or 0

        day_total = (day.input_tokens or 0) + (day.output_tokens or 0)
        if day_total > 0:
            active_dates.add(day.date)

        try:
            d = datetime.strptime(day.date, "%Y-%m-%d")
            dow_counts[d.weekday()] += day_total
            # Python weekday: Mon=0..Sun=6
            # JS getDay: Sun=0..Sat=6
            # We'll store Python-style but convert for compatibility: keep as JS-style
            # Actually, let's match JS behavior for consistency in the array:
            # JS: [Sun, Mon, Tue, Wed, Thu, Fri, Sat]
            js_dow = (d.weekday() + 1) % 7  # Convert: Mon(0)->1, Sun(6)->0
            dow_counts_js = dow_counts  # We'll rebuild below
        except ValueError:
            pass

        if day.models:
            for model, tokens in day.models.items():
                all_time_model_tokens[model] = all_time_model_tokens.get(model, 0) + tokens
                if day.date >= recent_cutoff:
                    recent_model_tokens[model] = recent_model_tokens.get(model, 0) + tokens

    # Rebuild dow_counts in JS order: [Sun, Mon, Tue, Wed, Thu, Fri, Sat]
    dow_counts_js = [0] * 7
    for day in days:
        day_total = (day.input_tokens or 0) + (day.output_tokens or 0)
        try:
            d = datetime.strptime(day.date, "%Y-%m-%d")
            js_dow = (d.weekday() + 1) % 7
            dow_counts_js[js_dow] += day_total
        except ValueError:
            pass

    effective_input = input_tokens + cache_read_tokens
    total_tokens = effective_input + output_tokens

    # Compute most used model from daily data
    most_used_model: dict[str, object] | None = None
    for name, tokens in all_time_model_tokens.items():
        if tokens > 0 and (most_used_model is None or tokens > most_used_model["tokens"]):  # type: ignore[operator]
            most_used_model = {"name": name, "tokens": tokens}

    recent_model: dict[str, object] | None = None
    for name, tokens in recent_model_tokens.items():
        if tokens > 0 and (recent_model is None or tokens > recent_model["tokens"]):  # type: ignore[operator]
            recent_model = {"name": name, "tokens": tokens}

    current_streak, longest_streak = _compute_streaks(active_dates)

    peak_hour: dict[str, object] | None = None
    if hour_counts:
        for hour_str, count in hour_counts.items():
            if count > 0:
                if peak_hour is None or count > peak_hour["count"]:  # type: ignore[operator]
                    peak_hour = {"hour": _format_hour(int(hour_str)), "count": count}

    max_dow = max(dow_counts_js) if dow_counts_js else 0
    busiest_day: str | None = None
    if max_dow > 0:
        busiest_day_idx = dow_counts_js.index(max_dow)
        busiest_day = WEEKDAY_NAMES[busiest_day_idx]

    avg_session_minutes = round(avg_session_seconds / 60) if avg_session_seconds else 0

    return Stats(
        input_tokens=effective_input,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        total_tokens=total_tokens,
        most_used_model=most_used_model,
        recent_model=recent_model,
        current_streak=current_streak,
        longest_streak=longest_streak,
        total_sessions=total_sessions,
        total_messages=total_messages,
        peak_hour=peak_hour,
        busiest_day=busiest_day,
        dow_counts=dow_counts_js,
        avg_session_minutes=avg_session_minutes,
    )
