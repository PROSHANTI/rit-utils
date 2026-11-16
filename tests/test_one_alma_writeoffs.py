import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pypdf import PdfReader

from src.main import application
from src.utils.one_alma.models import NewProduct
from src.utils.one_alma.pdf_export import InventoryPdfExporter, SalesPdfExporter
from src.utils.one_alma.repository import InventoryRepository


@pytest.fixture
def repository(tmp_path):
    return InventoryRepository(tmp_path / "one_alma.sqlite3")


@pytest.fixture
def item():
    return NewProduct(
        position=26,
        article="0007",
        name="Крем",
        volume="30 мл",
        expiry="05.2028",
        central_bank_price="100,25",
        wholesale_price="200",
        market_price="",
        quantity=7,
    )


@pytest.fixture
def product(repository, item):
    repository.add_product(item)
    return repository.snapshot().products[-1]


def writeoff(repository, product, quantity=1, comment="Брак", request_id=None):
    return repository.record_writeoff(product.id, quantity, comment, request_id or str(uuid4()))


def pdf_text(content):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


def test_writeoff_preserves_sales_prices_ids_and_stock_identity(repository, product):
    repository.record_sale(product.id, 3, "Покупатель", "79", str(uuid4()))
    repository.set_showcase_quantity(product.id, 3)
    before = repository.snapshot()

    changed = writeoff(repository, product)

    saved = changed.products[-1]
    assert (saved.sold_count, saved.written_off_count, saved.available, saved.showcase_quantity) == (3, 1, 3, 3)
    assert changed.total == before.total
    assert changed.total == changed.sold + changed.written_off + changed.available
    assert changed.sales == before.sales and changed.sales_amount == before.sales_amount
    assert saved.cells == product.cells
    assert [unit.id for unit in saved.units] == [unit.id for unit in product.units]
    assert not any(unit.sold and unit.written_off for unit in saved.units)
    assert changed.writeoffs[-1].comment == "Брак"
    assert changed.history[0].writeoff_id == changed.writeoffs[-1].id
    assert InventoryRepository(repository.database).snapshot() == changed


@pytest.mark.parametrize("quantity", [0, -1, 8, 1.5, True])
def test_invalid_writeoff_quantity_is_atomic(repository, product, quantity):
    before = repository.snapshot()

    with pytest.raises(ValueError):
        writeoff(repository, product, quantity)

    assert repository.snapshot() == before


def test_comment_length_and_request_id_are_validated_before_mutation(repository, product):
    writeoff(repository, product, comment="Я" * 255)
    before = repository.snapshot()

    with pytest.raises(ValueError, match="255"):
        writeoff(repository, product, comment="Я" * 256)
    with pytest.raises(ValueError, match="окно списания"):
        writeoff(repository, product, request_id="invalid")

    assert repository.snapshot() == before


def test_repeated_request_never_writes_off_twice_even_after_cancel(repository, product):
    request_id = str(uuid4())
    first = writeoff(repository, product, 2, request_id=request_id)

    repeated = writeoff(repository, product, 2, request_id=request_id)
    cancelled = repository.cancel_writeoff(first.writeoffs[-1].id)
    after_retry = writeoff(repository, product, 2, request_id=request_id)

    assert repeated == first
    assert after_retry == cancelled
    with pytest.raises(ValueError, match="уже использован"):
        writeoff(repository, product, 1, request_id=request_id)
    assert repository.snapshot() == cancelled


def test_cancel_older_writeoff_keeps_newer_writeoff_and_sale(repository, product):
    first = writeoff(repository, product).writeoffs[-1]
    second = writeoff(repository, product, 2).writeoffs[-1]
    sale = repository.record_sale(product.id, 1, "Анна", "80", str(uuid4())).sales[-1]

    changed = repository.cancel_writeoff(first.id)

    assert changed.products[-1].written_off_count == 2
    assert changed.products[-1].available == 4
    assert changed.writeoffs[-1] == second
    assert changed.sales[-1] == sale
    assert changed.writeoffs[0].cancelled_at is not None
    assert changed.history[0].description == f"Отмена списания #{first.id}"
    with pytest.raises(ValueError, match="уже отменено"):
        repository.cancel_writeoff(first.id)
    assert repository.snapshot() == changed


def test_writeoff_clamps_showcase_and_cancel_does_not_invent_showcase_units(repository, product):
    repository.set_showcase_quantity(product.id, 6)

    changed = writeoff(repository, product, 5)
    restored = repository.cancel_writeoff(changed.writeoffs[-1].id)

    assert changed.products[-1].available == changed.products[-1].showcase_quantity == 2
    assert restored.products[-1].available == 7
    assert restored.products[-1].showcase_quantity == 2


def test_written_units_cannot_be_sold_with_any_sale_method(repository, product):
    changed = writeoff(repository, product, 6)
    unit = next(unit for unit in changed.products[-1].units if unit.written_off)

    with pytest.raises(ValueError, match="списана"):
        repository.set_sold(unit.id, True)
    with pytest.raises(ValueError):
        repository.set_sold_count(product.id, 2)
    with pytest.raises(ValueError, match="не больше 1"):
        repository.record_sale(product.id, 2, "", "", str(uuid4()))
    sold = repository.set_sold_count(product.id, 1)

    assert sold.products[-1].available == 0
    assert not any(unit.sold and unit.written_off for unit in sold.products[-1].units)


