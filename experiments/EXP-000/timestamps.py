"""Timestamp normalisation. Keeps the raw string always; never raises on bad input."""

from __future__ import annotations

from datetime import date, datetime

#: Tried in order after ISO 8601. Day-first before month-first, since the data is Indian.
COMMON_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
    "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M", "%d/%m/%y",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M %p",
    "%d/%m/%y %I:%M:%S %p", "%d/%m/%y %I:%M %p",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
)


def parse(value, *, date_format: str | None = None) -> tuple[str | None, str]:
    """Return (ISO 8601 or None, raw string).

    A datetime or date arrives already parsed from XLSX. Everything else is tried as ISO, then
    `date_format` if the operator gave one, then the common formats. An unparseable value yields
    None and is counted in the summary, so a format problem is visible rather than silent.
    """
    if value is None:
        return None, ""
    if isinstance(value, datetime):
        return value.isoformat(), value.isoformat()
    if isinstance(value, date):
        return value.isoformat(), value.isoformat()

    raw = str(value).strip()
    if not raw:
        return None, ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat(), raw
    except ValueError:
        pass
    candidates = ((date_format,) if date_format else ()) + COMMON_FORMATS
    for fmt in candidates:
        try:
            return datetime.strptime(raw, fmt).isoformat(), raw
        except ValueError:
            continue
    return None, raw
