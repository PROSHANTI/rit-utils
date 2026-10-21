import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.utils.one_alma.models import NewProduct
from src.utils.one_alma.pdf_export import InventoryPdfExporter
from src.utils.one_alma.repository import InventoryRepository


@pytest.fixture
def repository(tmp_path):
    return InventoryRepository(tmp_path / "inventory.sqlite3")


@pytest.fixture
def product(repository):
    repository.add_product(
        NewProduct(
            position=26,
            article="0007",
            name="Крем",
            volume="50 мл",
            expiry="09.2028",
            central_bank_price="100",
            wholesale_price="",
            market_price="",
            quantity=7,
        )
    )
    return repository.snapshot().products[-1]


def test_showcase_is_part_of_stock_and_preserves_prices_sales_and_ids(repository, product):
    before = repository.snapshot()

    changed = repository.set_showcase_quantity(product.id, 3)

    assert changed.total == before.total == 57
    assert changed.sold == before.sold == 0
    assert changed.available == before.available == 57
    assert changed.valuations == before.valuations
    assert changed.products[-1].units == product.units
    assert changed.products[-1].cells == product.cells
    assert changed.showcase_quantity == 3 and changed.showcased_products == 1
    assert InventoryRepository(repository.database).snapshot() == changed


def test_zero_clears_showcase_without_requiring_a_separate_flag(repository, product):
    repository.set_showcase_quantity(product.id, 3)

    cleared = repository.set_showcase_quantity(product.id, 0)

    assert cleared.showcase_quantity == cleared.showcased_products == 0
    assert cleared.products[-1].available == 7


@pytest.mark.parametrize("quantity", [-1, 8, 1.5, True])
@pytest.mark.parametrize("method", ["set_showcase_quantity", "set_sold_count"])
def test_invalid_counts_do_not_modify_inventory(repository, product, method, quantity):
    before = repository.snapshot()

    with pytest.raises(ValueError, match="целое количество"):
        getattr(repository, method)(product.id, quantity)

    assert repository.snapshot() == before


def test_showcase_cannot_use_already_sold_stock(repository, product):
    repository.set_sold_count(product.id, 5)
    before = repository.snapshot()

    with pytest.raises(ValueError, match="от 0 до 2"):
        repository.set_showcase_quantity(product.id, 3)

    assert repository.snapshot() == before


def test_sold_count_preserves_existing_sale_ids_and_is_idempotent(repository, product):
    repository.set_sold(product.units[-1].id, True)
    repository.set_showcase_quantity(product.id, 4)

    changed = repository.set_sold_count(product.id, 3)
    repeated = repository.set_sold_count(product.id, 3)

    saved = changed.products[-1]
    assert (changed.total, saved.sold_count, saved.available, saved.showcase_quantity) == (57, 3, 4, 4)
    assert saved.units[-1].sold
    assert [unit.id for unit in saved.units] == [unit.id for unit in product.units]
    assert repeated == changed == InventoryRepository(repository.database).snapshot()
    assert changed.valuations[0].sold == 300


def test_sold_count_can_be_reduced_without_changing_total_stock(repository, product):
    repository.set_sold_count(product.id, 5)

    changed = repository.set_sold_count(product.id, 2)

    assert (changed.total, changed.products[-1].sold_count, changed.products[-1].available) == (57, 2, 5)
    assert changed.products[-1].units[:2] == tuple(replace(unit, sold=True) for unit in product.units[:2])
    assert changed.products[-1].units[2:] == product.units[2:]


def test_last_sale_clears_showcase_and_keeps_product_and_sales_history(repository, product):
    repository.set_showcase_quantity(product.id, 4)

    changed = repository.set_sold_count(product.id, 7)

    saved = changed.products[-1]
    assert (saved.id, saved.sold_count, saved.available, saved.showcase_quantity) == (product.id, 7, 0, 0)
    assert len(changed.products) == 26
    assert all(unit.sold for unit in saved.units)
    assert changed.total == 57


def test_legacy_unit_sale_also_limits_showcase_to_available_stock(repository, product):
    repository.set_showcase_quantity(product.id, 7)

    changed = repository.set_sold(product.units[0].id, True)

    assert changed.products[-1].showcase_quantity == changed.products[-1].available == 6


@pytest.mark.parametrize("method", ["set_showcase_quantity", "set_sold_count"])
def test_deleted_product_cannot_be_changed_by_an_old_tab(repository, product, method):
    repository.delete_products([product.id])
    before = repository.snapshot()

    with pytest.raises(LookupError):
        getattr(repository, method)(product.id, 1)

    assert repository.snapshot() == before