def test_manual_edit_cannot_remove_sold_or_written_units(repository, product, item):
    repository.record_sale(product.id, 2, "Анна", "80", str(uuid4()))
    writeoff(repository, product, 3)
    before = repository.snapshot()

    with pytest.raises(ValueError, match="списанных"):
        repository.update_product(product.id, replace(item, quantity=4))
    unchanged = repository.snapshot()
    repository.update_product(product.id, replace(item, quantity=5))
    changed = repository.snapshot()

    assert unchanged == before
    assert changed.products[-1].sold_count == 2 and changed.products[-1].written_off_count == 3
    assert changed.products[-1].available == 0
    assert changed.writeoffs == before.writeoffs and changed.sales == before.sales
    restored = repository.cancel_writeoff(changed.writeoffs[-1].id)
    assert restored.products[-1].available == 3


def test_shipment_adds_stock_and_preserves_writeoffs_sales_prices_and_showcase(repository, product, item):
    repository.record_sale(product.id, 1, "Анна", "80", str(uuid4()))
    writeoff(repository, product, 2)
    repository.set_showcase_quantity(product.id, 2)
    before = repository.snapshot()

    repository.import_products([replace(item, quantity=3, central_bank_price="999")], str(uuid4()))
    changed = repository.snapshot()

    saved = changed.products[-1]
    assert len(saved.units) == 10
    assert saved.sold_count == 1 and saved.written_off_count == 2 and saved.available == 7
    assert saved.showcase_quantity == 2
    assert saved.cells == product.cells
    assert changed.writeoffs == before.writeoffs and changed.sales == before.sales


def test_valuations_exclude_writeoffs_from_available_without_treating_them_as_sales(repository, product):
    before = repository.snapshot()

    changed = writeoff(repository, product, 2)

    assert changed.valuations[0].total == before.valuations[0].total
    assert changed.valuations[0].sold == before.valuations[0].sold
    assert changed.valuations[0].available == before.valuations[0].available - Decimal("200.50")
    assert changed.valuations[2].unpriced_available == before.valuations[2].unpriced_available - 2
    assert changed.sales_amount == "0,00"


def test_parallel_sale_and_writeoff_cannot_allocate_the_same_unit(repository, product):
    def operation(kind):
        try:
            if kind == "sale":
                repository.record_sale(product.id, 5, "Анна", "80", str(uuid4()))
            else:
                writeoff(repository, product, 5)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation, ["sale", "writeoff"]))

    saved = repository.snapshot().products[-1]
    assert sorted(results) == [False, True]
    assert saved.available == 2
    assert saved.sold_count + saved.written_off_count == 5
    assert not any(unit.sold and unit.written_off for unit in saved.units)


def test_parallel_identical_requests_write_off_once(repository, product):
    request_id = str(uuid4())

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: writeoff(repository, product, 2, request_id=request_id), range(3)))

    assert all(result.products[-1].written_off_count == 2 for result in results)
    assert len(repository.snapshot().writeoffs) == 1


def test_deleted_product_retains_writeoff_record_without_reusing_its_id(repository, product, item):
    before = writeoff(repository, product, 2)

    repository.delete_products([product.id])
    repository.add_product(item)
    changed = repository.snapshot()

    assert changed.writeoffs == before.writeoffs
    assert changed.products[-1].id != product.id
    with pytest.raises(ValueError, match="удалён"):
        repository.cancel_writeoff(before.writeoffs[-1].id)


@pytest.fixture
def web(authenticated_client, repository, product, monkeypatch):
    monkeypatch.setattr(application.routes.one_alma, "repository", repository)
    response = authenticated_client.get("/one_alma")
    match = re.search(r'data-csrf-token="([^"]+)"', response.text)
    assert match is not None
    return authenticated_client, match.group(1)


def test_writeoff_endpoints_history_cancel_and_idempotent_retry(web, repository, product):
    client, csrf = web
    body = dict(quantity="2", comment="<b>Брак & упаковка</b>", request_id=str(uuid4()), csrf_token=csrf)

    saved = client.post(f"/one_alma/products/{product.id}/writeoffs", data=body)
    repeated = client.post(f"/one_alma/products/{product.id}/writeoffs", data=body)
    history = client.get(f"/one_alma/products/{product.id}/history").json()
    writeoff_id = repository.snapshot().writeoffs[-1].id
    cancelled = client.post(f"/one_alma/writeoffs/{writeoff_id}/cancel", data={"csrf_token": csrf})

    assert saved.status_code == repeated.status_code == cancelled.status_code == 200
    assert saved.json() == repeated.json()
    assert saved.json()["written_off"] == 2 and saved.json()["sold"] == 0
    assert history["written_off"] == 2 and history["available"] == 5 and history["total"] == 7
    entry = next(entry for entry in history["entries"] if entry["writeoff_id"] == writeoff_id)
    assert entry["comment"] == body["comment"] and entry["can_cancel"]
    assert cancelled.json()["written_off"] == 0


