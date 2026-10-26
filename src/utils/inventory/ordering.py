import re
from decimal import Decimal
from typing import Literal

from .models import StoredItem

SortColumn = Literal["id", "article", "brand", "name", "purchase_price", "sale_price", "expiry", "quantity"]


class InventoryOrdering:
    fields = ("id", "article", "brand", "name", "purchase_price", "sale_price", "expiry", "quantity")

    @classmethod
    def apply(cls, items: list[StoredItem], column: SortColumn = "id", descending: bool = False) -> list[StoredItem]:
        if column not in cls.fields:
            raise ValueError("Неизвестный столбец сортировки.")
        populated = [item for item in items if str(getattr(item, column)).strip() not in ("", "—", "-")]
        missing = [item for item in items if str(getattr(item, column)).strip() in ("", "—", "-")]
        return sorted(populated, key=lambda item: cls._key(item, column), reverse=descending) + missing

    @staticmethod
    def _key(item: StoredItem, column: SortColumn) -> tuple[int, Decimal, str]:
        value = str(getattr(item, column))
        if column in ("id", "article", "quantity"):
            return 0, Decimal(value), ""
        if column == "expiry":
            month, year = map(int, value.split("."))
            return 0, Decimal(year * 12 + month), ""
        if column in ("purchase_price", "sale_price"):
            number = re.sub(r"\s*(?:₽|руб\.?|р\.)\s*$", "", value, flags=re.I)
            number = re.sub(r"\s+", "", number).replace(",", ".")
            if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", number):
                return 0, Decimal(number), ""
        return 1, Decimal(0), value.casefold().replace("ё", "е")
