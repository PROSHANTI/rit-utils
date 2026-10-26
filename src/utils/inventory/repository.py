import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .models import MOSCOW, InventoryItem, StoredItem


class InventoryRepository:
    """Separate SQLite store. Every mutation has an online, restorable pre-change backup."""

    backup_limit = 20

    def __init__(self, database: Path | None = None, backup_directory: Path | None = None) -> None:
        default = Path(__file__).resolve().parents[3] / "data" / "inventory.sqlite3"
        self.database = database or Path(os.getenv("INVENTORY_DB_PATH", str(default)))
        self.backup_directory = backup_directory or Path(
            os.getenv("INVENTORY_BACKUP_DIR", str(self.database.parent / "inventory-backups"))
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS inventory_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article TEXT NOT NULL, brand TEXT NOT NULL, name TEXT NOT NULL,
                    purchase_price TEXT NOT NULL, sale_price TEXT NOT NULL, expiry TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity >= 0)
                );
                CREATE TABLE IF NOT EXISTS inventory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL, ended_at TEXT, products_json TEXT NOT NULL
                );
            """)
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            # Use a separate read connection while the reservation prevents other writers.
            # Calling backup() on a connection with its own write transaction can block.
            self._backup()
            yield connection

    def _backup(self) -> None:
        self.backup_directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(MOSCOW).strftime("%Y%m%d-%H%M%S-%f")
        target = self.backup_directory / f"inventory-{stamp}-{uuid4().hex[:8]}.sqlite3"
        partial = target.with_suffix(".partial")
        try:
            with sqlite3.connect(self.database) as source, sqlite3.connect(partial) as destination:
                source.backup(destination)
            partial.chmod(0o600)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
        for old in sorted(self.backup_directory.glob("inventory-*.sqlite3"), reverse=True)[self.backup_limit :]:
            old.unlink()

    @staticmethod
    def _items(connection: sqlite3.Connection) -> list[StoredItem]:
        return [StoredItem(**dict(row)) for row in connection.execute("SELECT * FROM inventory_products ORDER BY id")]

    def items(self) -> list[StoredItem]:
        with self._connection() as connection:
            return self._items(connection)

    @staticmethod
    def _insert(connection: sqlite3.Connection, item: InventoryItem) -> int:
        cursor = connection.execute(
            """INSERT INTO inventory_products
               (article, brand, name, purchase_price, sale_price, expiry, quantity) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (item.article, item.brand, item.name, item.purchase_price, item.sale_price, item.expiry, item.quantity),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def add(self, item: InventoryItem) -> int:
        with self._write() as connection:
            return self._insert(connection, item)

    def update(self, item_id: int, item: InventoryItem) -> None:
        with self._write() as connection:
            cursor = connection.execute(
                """UPDATE inventory_products SET article=?, brand=?, name=?, purchase_price=?, sale_price=?, expiry=?, quantity=?
                   WHERE id=?""",
                (item.article, item.brand, item.name, item.purchase_price, item.sale_price, item.expiry, item.quantity, item_id),
            )
            if not cursor.rowcount:
                raise LookupError("Товар не найден. Обновите страницу.")

    def delete(self, item_id: int) -> None:
        with self._write() as connection:
            if not connection.execute("DELETE FROM inventory_products WHERE id=?", (item_id,)).rowcount:
                raise LookupError("Товар не найден.")

    def set_quantity(self, item_id: int, *, quantity: int | None = None, delta: int | None = None) -> None:
        if (quantity is None) == (delta is None):
            raise ValueError("Укажите количество или изменение на одну штуку.")
        with self._write() as connection:
            row = connection.execute("SELECT * FROM inventory_products WHERE id=?", (item_id,)).fetchone()
            if row is None:
                raise LookupError("Товар не найден. Обновите страницу.")
            value = quantity if quantity is not None else row["quantity"] + (delta or 0)
            # Apply the same validation to direct edits and atomic +/- operations.
            item = InventoryItem(**({key: row[key] for key in InventoryItem.model_fields} | {"quantity": value}))
            connection.execute("UPDATE inventory_products SET quantity=? WHERE id=?", (item.quantity, item_id))

    def preview_import(self, items: list[InventoryItem]) -> dict[str, object]:
        with self._connection() as connection:
            return self._import_plan(connection, items)

    def _import_plan(self, connection: sqlite3.Connection, items: list[InventoryItem]) -> dict[str, object]:
        existing = self._items(connection)
        fingerprint = hashlib.sha256(json.dumps([item.model_dump() for item in existing], sort_keys=True).encode()).hexdigest()
        articles: dict[str, list[StoredItem]] = {}
        for stored in existing:
            if stored.article:
                articles.setdefault(stored.article, []).append(stored)
        seen = set()
        rows = []
        for item in items:
            if item.article and item.article in seen:
                raise ValueError(f"Артикул {item.article} повторяется в Excel. Оставьте одну строку на артикул.")
            seen.add(item.article)
            matches = articles.get(item.article, []) if item.article else []
            if len(matches) > 1:
                raise ValueError(f"Артикул {item.article} найден у нескольких товаров. Уточните артикулы перед импортом.")
            previous = matches[0] if matches else None
            merged = (
                InventoryItem(
                    **(
                        previous.model_dump(include=set(InventoryItem.model_fields))
                        | item.model_dump(include=item.model_fields_set)
                    )
                )
                if previous
                else item
            )
            rows.append(
                {
                    "id": previous.id if previous else None,
                    "action": "update" if previous else "add",
                    "before": previous.view() if previous else None,
                    "after": merged.model_dump() | {"quantity": str(merged.quantity)},
                }
            )
        return {
            "fingerprint": fingerprint,
            "rows": rows,
            "added": sum(row["action"] == "add" for row in rows),
            "updated": sum(row["action"] == "update" for row in rows),
        }

    def import_items(self, items: list[InventoryItem], fingerprint: str) -> dict[str, int]:
        added = updated = 0
        with self._write() as connection:
            plan = self._import_plan(connection, items)
            if plan["fingerprint"] != fingerprint:
                raise ValueError("Таблица изменилась после сверки. Постройте предварительный просмотр ещё раз.")
            # Recompute matches under the write lock; nothing is partially committed on failure.
            for item in items:
                row = (
                    connection.execute("SELECT * FROM inventory_products WHERE article=?", (item.article,)).fetchone()
                    if item.article
                    else None
                )
                if row is None:
                    self._insert(connection, item)
                    added += 1
                else:
                    merged = InventoryItem(
                        **(
                            {key: row[key] for key in InventoryItem.model_fields}
                            | item.model_dump(include=item.model_fields_set)
                        )
                    )
                    connection.execute(
                        """UPDATE inventory_products SET article=?, brand=?, name=?, purchase_price=?,
                           sale_price=?, expiry=?, quantity=?
                           WHERE id=?""",
                        (
                            merged.article,
                            merged.brand,
                            merged.name,
                            merged.purchase_price,
                            merged.sale_price,
                            merged.expiry,
                            merged.quantity,
                            row["id"],
                        ),
                    )
                    updated += 1
            return {"added": added, "updated": updated}

    def create_snapshot(self) -> int:
        with self._write() as connection:
            stamp = datetime.now(MOSCOW).isoformat(timespec="microseconds")
            products = json.dumps([item.model_dump() for item in self._items(connection)], ensure_ascii=False)
            connection.execute("UPDATE inventory_history SET ended_at=? WHERE ended_at IS NULL", (stamp,))
            cursor = connection.execute(
                "INSERT INTO inventory_history (created_at, products_json) VALUES (?, ?)", (stamp, products)
            )
            assert cursor.lastrowid is not None
            return cursor.lastrowid

    def history(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM inventory_history ORDER BY id DESC")]

    def export_state(self) -> tuple[list[StoredItem], list[dict[str, object]]]:
        with self._connection() as connection, connection:
            # Current stock and history are read from one consistent SQLite snapshot.
            connection.execute("BEGIN")
            return self._items(connection), [
                dict(row) for row in connection.execute("SELECT * FROM inventory_history ORDER BY id DESC")
            ]

    def delete_snapshot(self, snapshot_id: int) -> None:
        with self._write() as connection:
            row = connection.execute("SELECT * FROM inventory_history WHERE id=?", (snapshot_id,)).fetchone()
            if row is None:
                raise LookupError("Инвентаризация не найдена.")
            previous = connection.execute(
                "SELECT id FROM inventory_history WHERE id<? ORDER BY id DESC LIMIT 1", (snapshot_id,)
            ).fetchone()
            if previous:
                connection.execute("UPDATE inventory_history SET ended_at=? WHERE id=?", (row["ended_at"], previous["id"]))
            connection.execute("DELETE FROM inventory_history WHERE id=?", (snapshot_id,))
