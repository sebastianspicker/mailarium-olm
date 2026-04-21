"""Temporal email analysis using pandas."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from .email_db import EmailDatabase

logger = logging.getLogger(__name__)


def _resolve_zoneinfo_name(candidate: str) -> str | None:
    """Return *candidate* if it resolves to a valid IANA timezone."""
    normalized = candidate.removeprefix(":")
    if not normalized:
        return None
    try:
        ZoneInfo(normalized)
        return normalized
    except ZoneInfoNotFoundError:
        return None


def _system_zoneinfo_name() -> str | None:
    """Best-effort detection of the local IANA timezone name."""
    env_tz = os.getenv("TZ")
    if env_tz:
        resolved = _resolve_zoneinfo_name(env_tz)
        if resolved is not None:
            return resolved

    try:
        localtime_path = Path("/etc/localtime").resolve()
    except OSError:
        return None

    parts = localtime_path.parts
    if "zoneinfo" not in parts:
        return None

    zone_name = "/".join(parts[parts.index("zoneinfo") + 1 :])
    return _resolve_zoneinfo_name(zone_name)


def _local_display_timezone() -> tzinfo:
    """Return the system display timezone, falling back to UTC."""
    zone_name = _system_zoneinfo_name()
    if zone_name is not None:
        return ZoneInfo(zone_name)
    return datetime.now().astimezone().tzinfo or UTC


def _resolve_display_timezone(display_timezone: str | tzinfo | None) -> tzinfo:
    """Resolve the configured analytics display timezone."""
    if display_timezone is None:
        from .config import get_settings

        display_timezone = get_settings().analytics_timezone

    if isinstance(display_timezone, str):
        if display_timezone.lower() == "local":
            return _local_display_timezone()
        try:
            return ZoneInfo(display_timezone)
        except ZoneInfoNotFoundError:
            logger.warning("Unknown ANALYTICS_TIMEZONE %r; falling back to local timezone", display_timezone)
            return _local_display_timezone()

    return display_timezone


class TemporalAnalyzer:
    """Time-based analysis of email patterns."""

    def __init__(self, email_db: EmailDatabase, *, display_timezone: str | tzinfo | None = None) -> None:
        self._db = email_db
        self._display_timezone = _resolve_display_timezone(display_timezone)

    def _normalized_dates(self, dates: list[str]):
        """Convert stored dates into the configured analytics display timezone."""
        import pandas as pd

        dt_series = pd.to_datetime(dates, errors="coerce", utc=True).dropna()
        if dt_series.empty:
            return dt_series
        localized = dt_series.tz_convert(self._display_timezone)
        return localized.tz_localize(None)

    def volume_over_time(
        self,
        period: str = "day",
        date_from: str | None = None,
        date_to: str | None = None,
        sender: str | None = None,
    ) -> list[dict[str, Any]]:
        """Email volume grouped by time period."""
        try:
            import pandas as pd
        except ImportError:
            return [{"error": "pandas not installed. Run: pip install pandas"}]

        dates = self._db.email_dates(sender=sender)
        if not dates:
            return []

        dt_series = self._normalized_dates(dates)
        if dt_series.empty:
            return []

        df = pd.DataFrame({"date": dt_series})
        if date_from:
            df = df[df["date"] >= pd.Timestamp(date_from[:10])]
        if date_to:
            df = df[df["date"] < (pd.Timestamp(date_to[:10]) + pd.Timedelta(days=1))]
        if df.empty:
            return []

        # W-SUN = weeks ending on Sunday = starting Monday (ISO 8601)
        freq_map = {"day": "D", "week": "W-SUN", "month": "M"}
        freq = freq_map.get(period, "D")

        grouped = df.groupby(df["date"].dt.to_period(freq)).size()
        return [{"period": str(p), "count": int(c)} for p, c in grouped.items()]

    def activity_heatmap(self) -> list[dict[str, int]]:
        """Hour-of-day x day-of-week email counts."""
        try:
            import pandas as pd
        except ImportError:
            return [{"error": "pandas not installed. Run: pip install pandas"}]

        dates = self._db.email_dates()
        if not dates:
            return []

        dt_series = self._normalized_dates(dates)
        if dt_series.empty:
            return []

        df = pd.DataFrame({"date": dt_series})
        df["hour"] = df["date"].dt.hour
        df["day_of_week"] = df["date"].dt.dayofweek  # 0=Mon..6=Sun

        grouped = df.groupby(["day_of_week", "hour"]).size().reset_index(name="count")
        return [
            {"day_of_week": int(row["day_of_week"]), "hour": int(row["hour"]), "count": int(row["count"])}
            for _, row in grouped.iterrows()
        ]

    def response_times(self, sender: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Average response times per replier (in hours)."""
        pairs = self._db.response_pairs(sender=sender, limit=500)
        if not pairs:
            return []

        sender_times: dict[str, list[float]] = {}
        for pair in pairs:
            try:
                reply_dt = datetime.fromisoformat(pair["reply_date"])
                orig_dt = datetime.fromisoformat(pair["original_date"])
                # Normalize both to UTC to avoid naive/aware mismatch
                if reply_dt.tzinfo is not None:
                    reply_dt = reply_dt.astimezone(UTC).replace(tzinfo=None)
                else:
                    reply_dt = reply_dt.replace(tzinfo=None)
                if orig_dt.tzinfo is not None:
                    orig_dt = orig_dt.astimezone(UTC).replace(tzinfo=None)
                else:
                    orig_dt = orig_dt.replace(tzinfo=None)
                hours = (reply_dt - orig_dt).total_seconds() / 3600
                if hours < 0:
                    continue
                reply_sender = pair["reply_sender"]
                sender_times.setdefault(reply_sender, []).append(hours)
            except (ValueError, TypeError):
                continue

        result = []
        for email, times in sender_times.items():
            if times:
                avg = sum(times) / len(times)
                result.append(
                    {
                        "replier": email,
                        "avg_response_hours": round(avg, 1),
                        "response_count": len(times),
                    }
                )

        result.sort(key=lambda x: x["response_count"], reverse=True)
        return result[:limit]
