import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from openpyxl import Workbook
from pydantic import ValidationError
from pypdf import PdfReader

from src.main import application
from src.utils.inventory.excel_import import InventoryExcelImporter
from src.utils.inventory.models import ExpiryPolicy, InventoryItem, StoredItem
from src.utils.inventory.ordering import InventoryOrdering
from src.utils.inventory.pdf_export import InventoryPdfExporter
from src.utils.inventory.repository import InventoryRepository


@pytest.fixture
def store(tmp_path, monkeypatch):
    repository = InventoryRepository(tmp_path / "inventory.sqlite3")
    monkeypatch.setattr(application.routes.inventory, "repository", repository)
    return repository


@pytest.fixture
def headers(authenticated_client, store):
    response = authenticated_client.get("/inventory")
    assert response.status_code == 200
    token = re.search(r'data-csrf-token="([^"]+)"', response.text)
    assert token
    return {"X-CSRF-Token": token[1]}


def item(**overrides):
    return InventoryItem(
        article="0001",
        name="Крем",
        brand="Бренд",
        expiry="09.2026",
        quantity=2,
        purchase_price="1200 ₽",
        sale_price="2000 ₽",
        **overrides,
    )


def workbook(*rows, headers=None, broken_style=False):
    book = Workbook()
    sheet = book.active
    assert sheet
    sheet.append(["Состояние склада Все"])
    sheet.append([])
    sheet.append(headers or ["Артикул", "Наименование", "Ед. Изм.", "Цена", "Кол-во", "На сумму", "Вал.", "Крит. остаток"])
    for row in rows:
        sheet.append(row)
    out = BytesIO()
    book.save(out)
    book.close()
    if not broken_style:
        return out.getvalue()
    modified = BytesIO()
    with ZipFile(BytesIO(out.getvalue())) as source, ZipFile(modified, "w") as target:
        for name in source.namelist():
            value = source.read(name)
            if name == "xl/styles.xml":
                value = (
                    value.replace(b"<fgColor", b'<fgColor rgb="invalid"', 1)
                    if b"<fgColor" in value
                    else value.replace(b"<patternFill/>", b'<patternFill><fgColor rgb="invalid"/></patternFill>', 1)
                )
            target.writestr(name, value)
    return modified.getvalue()


def test_empty_database_is_separate_and_persists_edits(store):
    assert store.items() == [] and store.history() == []
    first = store.add(item())
    store.update(first, item().model_copy(update={"name": "Новое название"}))
    reopened = InventoryRepository(store.database)
    assert reopened.items()[0].name == "Новое название"
    store.delete(first)
    assert store.add(item()) > first


def test_backups_contain_previous_state_and_can_be_restored(store):
    first = store.add(item())
    snapshot_id = store.create_snapshot()
    store.set_quantity(first, quantity=4000)
    backup = sorted(store.backup_directory.glob("*.sqlite3"))[-1]
    restored = InventoryRepository(backup)
    assert restored.items()[0].quantity == 2
    assert restored.history()[0]["id"] == snapshot_id
    assert store.items()[0].quantity == 4000


def test_backup_failure_prevents_write(store, monkeypatch):
    first = store.add(item())

    def fail():
        raise OSError("Unavailable backup disk")

    monkeypatch.setattr(store, "_backup", fail)
    with pytest.raises(OSError):
        store.set_quantity(first, quantity=99)
    assert store.items()[0].quantity == 2


def test_backup_retention(store):
    store.backup_limit = 3
    first = store.add(item())
    for _ in range(6):
        store.set_quantity(first, delta=1)
    assert len(list(store.backup_directory.glob("*.sqlite3"))) == 3


def test_quantity_has_no_stock_cap_and_increments_are_atomic(store):
    first = store.add(item())
    store.set_quantity(first, quantity=10**10)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: store.set_quantity(first, delta=1), range(12)))
    assert store.items()[0].quantity == 10**10 + 12
    store.set_quantity(first, quantity=0)
    with pytest.raises(ValidationError):
        store.set_quantity(first, delta=-1)
    assert store.items()[0].quantity == 0


