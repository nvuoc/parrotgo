"""Time validation and Vietnamese appointment normalization utilities."""

import math
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from src.core.state import PickupTimeSlot

NUMBER_WORDS = {
    "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6,
    "bảy": 7, "tám": 8, "chín": 9, "mười": 10, "mười một": 11,
    "mười hai": 12, "mười lăm": 15, "hai mươi": 20, "ba mươi": 30,
}
NUMBER_TOKEN = r"(?:\d{1,3}|mười\s+(?:một|hai|lăm)|hai mươi|ba mươi|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)"


def parse_aware(value: str) -> datetime:
    """Parse ISO timestamp with required timezone offset."""
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Timestamp phải có múi giờ (Timezone offset is required)")
    return dt


def now_iso(timezone_str: str = "Asia/Ho_Chi_Minh") -> str:
    return datetime.now(ZoneInfo(timezone_str)).isoformat()


def valid_coords(coords: Any) -> bool:
    if not isinstance(coords, dict):
        return False
    lat, lng = coords.get("lat"), coords.get("lng")
    return (
        isinstance(lat, (float, int)) and not isinstance(lat, bool)
        and isinstance(lng, (float, int)) and not isinstance(lng, bool)
        and math.isfinite(lat) and math.isfinite(lng)
        and -90 <= lat <= 90 and -180 <= lng <= 180
    )


def _number(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return int(normalized) if normalized.isdigit() else NUMBER_WORDS[normalized]


def _natural_appointment(text: str, ref: datetime) -> Optional[datetime]:
    """Return a complete spoken appointment or None; no guessed date rollover."""
    low = re.sub(r"\s+", " ", text.lower()).strip()
    relative = re.search(rf"\b(?:sau\s+({NUMBER_TOKEN})\s*(phút|tiếng|giờ)|({NUMBER_TOKEN})\s*(phút|tiếng|giờ)\s+nữa)\b", low)
    if relative:
        amount = _number(relative.group(1) or relative.group(3))
        unit = relative.group(2) or relative.group(4)
        if amount <= 0:
            return None
        return ref + (timedelta(minutes=amount) if unit == "phút" else timedelta(hours=amount))
    if re.search(r"\bnửa\s+(?:tiếng|giờ)\b", low):
        return ref + timedelta(minutes=30)

    clock = re.search(r"\b(\d{1,2}):(\d{2})\b", low)
    shorthand = re.search(r"\b(\d{1,2})h(\d{1,2})?\b", low)
    spoken = re.search(rf"\b({NUMBER_TOKEN})\s*(?:giờ|h)\b(?:\s*(rưỡi|{NUMBER_TOKEN})(?:\s*phút)?)?", low)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2))
    elif shorthand:
        hour, minute = int(shorthand.group(1)), int(shorthand.group(2) or 0)
    elif spoken:
        hour = _number(spoken.group(1))
        minute_word = spoken.group(2)
        minute = 30 if minute_word == "rưỡi" else _number(minute_word) if minute_word else 0
    else:
        return None
    if re.search(r"\b(?:chiều|tối)\b", low) and 1 <= hour < 12:
        hour += 12
    elif re.search(r"\b(?:đêm|khuya)\b", low) and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    day = ref.date()
    if re.search(r"\b(?:ngày\s+)?kia\b", low):
        day += timedelta(days=2)
    elif re.search(r"\bmai\b", low):
        day += timedelta(days=1)
    explicit_date = re.search(r"\bngày\s+(\d{1,2})\s*(?:[/.-]|tháng)\s*(\d{1,2})(?:\s*(?:[/.-]|năm)\s*(\d{4}))?\b", low)
    if explicit_date:
        year = int(explicit_date.group(3)) if explicit_date.group(3) else ref.year
        day = ref.date().replace(year=year, month=int(explicit_date.group(2)), day=int(explicit_date.group(1)))
    weekday = re.search(r"\b(?:thứ\s+(hai|ba|tư|năm|sáu|bảy)|chủ nhật)\b", low)
    if weekday and not explicit_date and not re.search(r"\b(?:mai|kia|hôm nay)\b", low):
        index = {"hai": 0, "ba": 1, "tư": 2, "năm": 3, "sáu": 4, "bảy": 5, None: 6}[weekday.group(1)]
        day += timedelta(days=(index - ref.weekday()) % 7)
    return ref.replace(year=day.year, month=day.month, day=day.day, hour=hour, minute=minute, second=0, microsecond=0)


def normalize_pickup_time(value: Any, source_text: Optional[str], received_at: str, timezone: str = "Asia/Ho_Chi_Minh") -> PickupTimeSlot:
    """Anchor relative times once, preserve explicit dates and reject past/invalid times."""
    raw = source_text or (str(value) if value is not None else "")
    result: PickupTimeSlot = {"value": None, "raw": raw or None, "anchored_at": received_at, "status": "needs_clarification"}
    if value is None:
        return result
    try:
        ref = parse_aware(received_at).astimezone(ZoneInfo(timezone))
        text = str(value).strip()
        has_date = bool(re.search(r"\b(?:mai|kia|ngày\s+\d|thứ\s+|chủ nhật)\b", raw.lower()))
        if text == "now" and not has_date:
            return {**result, "value": "now", "status": "extracted"}
        if re.search(r"\b(?:đi ngay|đón ngay|bây giờ)\b", text.lower()) and not has_date:
            return {**result, "value": "now", "status": "extracted"}
        relative = re.fullmatch(r"\+([1-9]\d*)(m|h)", text)
        # Prefer the complete spoken phrase when the model omitted an explicit date.
        natural = _natural_appointment(raw, ref) if raw else None
        if natural is not None:
            dt = natural
        elif has_date:
            # Date mentioned but no reliable clock: ask, never reinterpret as immediate.
            return result
        elif relative:
            amount = int(relative.group(1))
            dt = ref + (timedelta(minutes=amount) if relative.group(2) == "m" else timedelta(hours=amount))
        else:
            natural = _natural_appointment(text, ref)
            dt = natural if natural is not None else parse_aware(text).astimezone(ZoneInfo(timezone))
        if dt <= ref:
            return result
        return {**result, "value": dt.isoformat(), "status": "extracted"}
    except (TypeError, ValueError, OverflowError, KeyError):
        return result


def valid_time(slot: Any, received_at: str) -> bool:
    if not isinstance(slot, dict) or slot.get("status") not in {"extracted", "confirmed"}:
        return False
    val = slot.get("value")
    if val == "now":
        return True
    if not val:
        return False
    try:
        return parse_aware(val) > parse_aware(received_at)
    except (TypeError, ValueError, KeyError):
        return False


def format_pickup_time_display(slot: PickupTimeSlot, timezone: str = "Asia/Ho_Chi_Minh") -> str:
    val = slot.get("value")
    if val == "now":
        return "đón ngay bây giờ"
    if val is None:
        return "thời gian đón chưa xác định"
    try:
        dt = parse_aware(val).astimezone(ZoneInfo(timezone))
        minute = f" {dt.minute} phút" if dt.minute else ""
        return f"đón lúc {dt.hour} giờ{minute}, ngày {dt.day} tháng {dt.month} năm {dt.year}"
    except (TypeError, ValueError, KeyError):
        return "thời gian đón chưa xác định"