@pytest.mark.parametrize("use_import", [False, True])
def test_quantity_reduction_keeps_showcase_within_new_remainder(repository, product, use_import):
    repository.set_sold_count(product.id, 1)
    repository.set_showcase_quantity(product.id, 5)
    updated = NewProduct(
        position=26,
        article="0007",
        name="Крем",
        volume="50 мл",
        expiry="09.2028",
        central_bank_price="100",
        wholesale_price="",
        market_price="",
        quantity=3,
    )

    if use_import:
        repository.import_products([updated])
    else:
        repository.update_product(product.id, updated)

    saved = repository.snapshot().products[-1]
    assert (len(saved.units), saved.sold_count, saved.available, saved.showcase_quantity) == (3, 1, 2, 2)


def test_concurrent_sale_and_showcase_updates_cannot_exceed_remainder(repository, product):
    repository.set_showcase_quantity(product.id, 7)

    with ThreadPoolExecutor(max_workers=2) as pool:
        sale = pool.submit(repository.set_sold_count, product.id, 7)
        showcase = pool.submit(repository.set_showcase_quantity, product.id, 7)
        sale.result()
        try:
            showcase.result()
        except ValueError:
            pass

    saved = repository.snapshot().products[-1]
    assert (saved.sold_count, saved.available, saved.showcase_quantity) == (7, 0, 0)


def test_failed_import_rolls_back_showcase_clamping_as_well_as_stock(repository, product):
    repository.set_showcase_quantity(product.id, 6)
    repository.set_sold_count(1, 2)
    before = repository.snapshot()
    changed = NewProduct(
        position=26,
        article="0007",
        name="Крем",
        volume="50 мл",
        expiry="09.2028",
        central_bank_price="100",
        wholesale_price="",
        market_price="",
        quantity=2,
    )

    with pytest.raises(ValueError, match="меньше"):
        repository.import_products([changed, replace(changed, position=1, quantity=1)])

    assert repository.snapshot() == before


@pytest.mark.parametrize("workers", [1, 4])
def test_old_database_migrates_without_losing_units_sales_or_sequences(repository, workers):
    with sqlite3.connect(repository.database) as connection:
        connection.executescript("""
            CREATE TABLE inventory_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO inventory_metadata VALUES ('seed_version','1'),('next_product_id','42'),('next_unit_id','300');
            CREATE TABLE products (id INTEGER PRIMARY KEY, position TEXT NOT NULL, article TEXT NOT NULL,
                name TEXT NOT NULL, volume TEXT NOT NULL, expiry TEXT NOT NULL, central_bank_price TEXT NOT NULL,
                wholesale_price TEXT NOT NULL, market_price TEXT NOT NULL);
            INSERT INTO products VALUES (41,'90','0007','Крем','50 мл','05.2028','100,00','—','—');
            CREATE TABLE product_units (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
                number INTEGER NOT NULL, sold INTEGER NOT NULL DEFAULT 0, UNIQUE(product_id,number));
            INSERT INTO product_units VALUES (298,41,1,1),(299,41,2,0);
        """)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        snapshots = list(pool.map(lambda _: InventoryRepository(repository.database).snapshot(), range(workers)))

    assert all(snapshot == snapshots[0] for snapshot in snapshots)
    saved = snapshots[0].products[0]
    assert (saved.id, saved.cells[1], saved.sold_count, saved.available, saved.showcase_quantity) == (41, "0007", 1, 1, 0)
    assert [unit.id for unit in saved.units] == [298, 299]
    with sqlite3.connect(repository.database) as connection:
        assert dict(connection.execute("SELECT key,value FROM inventory_metadata")) == {
            "seed_version": "1",
            "next_product_id": "42",
            "next_unit_id": "300",
        }


def test_showcase_sort_and_pdf_use_actual_quantity(repository, product):
    repository.set_showcase_quantity(product.id, 3)
    inventory = repository.snapshot()

    ordered = inventory.sorted_by(9, True)
    pdf = InventoryPdfExporter().export(ordered)

    text = " ".join(" ".join(page.extract_text().split()) for page in PdfReader(BytesIO(pdf)).pages)
    assert ordered.products[0].id == product.id
    assert ordered.total == inventory.total and ordered.valuations == inventory.valuations
    assert "На витрине: 3 шт." in text and "Витрина, шт." in text
    assert "0007 Крем 50 мл 09.2028 100,00 — — 3 0 из 7" in text
