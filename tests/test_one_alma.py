import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.utils.one_alma.models import NewProduct
from src.utils.one_alma.pdf_export import InventoryPdfExporter
from src.utils.one_alma.repository import InventoryRepository


@pytest.fixture
def repository(tmp_path):
    return InventoryRepository(tmp_path / "data" / "one_alma.sqlite3")


@pytest.fixture
def new_product():
    return NewProduct(
        position=26,
        article="0007",
        name="Тестовый крем",
        volume="50 мл",
        expiry="2028-09",
        central_bank_price="100,25",
        wholesale_price="200.10",
        market_price="300",
        quantity=3,
    )


def test_first_request_creates_database_and_imports_exact_seed(repository):
    assert not repository.database.exists()
    inventory = repository.snapshot()
    assert repository.database.is_file()
    assert (len(inventory.products), inventory.total, inventory.sold, inventory.available) == (25, 50, 0, 50)
    assert inventory.products[12].cells[1] == "0262"
    assert inventory.products[0].cells[5:] == ("1343,43", "5429,52", "8920,00")
    assert inventory.valuations[0].total == Decimal("63946.54")
    assert inventory.valuations[1].total == Decimal("134952.20")
    assert inventory.valuations[1].unpriced == (4, 0, 4)
    assert inventory.valuations[2].total == Decimal("230233.92")


def test_second_checkbox_is_one_unit_and_both_checks_leave_zero(repository):
    product = repository.snapshot().products[0]
    second = repository.set_sold(product.units[1].id, True)
    assert (second.sold, second.available) == (1, 49)
    assert (second.products[0].sold_count, second.products[0].available) == (1, 1)
    assert second.valuations[0].sold == Decimal("1343.43")
    both = repository.set_sold(product.units[0].id, True)
    assert (both.sold, both.available) == (2, 48)
    assert both.products[0].available == 0
    assert both.valuations[0].sold == Decimal("2686.86")
    undone = repository.set_sold(product.units[1].id, False)
    assert undone.products[0].available == 1
    assert undone.sold == 1


def test_repeat_sale_is_idempotent_and_survives_new_repository(repository):
    unit = repository.snapshot().products[0].units[0]
    repository.set_sold(unit.id, True)
    repository.set_sold(unit.id, True)
    reopened = InventoryRepository(repository.database).snapshot()
    assert (reopened.total, reopened.sold, reopened.available) == (50, 1, 49)


def test_unknown_price_is_counted_separately_not_as_zero(repository):
    product = repository.snapshot().products[3]
    inventory = repository.set_sold(product.units[0].id, True)
    assert inventory.valuations[1].unpriced == (4, 1, 3)
    assert inventory.valuations[1].sold == 0
    assert inventory.valuations[0].sold == Decimal("305.50")


def test_concurrent_first_requests_seed_once_and_sales_do_not_lose_updates(tmp_path):
    path = tmp_path / "concurrent.sqlite3"
    with ThreadPoolExecutor(max_workers=4) as pool:
        inventories = list(pool.map(lambda _: InventoryRepository(path).snapshot(), range(4)))
        assert all(inventory.total == 50 for inventory in inventories)
        units = inventories[0].products[0].units
        list(pool.map(lambda unit: InventoryRepository(path).set_sold(unit.id, True), units))
    assert InventoryRepository(path).snapshot().sold == 2


def test_create_and_edit_preserve_sales_and_update_financial_totals(repository, new_product):
    repository.add_product(new_product)
    inventory = repository.snapshot()
    product = inventory.products[-1]
    assert (inventory.total, product.cells[1], product.cells[4]) == (53, "0007", "09.2028")
    repository.set_sold(product.units[2].id, True)
    repository.update_product(product.id, replace(new_product, name="Новый крем", quantity=1, central_bank_price="110.25"))
    edited = InventoryRepository(repository.database).snapshot()
    updated = edited.products[-1]
    assert updated.cells[2] == "Новый крем"
    assert (len(updated.units), updated.sold_count, updated.available) == (1, 1, 0)
    assert updated.units[0].id == product.units[2].id
    assert updated.units[0].number == 1
    assert edited.valuations[0].sold == Decimal("110.25")
    repository.update_product(product.id, replace(new_product, quantity=4))
    assert repository.snapshot().products[-1].sold_count == 1
    assert repository.snapshot().products[-1].available == 3


