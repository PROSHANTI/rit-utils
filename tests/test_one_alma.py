import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.utils.one_alma.models import ImportResult, NewProduct
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
    existed_before = repository.database.exists()

    inventory = repository.snapshot()

    assert not existed_before
    assert repository.database.is_file()
    assert (len(inventory.products), inventory.total, inventory.sold, inventory.available) == (25, 50, 0, 50)
    assert inventory.products[12].cells[1] == "0262"
    assert inventory.products[0].cells[5:] == ("1343,43", "5429,52", "8920,00")
    assert inventory.valuations[0].total == Decimal("63946.54")
    assert inventory.valuations[1].total == Decimal("134952.20")
    assert inventory.valuations[1].unpriced == (4, 0, 4)
    assert inventory.valuations[2].total == Decimal("230233.92")


@pytest.mark.parametrize("indices, sold, available, amount", [([1], 1, 1, "1343.43"), ([1, 0], 2, 0, "2686.86")])
def test_checkboxes_count_individual_units(repository, indices, sold, available, amount):
    product = repository.snapshot().products[0]

    inventories = [repository.set_sold(product.units[index].id, True) for index in indices]

    inventory = inventories[-1]
    assert (inventory.sold, inventory.available) == (sold, 50 - sold)
    assert (inventory.products[0].sold_count, inventory.products[0].available) == (sold, available)
    assert inventory.valuations[0].sold == Decimal(amount)


def test_unchecking_sale_restores_one_available_unit(repository):
    product = repository.snapshot().products[0]
    for unit in product.units:
        repository.set_sold(unit.id, True)

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


def test_concurrent_first_requests_seed_once(tmp_path):
    path = tmp_path / "concurrent.sqlite3"

    with ThreadPoolExecutor(max_workers=4) as pool:
        inventories = list(pool.map(lambda _: InventoryRepository(path).snapshot(), range(4)))

    assert all(inventory.total == 50 for inventory in inventories)


def test_concurrent_sales_do_not_lose_updates(repository):
    units = repository.snapshot().products[0].units

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda unit: InventoryRepository(repository.database).set_sold(unit.id, True), units))

    assert InventoryRepository(repository.database).snapshot().sold == 2


def test_create_adds_product_fields_and_quantity(repository, new_product):
    repository.add_product(new_product)

    inventory = repository.snapshot()
    product = inventory.products[-1]
    assert (inventory.total, product.cells[1], product.cells[4]) == (53, "0007", "09.2028")


def test_edit_preserves_sales_and_updates_financial_totals(repository, new_product):
    repository.add_product(new_product)
    product = repository.snapshot().products[-1]
    repository.set_sold(product.units[2].id, True)

    repository.update_product(product.id, replace(new_product, name="Новый крем", quantity=1, central_bank_price="110.25"))

    edited = InventoryRepository(repository.database).snapshot()
    updated = edited.products[-1]
    assert updated.cells[2] == "Новый крем"
    assert (len(updated.units), updated.sold_count, updated.available) == (1, 1, 0)
    assert updated.units[0].id == product.units[2].id
    assert updated.units[0].number == 1
    assert edited.valuations[0].sold == Decimal("110.25")


def test_edit_increases_quantity_without_resetting_sales(repository, new_product):
    repository.add_product(new_product)
    product = repository.snapshot().products[-1]
    repository.set_sold(product.units[2].id, True)

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


def test_import_matches_article_volume_expiry_and_preserves_existing_fields(repository, new_product):
    repository.add_product(new_product)
    first = repository.snapshot().products[-1]
    before = repository.set_showcase_quantity(first.id, 2)
    incoming = replace(new_product, position=999, name="Новое имя", quantity=2, central_bank_price="500")

    result = repository.import_products([incoming, replace(new_product, article="NEW")])

    inventory = repository.snapshot()
    updated = inventory.products[-2]
    assert result == ImportResult(added=1, updated=1)
    assert (len(inventory.products), inventory.total) == (27, before.total + 5)
    assert updated.cells == first.cells
    assert updated.units[:3] == first.units
    assert len(updated.units) == 5 and updated.showcase_quantity == 2
    assert inventory.products[-1].cells[:2] == ("27", "NEW")
    assert inventory.products[:-2] == before.products[:-1]


