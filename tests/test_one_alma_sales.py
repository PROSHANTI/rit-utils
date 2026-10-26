import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook
from pypdf import PdfReader

from src.main import application
from src.utils.one_alma.models import NewProduct
from src.utils.one_alma.pdf_export import InventoryPdfExporter
from src.utils.one_alma.repository import InventoryRepository


@pytest.fixture
def repository(tmp_path):
    return InventoryRepository(tmp_path / "inventory.sqlite3")


@pytest.fixture
def item():
    return NewProduct(
        position=26,
        article="0007",
        name="Крем",
        volume="30 мл",
        expiry="05.2028",
        central_bank_price="100,25",
        wholesale_price="",
        market_price="",
        quantity=4,
    )


@pytest.fixture
def product(repository, item):
    repository.add_product(item)
    return repository.snapshot().products[-1]


def sell(repository, product, quantity=1, customer="Макс", price="79,99", request_id=None):
    return repository.record_sale(product.id, quantity, customer, price, request_id or str(uuid4()))


def test_sale_preserves_products_prices_ids_and_uses_editable_price(repository, product):
    repository.set_showcase_quantity(product.id, 2)
    before = repository.snapshot()

    changed = sell(repository, product, 2)

    saved = changed.products[-1]
    assert saved.cells == product.cells
    assert [u.id for u in saved.units] == [u.id for u in product.units]
    assert [u.sold for u in saved.units] == [True, True, False, False]
    assert saved.showcase_quantity == 2
    assert changed.total == before.total
    assert changed.sales[-1].quantity == 2 and changed.sales[-1].price_cents == 7999
    assert changed.sales_amount == "159,98"
    assert InventoryRepository(repository.database).snapshot() == changed


@pytest.mark.parametrize("quantity", [0, -1, 5, 1.5, True])
def test_invalid_sale_quantity_is_atomic(repository, product, quantity):
    before = repository.snapshot()

    with pytest.raises(ValueError):
        sell(repository, product, quantity)

    assert repository.snapshot() == before


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity", "10.001", "1e2", "1000000000"])
def test_invalid_sale_price_is_atomic(repository, product, price):
    before = repository.snapshot()

    with pytest.raises(ValueError):
        sell(repository, product, price=price)

    assert repository.snapshot() == before


def test_unknown_and_zero_prices_are_distinct(repository, product):
    sell(repository, product, 2, price="")

    changed = sell(repository, product, price="0")

    assert [s.price_cents for s in changed.sales] == [None, 0]
    assert changed.sales_unpriced == 2
    assert changed.sales_amount == "0,00"


def test_cancel_older_sale_preserves_later_sale_and_adds_history(repository, product):
    first = sell(repository, product).sales[-1]
    later = sell(repository, product, 2, "Петя", "150").sales[-1]

    changed = repository.cancel_sale(first.id)

    assert [u.sold for u in changed.products[-1].units] == [False, True, True, False]
    assert changed.sales[-1] == later
    assert changed.sales[0].cancelled_at is not None
    assert changed.sales_amount == "300,00"
    assert changed.history[0].description == f"Отмена продажи #{first.id}"
    assert changed.history[0].quantity == "+1"
    assert [entry.can_cancel for entry in changed.history if entry.sale_id == first.id] == [False, False]


def test_repeated_cancel_cannot_touch_units_resold_to_another_customer(repository, product):
    first = sell(repository, product).sales[-1]
    repository.cancel_sale(first.id)
    sell(repository, product, customer="Другой")
    before = repository.snapshot()

    with pytest.raises(ValueError, match="уже отменена"):
        repository.cancel_sale(first.id)

    assert repository.snapshot() == before


def test_full_sale_keeps_product_and_cancel_does_not_restore_showcase(repository, product):
    repository.set_showcase_quantity(product.id, 3)
    changed = sell(repository, product, 4)
    assert changed.products[-1].available == changed.products[-1].showcase_quantity == 0

    cancelled = repository.cancel_sale(changed.sales[-1].id)

    assert cancelled.products[-1].available == 4
    assert cancelled.products[-1].showcase_quantity == 0
    assert cancelled.products[-1].cells == product.cells


