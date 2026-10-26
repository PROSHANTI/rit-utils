import logging
import re
from datetime import date
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from pydantic import ValidationError

from .models import InventoryItem

logger = logging.getLogger(__name__)


class InventoryExcelImporter:
    max_file_size = 5 * 1024 * 1024
    max_rows = 10000
    aliases = {
        "article": ("артикул", "арт."),
        "brand": ("бренд",),
        "name": ("название", "наименование"),
        "purchase_price": ("закупочнаястоимость", "закупочнаяцена"),
        "sale_price": ("ценапродажи",),
        "price": ("цена",),
        "expiry": ("срокгодности", "годендо"),
        "quantity": ("количество", "кол-во"),
    }

    def parse(self, content: bytes, filename: str) -> list[InventoryItem]:
        if not filename.lower().endswith(".xlsx") or not content:
            raise ValueError("Выберите файл .xlsx.")
        if len(content) > self.max_file_size:
            raise ValueError("Размер файла не должен превышать 5 МБ.")
        prepared = self._prepare_archive(content)
        try:
            workbook = load_workbook(BytesIO(prepared), read_only=True, data_only=False, keep_links=False)
        except Exception:
            raise ValueError("Не удалось прочитать Excel. Проверьте файл .xlsx.") from None
        try:
            candidates = []
            for sheet in workbook:
                if (sheet.max_row or 0) > self.max_rows + 30 or (sheet.max_column or 0) > 64:
                    raise ValueError("Допускается до 10 000 строк и 64 колонок.")
                for row_number, row in enumerate(sheet.iter_rows(max_row=20, max_col=64, values_only=True), 1):
                    headers = self._headers(row)
                    if {"name", "quantity"} <= headers.keys():
                        candidates.append((sheet, row_number, headers))
                        break
            if len(candidates) != 1:
                raise ValueError("Нужен один лист с колонками «Наименование» / «Название» и «Кол-во» / «Количество».")
            sheet, header_row, headers = candidates[0]
            items = []
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=header_row + 1, max_col=64, values_only=True), header_row + 1
            ):
                if not any(value is not None and str(value).strip() for value in row):
                    continue
                # Totals in warehouse exports can be in any column.
                if any(re.match(r"^(итого|всего)(?:\s|:|$)", str(value or "").strip(), re.I) for value in row[:3]):
                    continue
                try:
                    values = {field: row[column] for field, column in headers.items()}
                    if any(isinstance(value, str) and value.startswith("=") for value in values.values()):
                        raise ValueError("Замените формулы значениями.")
                    result = {field: self._text(value) for field, value in values.items() if field not in ("price", "quantity")}
                    if "price" in values and "sale_price" not in values:
                        result["sale_price"] = self._text(values["price"])
                    expiry = values.get("expiry")
                    if isinstance(expiry, date):
                        result["expiry"] = expiry.strftime("%m.%Y")
                    quantity = str(values["quantity"]).strip()
                    if not re.fullmatch(r"[0-9]+(?:\.0+)?", quantity):
                        raise ValueError("Количество должно быть целым неотрицательным числом.")
                    items.append(InventoryItem(**result, quantity=int(quantity.split(".", 1)[0])))
                except (ValueError, TypeError, ValidationError) as exc:
                    detail = (
                        "Проверьте длину полей, числовой артикул, количество и срок годности."
                        if isinstance(exc, ValidationError)
                        else str(exc)
                    )
                    raise ValueError(f"Строка {row_number}: {detail} Импорт отменён.") from None
                if len(items) > self.max_rows:
                    raise ValueError("За один импорт допускается до 10 000 товаров.")
            if not items:
                raise ValueError("В файле нет товаров.")
            logger.info("Excel инвентаризации прочитан: строк товаров %s", len(items))
            return items
        finally:
            workbook.close()

    def _headers(self, row: tuple[object, ...]) -> dict[str, int]:
        result = {}
        for index, value in enumerate(row):
            name = re.sub(r"\s+", "", str(value or "")).lower().replace("ё", "е")
            for field, aliases in self.aliases.items():
                if name in aliases:
                    if field in result:
                        raise ValueError(f"В Excel повторяется колонка «{value}».")
                    result[field] = index
        return result

    @staticmethod
    def _text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    @staticmethod
    def _prepare_archive(content: bytes) -> bytes:
        """Repair only invalid RGB metadata found in the supplied warehouse export."""
        output = BytesIO()
        try:
            with ZipFile(BytesIO(content)) as source, ZipFile(output, "w") as target:
                entries = source.infolist()
                if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 25 * 1024 * 1024:
                    raise ValueError("Excel слишком большой в распакованном виде.")
                if len({entry.filename for entry in entries}) != len(entries):
                    raise ValueError("В архиве Excel повторяются части документа.")
                for entry in entries:
                    data = source.read(entry)
                    if entry.filename.endswith((".xml", ".rels")):
                        declarations = data.replace(b"\x00", b"").upper()
                        if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
                            raise ValueError("Excel содержит недопустимые XML-объявления.")
                    if entry.filename == "xl/styles.xml":
                        root = ElementTree.fromstring(data)
                        changed = False
                        for element in root.iter():
                            color = element.get("rgb")
                            if color is not None and not re.fullmatch(r"(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})", color):
                                element.set("rgb", "FF000000")
                                changed = True
                        if changed:
                            data = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                    target.writestr(entry.filename, data)
        except (BadZipFile, ElementTree.ParseError, RuntimeError):
            raise ValueError("Некорректный файл .xlsx.") from None
        return output.getvalue()