def test_repeat_import_preserves_sales_unit_ids_and_sequences(repository, new_product):
    repository.import_products([new_product])
    added = repository.snapshot().products[-1]
    before = repository.set_sold(added.units[-1].id, True)
    with sqlite3.connect(repository.database) as connection:
        stored_before = list(connection.iterdump())

    result = repository.import_products([new_product])

    assert result == ImportResult(added=0, updated=0, already_imported=True)
    assert repository.snapshot() == before
    with sqlite3.connect(repository.database) as connection:
        assert list(connection.iterdump()) == stored_before


@pytest.mark.parametrize("quantity", [1, 5])
def test_import_adds_to_total_and_keeps_sold_units(repository, new_product, quantity):
    repository.add_product(new_product)
    original = repository.snapshot().products[-1]
    sold_unit = original.units[-1]
    repository.set_sold(sold_unit.id, True)
    changed = replace(new_product, quantity=quantity, central_bank_price="110.25")

    result = repository.import_products([changed])

    inventory = repository.snapshot()
    updated = inventory.products[-1]
    assert result == ImportResult(added=0, updated=1)
    assert updated.id == original.id
    assert (len(updated.units), updated.sold_count, updated.available) == (3 + quantity, 1, 2 + quantity)
    assert [unit.number for unit in updated.units] == list(range(1, 4 + quantity))
    assert next(unit for unit in updated.units if unit.sold).id == sold_unit.id
    assert inventory.valuations[0].sold == Decimal("100.25")
    assert all(unit.id > sold_unit.id and not unit.sold for unit in updated.units[3:])


@pytest.mark.parametrize("changes", [{"expiry": "10.2028"}, {"volume": "100 мл"}, {"article": "007"}])
def test_different_batch_gets_separate_automatic_position(repository, new_product, changes):
    repository.add_product(new_product)
    before = repository.snapshot()

    result = repository.import_products([replace(new_product, position=1, **changes)])

    after = repository.snapshot()
    assert result == ImportResult(added=1, updated=0)
    assert after.products[:-1] == before.products
    assert after.products[-1].cells[0] == "27"
    assert after.total == before.total + 3


def test_repeated_composite_key_inside_file_is_combined_without_using_position(repository, new_product):
    before = repository.snapshot()

    result = repository.import_products([new_product, replace(new_product, position=1, quantity=2)])

    after = repository.snapshot()
    assert result == ImportResult(added=1, updated=0)
    assert len(after.products) == len(before.products) + 1
    assert len(after.products[-1].units) == 5


def test_overflow_rolls_back_additions_history_receipt_and_sequences(repository, new_product):
    repository.add_product(new_product)
    before = repository.snapshot()
    with sqlite3.connect(repository.database) as connection:
        stored_before = list(connection.iterdump())
    products = [replace(new_product, article="NEW"), replace(new_product, quantity=1000)]

    with pytest.raises(ValueError, match="больше 1000"):
        repository.import_products(products)

    assert repository.snapshot() == before
    with sqlite3.connect(repository.database) as connection:
        assert list(connection.iterdump()) == stored_before


def test_import_validates_all_fields_before_changing_database(repository, new_product):
    products = [new_product, replace(new_product, position=1, market_price="-1")]

    with pytest.raises(ValueError, match="Цена"):
        repository.import_products(products)

    assert not repository.database.exists()


def test_concurrent_imports_of_same_delivery_do_not_add_twice(repository, new_product):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: InventoryRepository(repository.database).import_products([new_product]), range(4)))

    inventory = repository.snapshot()
    assert sum(result.added for result in results) == 1
    assert sum(result.already_imported for result in results) == 3
    assert (len(inventory.products), inventory.total) == (26, 53)


def test_distinct_identical_deliveries_are_both_added(repository, new_product):
    repository.import_products([new_product], "delivery-one")

    result = repository.import_products([new_product], "delivery-two")

    assert result == ImportResult(added=0, updated=1)
    assert len(repository.snapshot().products[-1].units) == 6


def test_changed_previously_imported_delivery_is_rejected(repository, new_product):
    repository.import_products([new_product], "delivery-one")
    before = repository.snapshot()

    with pytest.raises(ValueError, match="другими данными"):
        repository.import_products([replace(new_product, quantity=2)], "delivery-one")

    assert repository.snapshot() == before