@pytest.mark.parametrize(
    "data", [{"quantity": "0"}, {"quantity": "8"}, {"quantity": "1.5"}, {"comment": "Я" * 256}, {"csrf_token": "bad"}]
)
def test_invalid_endpoint_writeoff_does_not_mutate_database(web, repository, product, data):
    client, csrf = web
    body = dict(quantity="1", comment="", request_id=str(uuid4()), csrf_token=csrf) | data
    before = repository.snapshot()

    response = client.post(f"/one_alma/products/{product.id}/writeoffs", data=body)

    assert response.status_code in (403, 422)
    assert repository.snapshot() == before


def test_sales_history_lists_existing_sales_without_product_edits_or_writeoffs(web, repository, product, item):
    client, _ = web
    before = repository.record_sale(product.id, 2, "Анна & <компания>", "80,25", str(uuid4()))
    writeoff(repository, product, 1)
    repository.update_product(product.id, replace(item, name="Новое название", central_bank_price="999"))

    response = client.get("/one_alma/sales")
    data = response.json()

    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert len(data["sales"]) == 1 and data["sold"] == 2
    sale = data["sales"][0]
    assert sale["customer"] == "Анна & <компания>" and sale["price"] == "80,25" and sale["amount"] == "160,50"
    assert sale["cells"] == list(before.sales[-1].cells)
    assert sale["created_at"] == before.sales[-1].created_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M:%S")


def test_inventory_pdf_separates_writeoffs_and_changes_from_sales(repository, product, item):
    repository.record_sale(product.id, 2, "Уникальный покупатель", "80,25", str(uuid4()))
    writeoff(repository, product, 1, "Треснул <флакон> & крышка")
    repository.update_product(product.id, replace(item, name="Новое имя"))
    inventory = repository.snapshot()

    text = pdf_text(InventoryPdfExporter().export(inventory))
    sales_text = pdf_text(SalesPdfExporter().export(inventory))

    assert "Списанные товары" in text and "Треснул <флакон> & крышка" in text
    assert "История изменений" in text
    assert "Уникальный покупатель" not in text and "Продажа #" not in text
    assert "Уникальный покупатель" in sales_text and "80,25" in sales_text and "160,50" in sales_text
    assert "История изменений" not in sales_text and "Треснул" not in sales_text


def test_cancelled_writeoff_and_single_sale_pdf_preserve_original_details(web, repository, product):
    client, _ = web
    writeoff_id = writeoff(repository, product).writeoffs[-1].id
    repository.cancel_writeoff(writeoff_id)
    first = repository.record_sale(product.id, 1, "Первый покупатель", "80", str(uuid4())).sales[-1]
    repository.record_sale(product.id, 1, "Второй покупатель", "90", str(uuid4()))
    repository.cancel_sale(first.id)

    sales = client.get(f"/one_alma/sales/pdf?sale_id={first.id}")
    missing = client.get("/one_alma/sales/pdf?sale_id=99999")
    text = pdf_text(sales.content)
    inventory_text = pdf_text(InventoryPdfExporter().export(repository.snapshot()))

    assert sales.status_code == 200 and missing.status_code == 404
    assert "Первый покупатель" in text and "Второй покупатель" not in text and "Отменена" in text
    assert "Списанные товары" in inventory_text and "Отменено" in inventory_text


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/one_alma/sales"),
        ("GET", "/one_alma/sales/pdf"),
        ("POST", "/one_alma/products/1/writeoffs"),
        ("POST", "/one_alma/writeoffs/1/cancel"),
    ],
)
def test_new_routes_require_authentication(client, method, path):
    response = client.request(method, path, follow_redirects=False)

    assert response.status_code in (303, 401)


def test_migration_preserves_all_original_sales_and_history_cells(repository, product):
    repository.set_showcase_quantity(product.id, 3)
    original = repository.record_sale(product.id, 2, "Анна", "80,25", str(uuid4()))
    with sqlite3.connect(repository.database) as connection:
        connection.execute("ALTER TABLE one_alma_history DROP COLUMN writeoff_id")
        connection.execute("ALTER TABLE product_units DROP COLUMN written_off")
        connection.execute("DROP TABLE one_alma_writeoff_units")
        connection.execute("DROP TABLE one_alma_writeoffs")
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        ]
        columns = {name: [row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')] for name in tables}
        before = {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall() for name in tables}

    migrated = repository.snapshot()
    repeated = repository.snapshot()

    assert migrated == repeated
    assert migrated.sales == original.sales and migrated.history == original.history
    assert migrated.products == original.products and migrated.written_off == 0
    with sqlite3.connect(repository.database) as connection:
        for name, names in columns.items():
            projection = ",".join(f'"{column}"' for column in names)
            assert connection.execute(f'SELECT {projection} FROM "{name}" ORDER BY rowid').fetchall() == before[name]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
