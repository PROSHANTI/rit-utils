import re
from io import BytesIO

import pytest
from openpyxl import Workbook
from pypdf import PdfReader

from src.main import application
from src.utils.one_alma.repository import InventoryRepository


@pytest.fixture
def inventory_repository(tmp_path, monkeypatch):
    repository = InventoryRepository(tmp_path / "inventory.sqlite3")
    monkeypatch.setattr(application.routes.one_alma, "repository", repository)
    return repository


@pytest.fixture
def csrf(authenticated_client, inventory_repository):
    response = authenticated_client.get("/one_alma")
    assert response.status_code == 200
    match = re.search(r'data-csrf-token="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def product_data(csrf):
    return dict(
        position="26",
        article="0007",
        name="Новый крем",
        volume="50 мл",
        expiry="2028-09",
        central_bank_price="100,25",
        wholesale_price="200",
        market_price="300",
        quantity="3",
        csrf_token=csrf,
    )


def test_page_home_card_and_button_placement(authenticated_client, inventory_repository):
    home = authenticated_client.get("/home").text
    assert "Учет OneAlma" in home and "Учет продажи товаров" in home
    response = authenticated_client.get("/one_alma")
    html = response.text
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert html.count("data-unit-id=") == 50
    assert "Штука 1" in html and "Штука 2" in html
    assert "Продано: 0 из 2" in html
    assert "Каждый чекбокс —" not in html and "Изменения сохраняются автоматически." not in html
    assert html.index("Денежные итоги") < html.index("Скачать PDF") < html.index('class="inventory-table"')
    assert "Импорт товаров" in html and "Удалить выбранные" in html
    assert "Без цены: 4 шт." in html
    assert len(re.findall("data-sort-column=", html)) == 9


def test_sale_endpoint_counts_one_unit_and_two_units(authenticated_client, inventory_repository, csrf):
    units = inventory_repository.snapshot().products[0].units
    second = authenticated_client.post(f"/one_alma/units/{units[1].id}", data={"sold": "true", "csrf_token": csrf})
    assert second.status_code == 200
    assert second.json()["available"] == 49
    assert second.json()["products"][0]["available"] == 1
    assert second.json()["valuations"][0]["amounts"][1] == "1 343,43"
    both = authenticated_client.post(f"/one_alma/units/{units[0].id}", data={"sold": "true", "csrf_token": csrf})
    assert both.json()["products"][0]["available"] == 0
    page = authenticated_client.get("/one_alma").text
    assert "Продано: 2 из 2" in page


def test_crud_endpoints_create_edit_and_bulk_delete(authenticated_client, inventory_repository, csrf):
    response = authenticated_client.post("/one_alma/products", data=product_data(csrf))
    assert response.status_code == 201
    added = inventory_repository.snapshot().products[-1]
    assert inventory_repository.snapshot().total == 53
    read_page = authenticated_client.get("/one_alma")
    assert read_page.status_code == 200
    assert "Новый крем" in read_page.text
    assert "0007" in read_page.text
    data = product_data(csrf) | {"name": "Изменённый крем", "quantity": "4"}
    response = authenticated_client.put(f"/one_alma/products/{added.id}", data=data)
    assert response.status_code == 200
    assert inventory_repository.snapshot().products[-1].cells[2] == "Изменённый крем"
    response = authenticated_client.request(
        "DELETE", "/one_alma/products", data={"product_ids": [added.id, 1], "csrf_token": csrf}
    )
    assert response.status_code == 200
    assert len(inventory_repository.snapshot().products) == 24
    assert inventory_repository.snapshot().total == 48


def test_delete_one_product_removes_its_sales_and_survives_reopen(authenticated_client, inventory_repository, csrf):
    first = inventory_repository.snapshot().products[0]
    authenticated_client.post(f"/one_alma/units/{first.units[0].id}", data={"sold": "true", "csrf_token": csrf})
    response = authenticated_client.request("DELETE", "/one_alma/products", data={"product_ids": [first.id], "csrf_token": csrf})
    assert response.status_code == 200
    reopened = InventoryRepository(inventory_repository.database).snapshot()
    assert (len(reopened.products), reopened.total, reopened.sold, reopened.available) == (24, 48, 0, 48)
    assert all(product.id != first.id for product in reopened.products)


def test_edit_cannot_reduce_quantity_below_sales(authenticated_client, inventory_repository, csrf):
    first = inventory_repository.snapshot().products[0]
    for unit in first.units:
        authenticated_client.post(f"/one_alma/units/{unit.id}", data={"sold": "true", "csrf_token": csrf})
    response = authenticated_client.put(f"/one_alma/products/{first.id}", data=product_data(csrf) | {"quantity": "1"})
    assert response.status_code == 422
    unchanged = inventory_repository.snapshot().products[0]
    assert unchanged.cells == first.cells
    assert unchanged.sold_count == 2


def test_csrf_rejects_mutations_without_changing_database(authenticated_client, inventory_repository, csrf):
    response = authenticated_client.post("/one_alma/units/1", data={"sold": "true", "csrf_token": "wrong"})
    assert response.status_code == 403
    response = authenticated_client.post("/one_alma/products", data=product_data("wrong"))
    assert response.status_code == 403
    response = authenticated_client.request("DELETE", "/one_alma/products", data={"product_ids": [1], "csrf_token": "wrong"})
    assert response.status_code == 403
    assert inventory_repository.snapshot().total == 50
    assert inventory_repository.snapshot().sold == 0


def test_duplicate_position_and_invalid_fields_do_not_mutate(authenticated_client, inventory_repository, csrf):
    response = authenticated_client.post("/one_alma/products", data=product_data(csrf) | {"position": "1"})
    assert response.status_code == 409
    response = authenticated_client.post("/one_alma/products", data=product_data(csrf) | {"market_price": "-1"})
    assert response.status_code == 422
    response = authenticated_client.post("/one_alma/products", data=product_data(csrf) | {"quantity": "-1"})
    assert response.status_code == 422
    assert inventory_repository.snapshot().total == 50


def test_pdf_returns_snapshot_and_matches_selected_sort(authenticated_client, inventory_repository, csrf):
    authenticated_client.post("/one_alma/units/1", data={"sold": "true", "csrf_token": csrf})
    response = authenticated_client.get("/one_alma/pdf?sort=0&descending=true")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
    assert "Продано: 1." in text and "1 343,43" in text
    assert authenticated_client.get("/one_alma/pdf?sort=99").status_code == 422


def test_excel_upload_adds_products_and_rejects_duplicate_without_partial_write(
    authenticated_client, inventory_repository, csrf
):
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["№", "Артикул", "Наименование", "Объём", "Годен до", "Цена ЦБ", "Цена опт", "Цена магазина", "Количество"])
    sheet.append([26, "0001", "Крем из Excel", "50 мл", "09.2028", 100, 200, 300, 4])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    response = authenticated_client.post(
        "/one_alma/import",
        data={"csrf_token": csrf},
        files={
            "file": ("products.xlsx", output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        },
    )
    assert response.status_code == 201
    assert inventory_repository.snapshot().total == 54
    assert inventory_repository.snapshot().products[-1].cells[1] == "0001"
    duplicate = authenticated_client.post(
        "/one_alma/import", data={"csrf_token": csrf}, files={"file": ("products.xlsx", output.getvalue())}
    )
    assert duplicate.status_code == 409
    assert inventory_repository.snapshot().total == 54


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/one_alma"),
        ("GET", "/one_alma/pdf"),
        ("POST", "/one_alma/units/1"),
        ("POST", "/one_alma/products"),
        ("PUT", "/one_alma/products/1"),
        ("DELETE", "/one_alma/products"),
        ("POST", "/one_alma/import"),
    ],
)
def test_unauthenticated_routes_reject_access_and_do_not_create_db(client, inventory_repository, method, path):
    response = client.request(method, path, follow_redirects=False)
    assert response.status_code in (303, 401, 422)
    assert not inventory_repository.database.exists()