def test_quantity_cannot_be_lower_than_sold_and_change_rolls_back(repository, new_product):
    repository.add_product(new_product)
    product = repository.snapshot().products[-1]
    repository.set_sold(product.units[0].id, True)
    repository.set_sold(product.units[1].id, True)
    with pytest.raises(ValueError, match="меньше"):
        repository.update_product(product.id, replace(new_product, name="Не должно сохраниться", quantity=1))
    assert repository.snapshot().products[-1].cells[2] == new_product.name
    assert repository.snapshot().total == 53


def test_import_duplicate_position_rolls_back_entire_batch(repository, new_product):
    with pytest.raises(sqlite3.IntegrityError):
        repository.import_products([new_product, replace(new_product, position=1)])
    assert len(repository.snapshot().products) == 25
    assert repository.snapshot().total == 50


def test_bulk_delete_is_atomic_and_deleted_ids_are_not_reused(repository, new_product):
    initial = repository.snapshot()
    with pytest.raises(LookupError):
        repository.delete_products([initial.products[0].id, 9999])
    assert len(repository.snapshot().products) == 25
    repository.delete_products([product.id for product in initial.products])
    assert InventoryRepository(repository.database).snapshot().total == 0
    repository.add_product(new_product)
    product = repository.snapshot().products[0]
    assert product.id > initial.products[-1].id
    assert product.units[0].id > initial.products[-1].units[-1].id
    with pytest.raises(LookupError):
        repository.set_sold(initial.products[0].units[0].id, True)


@pytest.mark.parametrize("column", range(9))
@pytest.mark.parametrize("descending", [False, True])
def test_sort_preserves_all_products_and_totals(repository, column, descending):
    inventory = repository.snapshot()
    sorted_inventory = inventory.sorted_by(column, descending)
    assert {product.id for product in sorted_inventory.products} == {product.id for product in inventory.products}
    assert sorted_inventory.total == 50
    assert sorted_inventory.valuations == inventory.valuations


def test_numeric_date_and_sold_sort_order_and_missing_prices_last(repository):
    inventory = repository.snapshot()
    assert [product.cells[0] for product in inventory.sorted_by(0).products][:3] == ["1", "2", "3"]
    assert [product.cells[0] for product in inventory.sorted_by(0, True).products][:3] == ["25", "24", "23"]
    assert inventory.sorted_by(4).products[0].cells[4] == "04.2025"
    assert inventory.sorted_by(4, True).products[0].cells[4] == "10.2028"
    for descending in (True, False):
        assert all(product.cells[6] == "—" for product in inventory.sorted_by(6, descending).products[-2:])
    updated = repository.set_sold(inventory.products[5].units[0].id, True)
    assert updated.sorted_by(8, True).products[0].id == inventory.products[5].id


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity", "10,345", "=1+1", "abc"])
def test_invalid_prices_rejected_before_database_mutation(repository, new_product, price):
    with pytest.raises(ValueError):
        repository.add_product(replace(new_product, central_bank_price=price))
    assert not repository.database.exists()


def test_pdf_contains_every_product_and_current_counts_and_cb_amounts(repository):
    inventory = repository.snapshot()
    inventory = repository.set_sold(inventory.products[0].units[1].id, True)
    pdf = InventoryPdfExporter().export(inventory.sorted_by(0, True))
    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Всего товаров: 50. Продано: 1. В наличии: 49." in text
    assert "63 946,54" in text and "1 343,43" in text and "62 603,11" in text
    assert "Стоимость по цене ЦБ РФ" in text
    for product in inventory.products:
        assert product.cells[1] in text
        assert product.cells[2].split()[0] in text
    assert text.index(inventory.products[-1].cells[2].split()[0]) < text.index(inventory.products[0].cells[2].split()[0])


def test_pdf_can_export_empty_inventory(repository):
    repository.delete_products([product.id for product in repository.snapshot().products])
    pdf = InventoryPdfExporter().export(repository.snapshot())
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "Всего товаров: 0" in text