def test_concurrent_distinct_deliveries_do_not_lose_quantities(repository, new_product):
    repository.snapshot()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda n: InventoryRepository(repository.database).import_products([new_product], f"delivery-{n}"), range(4)
            )
        )

    assert sum(result.added for result in results) == 1
    assert sum(result.updated for result in results) == 3
    assert len(repository.snapshot().products[-1].units) == 12


def test_manual_creation_assigns_position_inside_transaction(repository, new_product):
    repository.snapshot()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(lambda _: InventoryRepository(repository.database).add_product(replace(new_product, position=1)), range(4))
        )

    assert [product.cells[0] for product in repository.snapshot().products[-4:]] == ["26", "27", "28", "29"]


def test_bulk_delete_is_atomic_when_any_product_is_missing(repository):
    initial = repository.snapshot()

    with pytest.raises(LookupError):
        repository.delete_products([initial.products[0].id, 9999])

    assert repository.snapshot() == initial


def test_bulk_delete_removes_all_selected_products(repository):
    initial = repository.snapshot()

    repository.delete_products([product.id for product in initial.products])

    assert InventoryRepository(repository.database).snapshot().total == 0


def test_deleted_product_and_unit_ids_are_not_reused(repository, new_product):
    initial = repository.snapshot()
    repository.delete_products([product.id for product in initial.products])

    repository.add_product(new_product)

    product = repository.snapshot().products[0]
    assert product.id > initial.products[-1].id
    assert product.units[0].id > initial.products[-1].units[-1].id


def test_deleted_unit_cannot_be_sold_after_adding_new_product(repository, new_product):
    initial = repository.snapshot()
    repository.delete_products([product.id for product in initial.products])
    repository.add_product(new_product)

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


@pytest.mark.parametrize(
    "column, descending, expected",
    [(0, False, ["1", "2", "3"]), (0, True, ["25", "24", "23"]), (4, False, ["04.2025"]), (4, True, ["10.2028"])],
)
def test_numeric_and_date_sort_order(repository, column, descending, expected):
    inventory = repository.snapshot()

    sorted_inventory = inventory.sorted_by(column, descending)

    assert [product.cells[column] for product in sorted_inventory.products][: len(expected)] == expected


@pytest.mark.parametrize("descending", [True, False])
def test_missing_prices_are_sorted_last(repository, descending):
    inventory = repository.snapshot()

    sorted_inventory = inventory.sorted_by(6, descending)

    assert all(product.cells[6] == "—" for product in sorted_inventory.products[-2:])


def test_sold_sort_order(repository):
    inventory = repository.snapshot()
    updated = repository.set_sold(inventory.products[5].units[0].id, True)

    sorted_inventory = updated.sorted_by(8, True)

    assert sorted_inventory.products[0].id == inventory.products[5].id


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity", "10,345", "=1+1", "abc"])
def test_invalid_prices_rejected_before_database_mutation(repository, new_product, price):
    invalid = replace(new_product, central_bank_price=price)

    with pytest.raises(ValueError):
        repository.add_product(invalid)

    assert not repository.database.exists()


def test_pdf_contains_every_product_and_current_counts_and_cb_amounts(repository):
    inventory = repository.snapshot()
    inventory = repository.set_sold(inventory.products[0].units[1].id, True)

    pdf = InventoryPdfExporter().export(inventory.sorted_by(0, True))

    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert pdf.startswith(b"%PDF-")
    assert "Всего товаров: 50. Продано: 1. В наличии: 49." in text
    assert "63 946,54" in text and "1 343,43" in text and "62 603,11" in text
    assert "Стоимость по цене ЦБ РФ" in text
    assert "Цена ЦБ, ₽" in text
    assert "Цена по ЦБ РФ на 27.05" not in text
    for product in inventory.products:
        assert product.cells[1] in text
        assert product.cells[2].split()[0] in text
    assert text.index(inventory.products[-1].cells[2].split()[0]) < text.index(inventory.products[0].cells[2].split()[0])


def test_pdf_can_export_empty_inventory(repository):
    repository.delete_products([product.id for product in repository.snapshot().products])

    pdf = InventoryPdfExporter().export(repository.snapshot())

    text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "Всего товаров: 0" in text