def test_same_request_is_idempotent_and_cannot_be_reused_with_other_data(repository, product):
    request_id = str(uuid4())
    original = sell(repository, product, request_id=request_id)

    repeated = sell(repository, product, request_id=request_id)
    with pytest.raises(ValueError, match="уже использован"):
        sell(repository, product, price="500", request_id=request_id)

    assert repeated == original == repository.snapshot()
    assert len(repeated.sales) == 1


def test_same_request_after_cancellation_does_not_create_a_new_sale(repository, product):
    request_id = str(uuid4())
    sale = sell(repository, product, request_id=request_id).sales[-1]
    before = repository.cancel_sale(sale.id)

    retried = sell(repository, product, request_id=request_id)

    assert retried == before
    assert retried.products[-1].sold_count == 0


def test_import_preserves_sale_snapshot_customer_date_price_and_showcase(repository, product, item):
    repository.set_showcase_quantity(product.id, 2)
    original = sell(repository, product, 2)
    sale = original.sales[-1]

    repository.import_products([replace(item, central_bank_price="500", quantity=5, name="Новое имя")])
    changed = repository.snapshot()

    assert changed.sales[-1] == sale
    assert changed.products[-1].cells[5] == "500,00"
    assert changed.products[-1].showcase_quantity == 2
    assert [u.id for u in changed.products[-1].units[:4]] == [u.id for u in product.units]
    assert changed.sales_amount == "159,98"
    assert changed.history[0].description == "Обновление из импорта"


def test_failed_import_rolls_back_inventory_and_history(repository, product, item):
    sell(repository, product, 3)
    before = repository.snapshot()

    with pytest.raises(ValueError, match="меньше"):
        repository.import_products([replace(item, position=27), replace(item, quantity=2)])

    assert repository.snapshot() == before


def test_sale_and_history_rollback_together_on_sql_failure(repository, product, monkeypatch):
    before = repository.snapshot()

    def fail(*args, **kwargs):
        raise sqlite3.IntegrityError("forced history failure")

    monkeypatch.setattr(repository, "_event", fail)

    with pytest.raises(sqlite3.IntegrityError):
        sell(repository, product, 2)

    assert repository.snapshot() == before


def test_concurrent_sales_cannot_oversell(repository, product):
    def attempt(_):
        try:
            sell(repository, product, 3)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))

    assert sorted(results) == [False, True]
    assert repository.snapshot().products[-1].sold_count == 3
    assert len(repository.snapshot().sales) == 1


def test_legacy_controls_cannot_corrupt_recorded_sales(repository, product):
    sell(repository, product, 2)
    before = repository.snapshot()

    with pytest.raises(ValueError, match="историю"):
        repository.set_sold(product.units[0].id, False)
    with pytest.raises(ValueError, match="историю"):
        repository.set_sold_count(product.id, 0)

    assert repository.snapshot() == before


def test_delete_preserves_sales_history_and_cannot_restore_deleted_units(repository, product):
    sale = sell(repository, product).sales[-1]

    repository.delete_products([product.id])
    changed = repository.snapshot()

    assert changed.sales[-1] == sale
    assert not any(p.id == product.id for p in changed.products)
    assert all(not entry.can_cancel for entry in changed.history if entry.sale_id == sale.id)
    with pytest.raises(ValueError, match="удалён"):
        repository.cancel_sale(sale.id)


