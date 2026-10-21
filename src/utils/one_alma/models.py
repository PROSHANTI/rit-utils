import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

COLUMNS = (
    "№",
    "Артикул",
    "Наименование препарата",
    "Объём",
    "Годен до",
    "Цена по ЦБ РФ на 27.05, ₽",
    "Оптовая цена Emansi, ₽",
    "Средняя цена в магазинах, ₽",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class NewProduct:
    position: int
    article: str
    name: str
    volume: str
    expiry: str
    central_bank_price: str
    wholesale_price: str
    market_price: str
    quantity: int = 2

    def to_cells(self) -> tuple[str, ...]:
        if not 1 <= self.position <= 999999 or not 1 <= self.quantity <= 1000:
            raise ValueError("Проверьте номер позиции и количество товаров.")
        if not self.article.strip() or not self.name.strip() or not self.volume.strip():
            raise ValueError("Укажите артикул, название и объём товара.")
        try:
            date_format = "%m.%Y" if "." in self.expiry else "%Y-%m"
            expiry = datetime.strptime(self.expiry, date_format).strftime("%m.%Y")
        except ValueError:
            raise ValueError("Укажите срок годности: месяц и год.") from None
        prices = tuple(self._format_price(value) for value in (self.central_bank_price, self.wholesale_price, self.market_price))
        return (str(self.position), self.article.strip(), self.name.strip(), self.volume.strip(), expiry, *prices)

    @staticmethod
    def _format_price(value: str) -> str:
        normalized = value.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        if normalized in ("", "—"):
            return "—"
        try:
            if not re.fullmatch(r"\d{1,9}(?:\.\d{1,2})?", normalized):
                raise InvalidOperation
            price = Decimal(normalized)
        except InvalidOperation:
            raise ValueError("Цена должна быть неотрицательным числом, не более двух знаков после запятой.") from None
        return f"{price:.2f}".replace(".", ",")


@dataclass(frozen=True, slots=True)
class ImportResult:
    added: int
    updated: int


@dataclass(frozen=True, slots=True)
class ProductUnit:
    id: int
    number: int
    sold: bool


@dataclass(frozen=True, slots=True)
class Product:
    id: int
    cells: tuple[str, ...]
    units: tuple[ProductUnit, ...]

    @property
    def sold_count(self) -> int:
        return sum(unit.sold for unit in self.units)

    @property
    def available(self) -> int:
        return len(self.units) - self.sold_count


@dataclass(frozen=True, slots=True)
class Valuation:
    label: str
    total: Decimal
    sold: Decimal
    available: Decimal
    unpriced_total: int
    unpriced_sold: int
    unpriced_available: int

    @property
    def amounts(self) -> tuple[str, ...]:
        return tuple(f"{value:,.2f}".replace(",", " ").replace(".", ",") for value in (self.total, self.sold, self.available))

    @property
    def unpriced(self) -> tuple[int, ...]:
        return self.unpriced_total, self.unpriced_sold, self.unpriced_available


@dataclass(frozen=True, slots=True)
class Inventory:
    products: tuple[Product, ...]

    @property
    def total(self) -> int:
        return sum(len(product.units) for product in self.products)

    @property
    def sold(self) -> int:
        return sum(product.sold_count for product in self.products)

    @property
    def available(self) -> int:
        return self.total - self.sold

    @property
    def next_position(self) -> int:
        return max((int(product.cells[0]) for product in self.products), default=0) + 1

    def sorted_by(self, column: int, descending: bool = False) -> "Inventory":
        if not 0 <= column <= 8:
            raise ValueError("Неизвестная колонка сортировки")
        if column == 8:
            ordered = sorted(self.products, key=lambda product: product.sold_count, reverse=descending)
        elif column in (0, 5, 6, 7):
            priced = [product for product in self.products if product.cells[column] not in ("", "—")]
            unpriced = [product for product in self.products if product.cells[column] in ("", "—")]
            ordered = (
                sorted(priced, key=lambda product: Decimal(product.cells[column].replace(",", ".")), reverse=descending)
                + unpriced
            )
        elif column == 4:
            ordered = sorted(
                self.products, key=lambda product: datetime.strptime(product.cells[column], "%m.%Y"), reverse=descending
            )
        else:
            ordered = sorted(self.products, key=lambda product: self._natural_key(product.cells[column]), reverse=descending)
        return Inventory(tuple(ordered))

    @property
    def valuations(self) -> tuple[Valuation, ...]:
        results = []
        for column, label in ((5, "Цена по ЦБ РФ"), (6, "Оптовая цена Emansi"), (7, "Средняя цена в магазинах")):
            total, sold = Decimal(0), Decimal(0)
            unpriced_total, unpriced_sold = 0, 0
            for product in self.products:
                raw_price = product.cells[column]
                if raw_price in ("", "—"):
                    unpriced_total += len(product.units)
                    unpriced_sold += product.sold_count
                else:
                    price = Decimal(raw_price.replace(" ", "").replace(",", "."))
                    total += price * len(product.units)
                    sold += price * product.sold_count
            results.append(
                Valuation(label, total, sold, total - sold, unpriced_total, unpriced_sold, unpriced_total - unpriced_sold)
            )
        return tuple(results)

    @staticmethod
    def _natural_key(value: str) -> tuple[str, ...]:
        return tuple(part.zfill(64) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))