def test_history_is_immutable_and_deleted_intervals_rejoin(store):
    first = store.add(item())
    one = store.create_snapshot()
    store.update(first, item().model_copy(update={"name": "Изменён", "quantity": 14}))
    two = store.create_snapshot()
    three = store.create_snapshot()
    history = store.history()
    oldest = history[-1]
    assert json.loads(oldest["products_json"])[0]["name"] == "Крем"
    assert json.loads(oldest["products_json"])[0]["quantity"] == 2
    assert oldest["ended_at"] == history[-2]["created_at"]
    store.delete_snapshot(two)
    history = store.history()
    assert history[-1]["ended_at"] == history[0]["created_at"]
    store.delete_snapshot(three)
    assert store.history()[0]["id"] == one
    assert store.history()[0]["ended_at"] is None
    assert store.items()[0].quantity == 14


@pytest.mark.parametrize(
    ("expiry", "today", "status"),
    [
        ("09.2026", date(2026, 9, 30), "soon"),
        ("09.2026", date(2026, 10, 1), "expired"),
        ("04.2027", date(2026, 10, 26), "normal"),
        ("04.2027", date(2026, 10, 30), "soon"),
        ("02.2028", date(2027, 8, 31), "soon"),
        ("", date(2026, 10, 26), "normal"),
    ],
)
def test_expiry_uses_six_calendar_months_and_month_end(expiry, today, status):
    assert ExpiryPolicy.status(expiry, today) == status


@pytest.mark.parametrize(
    "field,value",
    [
        ("article", "12A"),
        ("article", "1" * 65),
        ("brand", "a" * 256),
        ("name", ""),
        ("quantity", -1),
        ("quantity", 1.5),
        ("quantity", True),
        ("expiry", "13.2026"),
        ("expiry", "00.0000"),
    ],
)
def test_invalid_fields_rejected(field, value):
    data = item().model_dump() | {field: value}
    with pytest.raises(ValidationError):
        InventoryItem(**data)


def test_64_digit_article_and_text_prices_are_preserved():
    data = item().model_dump() | {"article": "0" + "9" * 63, "sale_price": "По запросу"}
    assert InventoryItem(**data).article == data["article"]
    assert InventoryItem(**data).sale_price == "По запросу"


def test_warehouse_export_headers_third_row_and_empty_article():
    content = workbook([None, "Крем", "шт.", 6000, 2.0, 12000, "руб.", 9], ["Итого:", None, None, None, 2])
    result = InventoryExcelImporter().parse(content, "Инвент.xlsx")
    assert len(result) == 1
    assert result[0].article == "" and result[0].quantity == 2
    assert result[0].sale_price == "6000" and result[0].purchase_price == ""
    assert "expiry" not in result[0].model_fields_set


def test_broken_rgb_styles_are_repaired_in_memory():
    content = workbook(["0007", "Крем", "шт.", 6000, 2, 12000, "руб.", 9], broken_style=True)
    assert InventoryExcelImporter().parse(content, "stock.xlsx")[0].article == "0007"


@pytest.mark.parametrize("bad_quantity", [1.5, -2, "=1+1", "нет"])
def test_invalid_excel_is_rejected_before_any_write(bad_quantity, store):
    content = workbook(["0001", "Крем", "шт.", 1, 4], ["0002", "Сыворотка", "шт.", 1, bad_quantity])
    with pytest.raises(ValueError, match="Строка 5"):
        InventoryExcelImporter().parse(content, "stock.xlsx")
    assert store.items() == []


def test_upsert_by_article_preserves_id_and_fields_missing_from_excel(store):
    first = store.add(item())
    imported = InventoryExcelImporter().parse(
        workbook(["0001", "Новое название", "шт.", 900, 8], ["0002", "Новинка", "шт.", 800, 1]), "stock.xlsx"
    )
    preview = store.preview_import(imported)
    assert preview["added"] == preview["updated"] == 1
    assert store.items()[0].quantity == 2
    result = store.import_items(imported, preview["fingerprint"])
    assert result == {"added": 1, "updated": 1}
    updated = store.items()[0]
    assert updated.id == first and updated.quantity == 8 and updated.name == "Новое название"
    assert updated.brand == "Бренд" and updated.expiry == "09.2026" and updated.purchase_price == "1200 ₽"
    preview = store.preview_import(imported)
    store.import_items(imported, preview["fingerprint"])
    assert len(store.items()) == 2 and store.items()[0].quantity == 8


