import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class ExpiryInfo:
    expires_on: date
    days_remaining: int
    status: Literal["expired", "soon", "normal"]


def get_expiry_info(expiry: str, *, today: date | None = None) -> ExpiryInfo:
    """A month-only expiry includes its last day; warn within two calendar months."""
    if not re.fullmatch(r"(0[1-9]|1[0-2])\.[0-9]{4}", expiry):
        raise ValueError("Укажите срок годности в формате ММ.ГГГГ.")
    month, year = map(int, expiry.split("."))
    expires_on = date(year, month, calendar.monthrange(year, month)[1])
    current = today if today is not None else datetime.now(ZoneInfo("Europe/Moscow")).date()
    warning_year, warning_month = divmod(current.year * 12 + current.month - 1 + 2, 12)
    warning_month += 1
    warning_day = min(current.day, calendar.monthrange(warning_year, warning_month)[1])
    warning_until = date(warning_year, warning_month, warning_day)
    days_remaining = (expires_on - current).days
    status: Literal["expired", "soon", "normal"] = (
        "expired" if days_remaining < 0 else "soon" if expires_on <= warning_until else "normal"
    )
    return ExpiryInfo(expires_on=expires_on, days_remaining=days_remaining, status=status)
