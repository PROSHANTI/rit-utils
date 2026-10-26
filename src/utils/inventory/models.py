import calendar
import re
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

MOSCOW = ZoneInfo("Europe/Moscow")
COLUMNS = ("№", "Артикул", "Бренд", "Название", "Закупочная стоимость", "Цена продажи", "Срок годности", "Количество")
MAX_QUANTITY = 2**63 - 1


class ExpiryPolicy:
    @staticmethod
    def normalize(value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
            value = f"{value[5:7]}.{value[:4]}"
        if not re.fullmatch(r"(0[1-9]|1[0-2])\.[0-9]{4}", value):
            raise ValueError("Укажите срок годности в формате ММ.ГГГГ или оставьте поле пустым.")
        month, year = map(int, value.split("."))
        date(year, month, 1)
        return value

    @staticmethod
    def status(value: str, today: date | None = None) -> Literal["normal", "soon", "expired"]:
        if not value:
            return "normal"
        month, year = map(int, value.split("."))
        expires = date(year, month, calendar.monthrange(year, month)[1])
        today = today or datetime.now(MOSCOW).date()
        if expires < today:
            return "expired"
        # Six calendar months, including end-of-month and leap-year boundaries.
        warning_year, warning_month = divmod(today.year * 12 + today.month - 1 + 6, 12)
        warning_month += 1
        warning_year = min(warning_year, 9999)
        warning = date(warning_year, warning_month, min(today.day, calendar.monthrange(warning_year, warning_month)[1]))
        return "soon" if expires <= warning else "normal"


class InventoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Decimal digits are stored as text: SQLite integers cannot hold a 64-digit article.
    # This also preserves leading zeros from Excel.
    article: str = Field(default="", max_length=64, pattern=r"^[0-9]*$")
    brand: str = Field(default="", max_length=255)
    name: str = Field(min_length=1, max_length=255)
    purchase_price: str = Field(default="", max_length=255)
    sale_price: str = Field(default="", max_length=255)
    expiry: str = Field(default="", max_length=255)
    quantity: int = Field(default=0, ge=0, le=MAX_QUANTITY)

    @field_validator("quantity", mode="before")
    @classmethod
    def integer_quantity(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Количество должно быть целым неотрицательным числом.")
        return value

    @field_validator("expiry")
    @classmethod
    def normalize_expiry(cls, value: str) -> str:
        return ExpiryPolicy.normalize(value)


class StoredItem(InventoryItem):
    id: int

    @property
    def cells(self) -> tuple[str, ...]:
        return (
            str(self.id),
            self.article,
            self.brand,
            self.name,
            self.purchase_price,
            self.sale_price,
            self.expiry,
            str(self.quantity),
        )

    def view(self, today: date | None = None) -> dict[str, object]:
        return self.model_dump() | {"quantity": str(self.quantity), "expiry_status": ExpiryPolicy.status(self.expiry, today)}


class QuantityChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int | None = Field(default=None, ge=0, le=MAX_QUANTITY)
    delta: Literal[-1, 1] | None = None

    @field_validator("quantity", "delta", mode="before")
    @classmethod
    def reject_boolean(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Укажите целое число.")
        return value
