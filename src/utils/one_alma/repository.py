import json
import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from .models import (
    HistoryEntry,
    ImportResult,
    Inventory,
    NewProduct,
    Product,
    ProductUnit,
    Sale,
    format_cents,
    product_key,
    shipment_fingerprint,
)

logger = logging.getLogger(__name__)
CELL_KEYS = ("position", "article", "name", "volume", "expiry", "central_bank_price", "wholesale_price", "market_price")


class InventoryRepository:
    def __init__(self, database: Path | None = None) -> None:
        default = Path(__file__).resolve().parents[3] / "data" / "one_alma.sqlite3"
        self.database = database if database is not None else Path(os.getenv("ONE_ALMA_DB_PATH", str(default)))

    def snapshot(self) -> Inventory:
        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._snapshot(connection)

    def record_sale(self, product_id: int, quantity: int, customer: str, unit_price: str, request_id: str) -> Inventory:
        if type(quantity) is not int or not 1 <= quantity <= 1000:
            raise ValueError("Укажите целое количество от 1 до 1000.")
        customer = customer.strip()
        if len(customer) > 200:
            raise ValueError("В поле «Кому» можно ввести до 200 символов.")
        normalized = NewProduct._format_price(unit_price)
        price = None if normalized == "—" else int(Decimal(normalized.replace(",", ".")) * 100)
        try:
            request_id = str(UUID(request_id))
        except ValueError:
            raise ValueError("Обновите окно продажи и повторите действие.") from None
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT * FROM one_alma_sales WHERE request_id=?", (request_id,)).fetchone()
            if previous:
                if (previous["product_id"], previous["quantity"], previous["customer"], previous["price_cents"]) != (
                    product_id,
                    quantity,
                    customer,
                    price,
                ):
                    raise ValueError("Этот запрос уже использован. Откройте новую продажу.")
                return self._snapshot(connection)
            cells = self._product_cells(connection, product_id)
            available = connection.execute(
                "SELECT id FROM product_units WHERE product_id=? AND sold=0 ORDER BY number", (product_id,)
            ).fetchall()
            if quantity > len(available):
                raise ValueError(f"Можно продать не больше {len(available)} шт. Обновите остаток.")
            created_at = datetime.now(UTC).isoformat()
            cursor = connection.execute(
                """INSERT INTO one_alma_sales(product_id,cells_json,customer,quantity,price_cents,created_at,request_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (product_id, json.dumps(cells, ensure_ascii=False), customer, quantity, price, created_at, request_id),
            )
            sale_id = cursor.lastrowid
            unit_ids = [row["id"] for row in available[:quantity]]
            connection.executemany("UPDATE product_units SET sold=1 WHERE id=?", [(unit_id,) for unit_id in unit_ids])
            connection.executemany(
                "INSERT INTO one_alma_sale_units(sale_id,unit_id) VALUES (?,?)", [(sale_id, unit_id) for unit_id in unit_ids]
            )
            self._clamp_showcase(connection, product_id)
            self._event(connection, product_id, "sale", {}, cells=cells, sale_id=sale_id, created_at=created_at)
            inventory = self._snapshot(connection)
        logger.info("Оформлена продажа OneAlma: %s, позиция %s, количество %s", sale_id, product_id, quantity)
        return inventory

    def cancel_sale(self, sale_id: int) -> Inventory:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            sale = connection.execute("SELECT * FROM one_alma_sales WHERE id=?", (sale_id,)).fetchone()
            if sale is None:
                raise LookupError("Продажа не найдена.")
            if sale["cancelled_at"] is not None:
                raise ValueError("Эта продажа уже отменена.")
            units = connection.execute(
                """SELECT u.id,u.sold,u.product_id FROM one_alma_sale_units s
                   JOIN product_units u ON u.id=s.unit_id WHERE s.sale_id=?""",
                (sale_id,),
            ).fetchall()
            if len(units) != sale["quantity"] or any(
                not unit["sold"] or unit["product_id"] != sale["product_id"] for unit in units
            ):
                raise ValueError("Товар удалён или остаток изменился. Не удалось отменить продажу.")
            cancelled_at = datetime.now(UTC).isoformat()
            connection.executemany("UPDATE product_units SET sold=0 WHERE id=?", [(unit["id"],) for unit in units])
            connection.execute("UPDATE one_alma_sales SET cancelled_at=? WHERE id=?", (cancelled_at, sale_id))
            self._event(
                connection,
                sale["product_id"],
                "cancel",
                {},
                cells=tuple(json.loads(sale["cells_json"])),
                sale_id=sale_id,
                created_at=cancelled_at,
            )
            inventory = self._snapshot(connection)
        logger.info("Отменена продажа OneAlma: %s", sale_id)
        return inventory

    def set_sold(self, unit_id: int, sold: bool) -> Inventory:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if not sold and self._managed_units(connection, [unit_id]):
                raise ValueError("Отмените эту продажу через историю товара.")
            cursor = connection.execute("UPDATE product_units SET sold = ? WHERE id = ?", (int(sold), unit_id))
            if cursor.rowcount == 0:
                raise LookupError("Товар не найден")
            product_id = connection.execute("SELECT product_id FROM product_units WHERE id=?", (unit_id,)).fetchone()[0]
            self._clamp_showcase(connection, product_id)
            inventory = self._snapshot(connection)
        logger.info("Отметка продажи сохранена: единица %s, продано %s", unit_id, sold)
        return inventory

    def set_sold_count(self, product_id: int, quantity: int) -> Inventory:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            units = connection.execute(
                "SELECT id, sold FROM product_units WHERE product_id=? ORDER BY number", (product_id,)
            ).fetchall()
            if not units:
                raise LookupError("Товар не найден")
            self._validate_count(quantity, len(units))
            managed = self._managed_units(connection, [unit["id"] for unit in units])
            if quantity < len(managed):
                raise ValueError("Отмените оформленные продажи через историю товара.")
            delta = quantity - sum(unit["sold"] for unit in units)
            candidates = (
                [unit for unit in units if not unit["sold"]]
                if delta > 0
                else [unit for unit in reversed(units) if unit["sold"] and unit["id"] not in managed]
            )
            connection.executemany(
                "UPDATE product_units SET sold=? WHERE id=?", [(int(delta > 0), unit["id"]) for unit in candidates[: abs(delta)]]
            )
            self._clamp_showcase(connection, product_id)
            inventory = self._snapshot(connection)
        logger.info("Количество продаж OneAlma сохранено: позиция %s, продано %s", product_id, quantity)
        return inventory

    def set_showcase_quantity(self, product_id: int, quantity: int) -> Inventory:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
                raise LookupError("Товар не найден")
            available = connection.execute(
                "SELECT COUNT(*) FROM product_units WHERE product_id=? AND sold=0", (product_id,)
            ).fetchone()[0]
            self._validate_count(quantity, available)
            before = connection.execute("SELECT showcase_quantity FROM products WHERE id=?", (product_id,)).fetchone()[0]
            connection.execute("UPDATE products SET showcase_quantity=? WHERE id=?", (quantity, product_id))
            if before != quantity:
                self._event(connection, product_id, "showcase", {"description": "Витрина", "quantity": f"{before} → {quantity}"})
            inventory = self._snapshot(connection)
        logger.info("Витрина OneAlma сохранена: позиция %s, количество %s", product_id, quantity)
        return inventory

    @staticmethod
    def _managed_units(connection: sqlite3.Connection, unit_ids: list[int]) -> set[int]:
        active = connection.execute(
            "SELECT u.unit_id FROM one_alma_sale_units u JOIN one_alma_sales s ON s.id=u.sale_id WHERE s.cancelled_at IS NULL"
        ).fetchall()
        return {row[0] for row in active}.intersection(unit_ids)

    @staticmethod
    def _product_cells(connection: sqlite3.Connection, product_id: int) -> tuple[str, ...]:
        row = connection.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if row is None:
            raise LookupError("Товар не найден.")
        return tuple(row[key] for key in CELL_KEYS)

    @classmethod
    def _event(
        cls,
        connection: sqlite3.Connection,
        product_id: int,
        kind: str,
        details: dict[str, str],
        *,
        cells: tuple[str, ...] | None = None,
        sale_id: int | None = None,
        created_at: str | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO one_alma_history(product_id,cells_json,kind,details_json,sale_id,created_at) VALUES (?,?,?,?,?,?)""",
            (
                product_id,
                json.dumps(cells or cls._product_cells(connection, product_id), ensure_ascii=False),
                kind,
                json.dumps(details, ensure_ascii=False),
                sale_id,
                created_at or datetime.now(UTC).isoformat(),
            ),
        )

    @staticmethod
    def _validate_count(quantity: int, maximum: int) -> None:
        if type(quantity) is not int or not 0 <= quantity <= maximum:
            raise ValueError(f"Укажите целое количество от 0 до {maximum}.")

    @staticmethod
    def _clamp_showcase(connection: sqlite3.Connection, product_id: int) -> None:
        connection.execute(
            """UPDATE products SET showcase_quantity=MIN(showcase_quantity,
               (SELECT COUNT(*) FROM product_units WHERE product_id=? AND sold=0)) WHERE id=?""",
            (product_id, product_id),
        )

    def add_product(self, product: NewProduct) -> None:
        replace(product, position=1).to_cells()
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            cells = replace(product, position=self._next_position(connection)).to_cells()
            product_id = self._insert_product(connection, cells, product.quantity)
            self._event(connection, product_id, "edit", {"description": "Добавлен товар", "quantity": f"0 → {product.quantity}"})
        logger.info("Добавлена позиция OneAlma: %s", " ".join(product.name.split()))

    @staticmethod
    def _next_position(connection: sqlite3.Connection) -> int:
        return connection.execute("SELECT COALESCE(MAX(CAST(position AS INTEGER)),0)+1 FROM products").fetchone()[0]

    @staticmethod
    def _check_receipt(connection: sqlite3.Connection, receipt_id: str, fingerprint: str) -> bool:
        previous = connection.execute("SELECT fingerprint FROM one_alma_imports WHERE receipt_id=?", (receipt_id,)).fetchone()
        if previous and previous["fingerprint"] != fingerprint:
            raise ValueError("Эта поставка уже загружена с другими данными. Для новой поставки скачайте новый шаблон.")
        return previous is not None

    @staticmethod
    def _import_plan(connection: sqlite3.Connection, products: list[NewProduct]) -> list[dict]:
        existing: dict[tuple[str, str, str], sqlite3.Row] = {}
        for row in connection.execute(
            """SELECT p.*,COUNT(u.id) AS quantity FROM products p LEFT JOIN product_units u ON u.product_id=p.id
               GROUP BY p.id ORDER BY CAST(p.position AS INTEGER),p.id"""
        ):
            existing.setdefault(product_key(tuple(row[key] for key in CELL_KEYS)), row)
        grouped: dict[tuple[str, str, str], dict] = {}
        next_position = InventoryRepository._next_position(connection)
        for product in products:
            cells = product.to_cells()
            key = product_key(cells)
            if key not in grouped:
                found = existing.get(key)
                position = int(found["position"]) if found else next_position
                if not found:
                    next_position += 1
                grouped[key] = {
                    "cells": replace(product, position=position).to_cells(),
                    "product_id": found["id"] if found else None,
                    "position": position,
                    "before": found["quantity"] if found else 0,
                    "incoming": 0,
                    "action": "Пополнение" if found else "Новый товар",
                    "error": "",
                }
            item = grouped[key]
            item["incoming"] += product.quantity
            item["after"] = item["before"] + item["incoming"]
            if item["after"] > 1000:
                item["error"] = "После пополнения получится больше 1000 шт. в одной позиции."
        return list(grouped.values())

    def preview_import(self, products: list[NewProduct], receipt_id: str) -> dict:
        fingerprint = shipment_fingerprint(products)
        with self._connection() as connection:
            connection.execute("BEGIN")
            already = self._check_receipt(connection, receipt_id, fingerprint)
            plan = self._import_plan(connection, products)
        return {
            "rows": plan,
            "added": sum(item["product_id"] is None for item in plan) if not already else 0,
            "updated": sum(item["product_id"] is not None for item in plan) if not already else 0,
            "quantity": sum(product.quantity for product in products) if not already else 0,
            "already_imported": already,
        }

    def import_products(self, products: list[NewProduct], receipt_id: str | None = None) -> ImportResult:
        if not products:
            raise ValueError("В файле нет товаров.")
        fingerprint = shipment_fingerprint(products)
        receipt_id = receipt_id or "content:" + fingerprint
        added = updated = 0
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._check_receipt(connection, receipt_id, fingerprint):
                return ImportResult(added=0, updated=0, already_imported=True)
            plan = self._import_plan(connection, products)
            for item in plan:
                if item["error"]:
                    raise ValueError(f"Артикул {item['cells'][1]}: {item['error']} Импорт отменён.")
                product_id = item["product_id"]
                if product_id is None:
                    product_id = self._insert_product(connection, item["cells"], item["incoming"])
                    added += 1
                else:
                    last_number = connection.execute(
                        "SELECT COALESCE(MAX(number),0) FROM product_units WHERE product_id=?", (product_id,)
                    ).fetchone()[0]
                    self._insert_units(connection, product_id, last_number + 1, last_number + item["incoming"])
                    updated += 1
                self._event(
                    connection,
                    product_id,
                    "import",
                    {"description": "Приход из Excel", "quantity": f"{item['before']} → {item['after']}"},
                )
            connection.execute(
                "INSERT INTO one_alma_imports(receipt_id,fingerprint,created_at) VALUES (?,?,?)",
                (receipt_id, fingerprint, datetime.now(UTC).isoformat()),
            )
        logger.info("Приход OneAlma сохранён: новых позиций %s, пополнено %s", added, updated)
        return ImportResult(added=added, updated=updated)

    def update_product(self, product_id: int, product: NewProduct) -> None:
        cells = product.to_cells()
        with self._connection() as connection, connection:
            # Obtain the write lock before reading quantities.
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
                raise LookupError("Товар не найден")
            self._update_product(connection, product_id, cells, product.quantity)
        logger.info("Позиция OneAlma обновлена: %s", product_id)

    def delete_products(self, product_ids: list[int]) -> None:
        ids = sorted(set(product_ids))
        if not ids or len(ids) > 1000:
            raise ValueError("Выберите от 1 до 1000 позиций для удаления.")
        placeholders = ",".join("?" for _ in ids)
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            found = connection.execute(f"SELECT COUNT(*) FROM products WHERE id IN ({placeholders})", ids).fetchone()[0]
            if found != len(ids):
                raise LookupError("Часть товаров уже удалена. Обновите страницу.")
            for product_id in ids:
                self._event(connection, product_id, "delete", {"description": "Удалён товар"})
            connection.execute(f"DELETE FROM product_units WHERE product_id IN ({placeholders})", ids)
            connection.execute(f"DELETE FROM products WHERE id IN ({placeholders})", ids)
        logger.info("Удалены позиции OneAlma: %s", len(ids))

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            self._initialize(connection)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS inventory_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                position TEXT NOT NULL,
                article TEXT NOT NULL,
                name TEXT NOT NULL,
                volume TEXT NOT NULL,
                expiry TEXT NOT NULL,
                central_bank_price TEXT NOT NULL,
                wholesale_price TEXT NOT NULL,
                market_price TEXT NOT NULL,
                showcase_quantity INTEGER NOT NULL DEFAULT 0 CHECK (showcase_quantity >= 0)
            );
            CREATE TABLE IF NOT EXISTS product_units (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                number INTEGER NOT NULL CHECK (number > 0),
                sold INTEGER NOT NULL DEFAULT 0 CHECK (sold IN (0, 1)),
                UNIQUE (product_id, number)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS products_position ON products(position);
            CREATE TABLE IF NOT EXISTS one_alma_imports (
                receipt_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS one_alma_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                cells_json TEXT NOT NULL,
                customer TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                price_cents INTEGER CHECK(price_cents >= 0),
                created_at TEXT NOT NULL,
                cancelled_at TEXT,
                request_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS one_alma_sale_units (
                sale_id INTEGER NOT NULL REFERENCES one_alma_sales(id),
                unit_id INTEGER NOT NULL,
                PRIMARY KEY(sale_id,unit_id)
            );
            CREATE INDEX IF NOT EXISTS one_alma_sale_product ON one_alma_sales(product_id);
            CREATE TABLE IF NOT EXISTS one_alma_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                cells_json TEXT NOT NULL,
                kind TEXT NOT NULL,
                details_json TEXT NOT NULL,
                sale_id INTEGER REFERENCES one_alma_sales(id),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS one_alma_history_product ON one_alma_history(product_id,id);
            """)
        # Serialize the first import across concurrent requests/processes.
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(products)")}
            if "showcase_quantity" not in columns:
                connection.execute(
                    "ALTER TABLE products ADD COLUMN showcase_quantity INTEGER NOT NULL DEFAULT 0 CHECK (showcase_quantity >= 0)"
                )
            if connection.execute("SELECT 1 FROM inventory_metadata WHERE key = 'seed_version'").fetchone():
                InventoryRepository._initialize_sequences(connection)
                return
            seed = json.loads(Path(__file__).with_name("products.json").read_text(encoding="utf-8"))
            for product in seed:
                cursor = connection.execute(
                    """INSERT INTO products
                       (position, article, name, volume, expiry, central_bank_price, wholesale_price, market_price)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    product["cells"],
                )
                connection.executemany(
                    "INSERT INTO product_units (product_id, number) VALUES (?, ?)",
                    [(cursor.lastrowid, number) for number in range(1, product["quantity"] + 1)],
                )
            connection.execute("INSERT INTO inventory_metadata VALUES ('seed_version', '1')")
            InventoryRepository._initialize_sequences(connection)
        logger.info("Создан начальный учёт OneAlma: %s позиций", len(seed))

    @staticmethod
    def _initialize_sequences(connection: sqlite3.Connection) -> None:
        # Never reuse deleted IDs: an old browser tab must not edit a new product.
        connection.execute(
            "INSERT OR IGNORE INTO inventory_metadata SELECT 'next_product_id', COALESCE(MAX(id), 0)+1 FROM products"
        )
        connection.execute(
            "INSERT OR IGNORE INTO inventory_metadata SELECT 'next_unit_id', COALESCE(MAX(id), 0)+1 FROM product_units"
        )

    @staticmethod
    def _reserve_ids(connection: sqlite3.Connection, key: str, count: int) -> int:
        first = int(connection.execute("SELECT value FROM inventory_metadata WHERE key=?", (key,)).fetchone()[0])
        connection.execute("UPDATE inventory_metadata SET value=? WHERE key=?", (str(first + count), key))
        return first

    @classmethod
    def _insert_product(cls, connection: sqlite3.Connection, cells: tuple[str, ...], quantity: int) -> int:
        product_id = cls._reserve_ids(connection, "next_product_id", 1)
        connection.execute(
            """INSERT INTO products
            (id, position, article, name, volume, expiry, central_bank_price, wholesale_price, market_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (product_id, *cells),
        )
        cls._insert_units(connection, product_id, 1, quantity)
        return product_id

    @classmethod
    def _insert_units(cls, connection: sqlite3.Connection, product_id: int, start: int, end: int) -> None:
        first = cls._reserve_ids(connection, "next_unit_id", end - start + 1)
        connection.executemany(
            "INSERT INTO product_units (id, product_id, number) VALUES (?, ?, ?)",
            [(first + number - start, product_id, number) for number in range(start, end + 1)],
        )

    @classmethod
    def _update_product(
        cls, connection: sqlite3.Connection, product_id: int, cells: tuple[str, ...], quantity: int, *, event_kind: str = "edit"
    ) -> None:
        previous_cells = cls._product_cells(connection, product_id)
        units = connection.execute("SELECT * FROM product_units WHERE product_id=? ORDER BY number", (product_id,)).fetchall()
        if quantity < sum(unit["sold"] for unit in units):
            raise ValueError(f"№ {cells[0]}: количество не может быть меньше числа уже проданных товаров.")
        connection.execute(
            """UPDATE products SET position=?, article=?, name=?, volume=?, expiry=?,
               central_bank_price=?, wholesale_price=?, market_price=? WHERE id=?""",
            (*cells, product_id),
        )
        if quantity < len(units):
            removable = [unit for unit in reversed(units) if not unit["sold"]][: len(units) - quantity]
            connection.executemany("DELETE FROM product_units WHERE id=?", [(unit["id"],) for unit in removable])
            remaining = connection.execute(
                "SELECT id FROM product_units WHERE product_id=? ORDER BY number", (product_id,)
            ).fetchall()
            connection.executemany(
                "UPDATE product_units SET number=? WHERE id=?",
                [(number, unit["id"]) for number, unit in enumerate(remaining, start=1)],
            )
        elif quantity > len(units):
            cls._insert_units(connection, product_id, len(units) + 1, quantity)
        cls._clamp_showcase(connection, product_id)
        if previous_cells != cells or len(units) != quantity:
            cls._event(
                connection,
                product_id,
                event_kind,
                {
                    "description": "Обновление из импорта" if event_kind == "import" else "Изменён товар",
                    "quantity": f"{len(units)} → {quantity}",
                    "price": f"{previous_cells[5]} → {cells[5]}",
                },
            )

    @staticmethod
    def _snapshot(connection: sqlite3.Connection) -> Inventory:
        rows = connection.execute("""SELECT p.*, u.id AS unit_id, u.number AS unit_number, u.sold
               FROM products p JOIN product_units u ON u.product_id = p.id
               ORDER BY p.id, u.number""").fetchall()
        cells: dict[int, tuple[str, ...]] = {}
        units: dict[int, list[ProductUnit]] = {}
        showcase: dict[int, int] = {}
        for row in rows:
            product_id = row["id"]
            showcase[product_id] = row["showcase_quantity"]
            cells[product_id] = tuple(
                row[key]
                for key in (
                    "position",
                    "article",
                    "name",
                    "volume",
                    "expiry",
                    "central_bank_price",
                    "wholesale_price",
                    "market_price",
                )
            )
            units.setdefault(product_id, []).append(ProductUnit(row["unit_id"], row["unit_number"], bool(row["sold"])))
        products = tuple(
            Product(product_id, values, tuple(units[product_id]), showcase[product_id]) for product_id, values in cells.items()
        )
        sales = tuple(
            Sale(
                row["id"],
                row["product_id"],
                tuple(json.loads(row["cells_json"])),
                row["customer"],
                row["quantity"],
                row["price_cents"],
                datetime.fromisoformat(row["created_at"]),
                datetime.fromisoformat(row["cancelled_at"]) if row["cancelled_at"] else None,
            )
            for row in connection.execute("SELECT * FROM one_alma_sales ORDER BY id")
        )
        sale_by_id = {sale.id: sale for sale in sales}
        history = []
        for row in connection.execute("SELECT * FROM one_alma_history ORDER BY id DESC"):
            details = json.loads(row["details_json"])
            entry = dict(
                description=details.get("description", ""),
                customer="—",
                quantity=details.get("quantity", "—"),
                price=details.get("price", "—"),
                amount="—",
            )
            sale = sale_by_id.get(row["sale_id"])
            cancelled = can_cancel = False
            if sale is not None:
                is_cancel = row["kind"] == "cancel"
                cancelled = is_cancel or sale.cancelled_at is not None
                can_cancel = not is_cancel and sale.cancelled_at is None and sale.product_id in cells
                description = f"{'Отмена продажи' if is_cancel else 'Продажа'} #{sale.id}"
                if not is_cancel and sale.cancelled_at is not None:
                    description += "\nОтменена"
                entry = dict(
                    description=description,
                    customer=sale.customer or "Не указан",
                    quantity=f"{'+' if is_cancel else '−'}{sale.quantity}",
                    price=format_cents(sale.price_cents),
                    amount=("−" if is_cancel and sale.amount_cents is not None else "") + format_cents(sale.amount_cents),
                )
            history.append(
                HistoryEntry(
                    row["id"],
                    row["product_id"],
                    datetime.fromisoformat(row["created_at"]),
                    tuple(json.loads(row["cells_json"])),
                    **entry,
                    sale_id=row["sale_id"],
                    cancelled=cancelled,
                    can_cancel=can_cancel,
                )
            )
        return Inventory(products, sales, tuple(history))
