from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook

from src.utils.one_alma.excel_import import ExcelProductImporter

HEADERS = ["№", "Артикул", "Наименование", "Объём", "Годен до", "Цена ЦБ", "Цена опт", "Цена магазина", "Количество"]


def excel_bytes(rows, headers=HEADERS):
    # An in-memory fixture, not a user workbook or deliverable.
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_import_reads_all_columns_and_quantities_and_leading_zero():
    content = excel_bytes([[26, "0001", "Крем", "50 мл", datetime(2028, 9, 1), 100.25, None, "250,10", 3]])

    products = ExcelProductImporter().parse(content, "products.xlsx")

    assert len(products) == 1
    assert products[0].quantity == 3
    assert products[0].to_cells() == ("26", "0001", "Крем", "50 мл", "09.2028", "100,25", "—", "250,10")


def test_original_emansi_table_is_supported_without_modification():
    source = Path("src/utils/Sroki_i_Ceny_za_edinitsu_Emansi.xlsx")
    if not source.exists():
        pytest.skip("Original private workbook is not required in CI")

    products = ExcelProductImporter().parse(source.read_bytes(), source.name)

    assert len(products) == 25
    assert sum(product.quantity for product in products) == 50
    assert products[12].article == "0262"


def test_quantity_defaults_to_two_when_column_missing():
    content = excel_bytes([[26, "0001", "Крем", "50 мл", "09.2028", 100, 200, 300]], HEADERS[:-1])

    products = ExcelProductImporter().parse(content, "products.xlsx")

    assert products[0].quantity == 2


@pytest.mark.parametrize(
    "row",
    [
        [26, "0001", "Крем", "50 мл", "99.2028", 100, 200, 300, 2],
        [26, "0001", "Крем", "50 мл", "09.2028", -10, 200, 300, 2],
        [26, "0001", "Крем", "50 мл", "09.2028", "=1+1", 200, 300, 2],
        [26, "0001", "Крем", "50 мл", "09.2028", 100, 200, 300, 0],
        [26, "0001", "Крем", "50 мл", "09.2028", 100, 200, 300, 1.5],
        [26, "0001", "", "50 мл", "09.2028", 100, 200, 300, 2],
    ],
)
def test_invalid_rows_report_line_and_prevent_import(row):
    content = excel_bytes([row])

    with pytest.raises(ValueError, match="Строка 2"):
        ExcelProductImporter().parse(content, "products.xlsx")


@pytest.mark.parametrize(
    "content, filename, error",
    [
        (b"not excel", "products.xlsx", "Некорректный"),
        (b"", "products.xls", ".xlsx"),
        (excel_bytes([], ["wrong"]), "products.xlsx", "нет товаров"),
    ],
)
def test_bad_workbook_and_missing_headers_have_safe_errors(content, filename, error):
    with pytest.raises(ValueError, match=error):
        ExcelProductImporter().parse(content, filename)


def test_malformed_workbook_xml_returns_import_error():
    original = BytesIO(excel_bytes([]))
    corrupted = BytesIO()
    with ZipFile(original) as source, ZipFile(corrupted, "w") as target:
        for item in source.infolist():
            content = b"<broken" if item.filename == "xl/workbook.xml" else source.read(item.filename)
            target.writestr(item, content)

    with pytest.raises(ValueError, match="Не удалось прочитать"):
        ExcelProductImporter().parse(corrupted.getvalue(), "products.xlsx")
