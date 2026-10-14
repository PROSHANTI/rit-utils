import json
import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import Inventory, NewProduct, Product, ProductUnit

logger = logging.getLogger(__name__)


class InventoryRepository:
    def __init__(self, database: Path | None = None) -> None:
        default = Path(__file__).resolve().parents[3] / "data" / "one_alma.sqlite3"
        self.database = database if database is not None else Path(os.getenv("ONE_ALMA_DB_PATH", str(default)))

    def snapshot(self) -> Inventory:
        with self._connection() as connection:
            return self._snapshot(connection)

    def set_sold(self, unit_id: int, sold: bool) -> Inventory:
        with self._connection() as connection, connection:
            cursor = connection.execute("UPDATE product_units SET sold = ? WHERE id = ?", (int(sold), unit_id))
            if cursor.rowcount == 0:
                raise LookupError("Товар не найден")
            inventory = self._snapshot(connection)
        logger.info("Отметка продажи сохранена: единица %s, продано %s", unit_id, sold)
        return inventory

    def add_product(self, product: NewProduct) -> None:
        cells = product.to_cells()
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_product(connection, cells, product.quantity)
        logger.info("Добавлена позиция OneAlma: %s", " ".join(product.name.split()))

    def import_products(self, products: list[NewProduct]) -> None:
        prepared = [(product.to_cells(), product.quantity) for product in products]
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for cells, quantity in prepared:
                self._insert_product(connection, cells, quantity)
        logger.info("Импорт товаров OneAlma завершён: %s позиций", len(products))

    def update_product(self, product_id: int, product: NewProduct) -> None:
        cells = product.to_cells()
        with self._connection() as connection, connection:
            # Obtain the write lock before reading quantities.
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
                raise LookupError("Товар не найден")
            units = connection.execute(
                "SELECT * FROM product_units WHERE product_id = ? ORDER BY number", (product_id,)
            ).fetchall()
            if product.quantity < sum(unit["sold"] for unit in units):
                raise ValueError("Количество не может быть меньше числа уже проданных товаров.")
            connection.execute(
                """UPDATE products SET position=?, article=?, name=?, volume=?, expiry=?,
                   central_bank_price=?, wholesale_price=?, market_price=? WHERE id=?""",
                (*cells, product_id),
            )
            if product.quantity < len(units):
                removable = [unit for unit in reversed(units) if not unit["sold"]][: len(units) - product.quantity]
                connection.executemany("DELETE FROM product_units WHERE id=?", [(unit["id"],) for unit in removable])
                remaining = connection.execute(
                    "SELECT id FROM product_units WHERE product_id=? ORDER BY number", (product_id,)
                ).fetchall()
                connection.executemany(
                    "UPDATE product_units SET number=? WHERE id=?",
                    [(number, unit["id"]) for number, unit in enumerate(remaining, start=1)],
                )
            elif product.quantity > len(units):
                self._insert_units(connection, product_id, len(units) + 1, product.quantity)
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
                market_price TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_units (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                number INTEGER NOT NULL CHECK (number > 0),
                sold INTEGER NOT NULL DEFAULT 0 CHECK (sold IN (0, 1)),
                UNIQUE (product_id, number)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS products_position ON products(position);
            """)
        # Serialize the first import across concurrent requests/processes.
        with connection:
            connection.execute("BEGIN IMMEDIATE")
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
    def _insert_product(cls, connection: sqlite3.Connection, cells: tuple[str, ...], quantity: int) -> None:
        product_id = cls._reserve_ids(connection, "next_product_id", 1)
        connection.execute(
            """INSERT INTO products
            (id, position, article, name, volume, expiry, central_bank_price, wholesale_price, market_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (product_id, *cells),
        )
        cls._insert_units(connection, product_id, 1, quantity)

    @classmethod
    def _insert_units(cls, connection: sqlite3.Connection, product_id: int, start: int, end: int) -> None:
        first = cls._reserve_ids(connection, "next_unit_id", end - start + 1)
        connection.executemany(
            "INSERT INTO product_units (id, product_id, number) VALUES (?, ?, ?)",
            [(first + number - start, product_id, number) for number in range(start, end + 1)],
        )

    @staticmethod
    def _snapshot(connection: sqlite3.Connection) -> Inventory:
        rows = connection.execute("""SELECT p.*, u.id AS unit_id, u.number AS unit_number, u.sold
               FROM products p JOIN product_units u ON u.product_id = p.id
               ORDER BY p.id, u.number""").fetchall()
        cells: dict[int, tuple[str, ...]] = {}
        units: dict[int, list[ProductUnit]] = {}
        for row in rows:
            product_id = row["id"]
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
        return Inventory(tuple(Product(product_id, values, tuple(units[product_id])) for product_id, values in cells.items()))