def test_import_blocks_duplicate_articles_and_stale_preview(store):
    first = store.add(item())
    with pytest.raises(ValueError, match="повторяется"):
        store.preview_import([item(), item()])
    preview = store.preview_import([item()])
    store.set_quantity(first, quantity=19)
    with pytest.raises(ValueError, match="изменилась"):
        store.import_items([item()], preview["fingerprint"])
    assert store.items()[0].quantity == 19
    store.add(item())
    with pytest.raises(ValueError, match="нескольких"):
        store.preview_import([item()])


def test_import_is_atomic_on_storage_failure(store):
    good = item()
    # model_copy can deliberately bypass validation to simulate a downstream write failure.
    bad = item().model_copy(update={"article": "0002", "quantity": -1})
    plan = store.preview_import([good, bad])
    with pytest.raises(sqlite3.IntegrityError):
        store.import_items([good, bad], plan["fingerprint"])
    assert store.items() == []


def test_page_actions_editing_history_and_pdf_end_to_end(authenticated_client, store, headers):
    page = authenticated_client.get("/inventory")
    assert page.headers["cache-control"] == "no-store"
    assert "Инвентаризация" in authenticated_client.get("/home").text
    assert "inventory-stats" not in page.text and "Учет продажи товаров" not in page.text
    client = authenticated_client
    result = client.post("/inventory/products", json=item().model_dump(), headers=headers)
    assert result.status_code == 201
    product = client.get("/inventory/items").json()["items"][0]
    item_id = product["id"]
    assert (
        client.put(f"/inventory/products/{item_id}", json=item().model_dump() | {"name": "Новое"}, headers=headers).status_code
        == 200
    )
    assert client.post(f"/inventory/products/{item_id}/quantity", json={"quantity": "10000"}, headers=headers).status_code == 200
    snapshot = client.post("/inventory/snapshots", headers=headers).json()["id"]
    assert client.post(f"/inventory/products/{item_id}/quantity", json={"delta": 1}, headers=headers).status_code == 200
    history = client.get("/inventory/history").json()["snapshots"]
    assert history[0]["items"][0]["quantity"] == "10000"
    assert history[0]["items"][0]["name"] == "Новое"
    pdf = client.get("/inventory/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert "Инвентаризация" in text and "Новое" in text and "10001" in text
    assert client.delete(f"/inventory/history/{snapshot}", headers=headers).status_code == 200
    assert store.history() == [] and store.items()[0].quantity == 10001
    assert client.delete(f"/inventory/products/{item_id}", headers=headers).status_code == 200
    assert client.put(f"/inventory/products/{item_id}", json=item().model_dump(), headers=headers).status_code == 404


def test_import_preview_endpoint_does_not_write_and_commit_upserts(authenticated_client, store, headers):
    content = workbook(["0001", "Крем", "шт.", 7, 9])
    upload = {"file": ("stock.xlsx", content)}
    preview = authenticated_client.post("/inventory/import", files=upload, headers=headers)
    assert preview.status_code == 200 and store.items() == []
    commit = authenticated_client.post(
        "/inventory/import", files=upload, headers=headers, data={"fingerprint": preview.json()["preview"]["fingerprint"]}
    )
    assert commit.status_code == 201
    assert store.items()[0].quantity == 9


def test_pdf_appends_every_complete_snapshot_after_current_stock(authenticated_client, store, headers):
    first = store.add(item())
    one = store.create_snapshot()
    store.update(first, item().model_copy(update={"name": "Второе состояние", "quantity": 11}))
    two = store.create_snapshot()
    store.update(first, item().model_copy(update={"name": "Текущее состояние", "quantity": 999}))
    response = authenticated_client.get("/inventory/pdf")
    reader = PdfReader(BytesIO(response.content))
    texts = [page.extract_text() for page in reader.pages]
    assert "Текущее состояние" in texts[0] and "999" in texts[0]
    history_text = "".join(texts[1:])
    assert "Истории инвентаризации" in history_text
    assert f"#{one}" in history_text and f"#{two}" in history_text
    assert "Второе состояние" in history_text and "Крем" in history_text
    assert "Закупочная стоимость" in " ".join(history_text.split()) and "09.2026" in history_text
    assert "Текущее состояние" not in history_text


def test_csrf_auth_and_missing_resources(authenticated_client, client, store, headers):
    assert authenticated_client.post("/inventory/products", json=item().model_dump()).status_code == 403
    assert authenticated_client.post("/inventory/snapshots", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert authenticated_client.delete("/inventory/history/999", headers=headers).status_code == 404
    assert (
        authenticated_client.post("/inventory/products/999/quantity", json={"quantity": 1}, headers=headers).status_code == 404
    )
    for path in ("/inventory", "/inventory/items", "/inventory/history", "/inventory/pdf"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code in (302, 303, 401)
    assert store.items() == []


def test_pdf_includes_all_rows_over_multiple_pages_and_escapes_text():
    items = [StoredItem(id=i, **(item().model_dump() | {"name": f"Крем <b> & {i}"})) for i in range(1, 90)]
    reader = PdfReader(BytesIO(InventoryPdfExporter().export(items)))
    text = "".join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) > 1 and "Крем <b> & 89" in text
    assert "Срок годности" in text and "Количество" in text


def test_demo_session_is_isolated_from_working_login_and_rejects_untrusted_host(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("INVENTORY_DEMO_DB_PATH", str(tmp_path / "demo.sqlite3"))
    from src.inventory_demo import InventoryDemoApplication

    with TestClient(InventoryDemoApplication().app) as demo:
        response = demo.get("/inventory")
        assert response.status_code == 200
        assert "INVENTORY_DEMO_SESSION" in demo.cookies
        assert "JWT_ACCESS_TOKEN_COOKIE" not in demo.cookies
        assert demo.get("/inventory", headers={"host": "untrusted.example"}).status_code == 400
        token = re.search(r'data-csrf-token="([^"]+)"', response.text)
        assert token
        assert demo.post("/inventory/products", headers={"X-CSRF-Token": token[1]}, json=item().model_dump()).status_code == 201
        assert demo.post("/inventory/snapshots").status_code == 403
        assert "quantity-dialog" not in response.text


@pytest.mark.parametrize(
    "column,ascending,descending",
    [
        ("id", [2, 3, 10], [10, 3, 2]),
        ("article", [2, 10, 3], [10, 2, 3]),
        ("brand", [2, 10, 3], [10, 2, 3]),
        ("name", [2, 3, 10], [10, 3, 2]),
        ("purchase_price", [2, 10, 3], [10, 2, 3]),
        ("sale_price", [2, 10, 3], [10, 2, 3]),
        ("expiry", [2, 10, 3], [10, 2, 3]),
        ("quantity", [2, 3, 10], [10, 3, 2]),
    ],
)
def test_every_sort_column_uses_values_and_leaves_empty_cells_last(column, ascending, descending):
    rows = [
        StoredItem(
            id=10,
            article="100",
            name="Я",
            brand="Я",
            purchase_price="1 200,50 ₽",
            sale_price="100,5",
            expiry="01.2028",
            quantity=100,
        ),
        StoredItem(id=2, article="9", name="А", brand="А", purchase_price="9,99", sale_price="9", expiry="12.2026", quantity=2),
        StoredItem(id=3, name="М", quantity=12),
    ]
    assert [row.id for row in InventoryOrdering.apply(rows, column)] == ascending
    assert [row.id for row in InventoryOrdering.apply(rows, column, True)] == descending


def test_sorting_api_pdf_and_headers_share_the_same_order(authenticated_client, store, headers):
    first = store.add(item().model_copy(update={"name": "Больше", "quantity": 20}))
    second = store.add(item().model_copy(update={"name": "Меньше", "quantity": 2, "article": "0002"}))
    page = authenticated_client.get("/inventory").text
    assert page.count("data-sort=") == 8
    assert 'placeholder="09.2026"' not in page and "quantity-dialog" not in page
    response = authenticated_client.get("/inventory/items?sort=quantity&descending=false")
    assert [row["id"] for row in response.json()["items"]] == [second, first]
    pdf = authenticated_client.get("/inventory/pdf?sort=quantity&descending=false")
    text = PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
    assert text.index("Меньше") < text.index("Больше")
    assert authenticated_client.get("/inventory/items?sort=unknown").status_code == 422