def test_migration_preserves_existing_rows_sales_and_showcase(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE inventory_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT INTO inventory_metadata VALUES('seed_version','1');
            CREATE TABLE products(id INTEGER PRIMARY KEY,position TEXT,article TEXT,name TEXT,volume TEXT,expiry TEXT,
                central_bank_price TEXT,wholesale_price TEXT,market_price TEXT,showcase_quantity INTEGER DEFAULT 0);
            INSERT INTO products VALUES(77,'90','0007','Крем','30 мл','05.2028','100,25','—','—',2);
            CREATE TABLE product_units(id INTEGER PRIMARY KEY,product_id INTEGER,number INTEGER,sold INTEGER,
                UNIQUE(product_id,number));
            INSERT INTO product_units VALUES(300,77,1,1),(301,77,2,1),(302,77,3,0),(303,77,4,0),(304,77,5,0);
        """)
        before = {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in ("products", "product_units")
        }
    repository = InventoryRepository(path)

    first = repository.snapshot()
    second = repository.snapshot()

    assert first == second
    assert first.sold == 2 and first.total == 5 and first.showcase_quantity == 2
    assert first.sales == first.history == ()
    with sqlite3.connect(path) as connection:
        assert {table: connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in before} == before
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.fixture
def web(authenticated_client, repository, product, monkeypatch):
    monkeypatch.setattr(application.routes.one_alma, "repository", repository)
    match = re.search(r'data-csrf-token="([^"]+)"', authenticated_client.get("/one_alma").text)
    assert match is not None
    return authenticated_client, match.group(1)


def test_sale_history_cancel_endpoints_and_pdf(web, repository, product):
    client, csrf = web
    body = dict(quantity="1", customer="<b>Макс & компания</b>", unit_price="80,25", request_id=str(uuid4()), csrf_token=csrf)

    sold = client.post(f"/one_alma/products/{product.id}/sales", data=body)
    history = client.get(f"/one_alma/products/{product.id}/history")
    sale = repository.snapshot().sales[-1]
    cancelled = client.post(f"/one_alma/sales/{sale.id}/cancel", data={"csrf_token": csrf})
    pdf = client.get("/one_alma/pdf?sort=9&descending=true")

    assert sold.status_code == history.status_code == cancelled.status_code == pdf.status_code == 200
    assert history.headers["cache-control"] == "no-store"
    entry = next(e for e in history.json()["entries"] if e["sale_id"] == sale.id)
    assert entry["can_cancel"] and entry["values"][3] == body["customer"]
    assert cancelled.json()["products"][-1]["sold"] == 0
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert "История изменений" in text and "Макс & компания" in text and "80,25" in text
    assert "Отмена продажи" in text
    assert "-80,25" in text
    assert "Москва, UTC+3" not in text and "Отмены сохранены отдельными строками" not in text


def test_actual_excel_import_keeps_recorded_sale_and_ignores_history_and_showcase_columns(web, repository, product):
    client, csrf = web
    repository.set_showcase_quantity(product.id, 2)
    before = sell(repository, product)
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(
        [
            "№",
            "Артикул",
            "Наименование",
            "Объём",
            "Годен до",
            "Цена ЦБ",
            "Цена опт",
            "Цена магазина",
            "Количество",
            "Витрина",
            "Кому",
            "Продано",
        ]
    )
    sheet.append([26, "0007", "Крем после импорта", "30 мл", "05.2028", 500, None, None, 5, 5, "Из Excel", 5])
    content = BytesIO()
    workbook.save(content)
    workbook.close()

    response = client.post(
        "/one_alma/import",
        data={"csrf_token": csrf},
        files={
            "file": ("products.xlsx", content.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        },
    )
    after = repository.snapshot()

    assert response.status_code == 201
    assert after.sales == before.sales
    assert after.products[-1].showcase_quantity == 2 and after.products[-1].sold_count == 1
    assert len(after.products[-1].units) == 5 and after.products[-1].cells[5] == "500,00"
    assert after.sales[-1].customer == "Макс" and after.sales[-1].price_cents == 7999


@pytest.mark.parametrize("route", ["sale", "cancel"])
def test_new_mutations_require_csrf_and_preserve_data(web, repository, product, route):
    client, _ = web
    before = repository.snapshot()
    path = f"/one_alma/products/{product.id}/sales" if route == "sale" else "/one_alma/sales/1/cancel"
    body = dict(quantity="1", unit_price="80", customer="", request_id=str(uuid4()), csrf_token="wrong")

    response = client.post(path, data=body)

    assert response.status_code == 403
    assert repository.snapshot() == before


@pytest.mark.parametrize(
    "method,path",
    [("GET", "/one_alma/products/1/history"), ("POST", "/one_alma/products/1/sales"), ("POST", "/one_alma/sales/1/cancel")],
)
def test_new_endpoints_require_authentication(client, method, path):
    response = client.request(method, path, follow_redirects=False)

    assert response.status_code in (303, 401)


def test_pdf_has_history_and_actual_prices_after_product_edit(repository, product, item):
    sell(repository, product, 2, "Покупатель", "80")
    repository.update_product(product.id, replace(item, central_bank_price="500"))
    inventory = repository.snapshot().sorted_by(0, True)

    content = InventoryPdfExporter().export(inventory)

    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)
    assert "Покупатель" in text and "160,00" in text and "80,00" in text
    assert inventory.sales_amount == "160,00"
