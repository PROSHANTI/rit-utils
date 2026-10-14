import re
from datetime import date, datetime
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

from .models import NewProduct


class ExcelProductImporter:
    max_file_size = 5 * 1024 * 1024
    max_rows = 2000

    def parse(self, content: bytes, filename: str) -> list[NewProduct]:
        if not filename.lower().endswith(".xlsx"):
            raise ValueError("Загрузите файл .xlsx.")
        if len(content) > self.max_file_size:
            raise ValueError("Размер файла не должен превышать 5 МБ.")
        self._validate_archive(content)
        try:
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
        except Exception:
            # XML/ZIP exception types depend on openpyxl's installed parser.
            raise ValueError("Не удалось прочитать Excel. Проверьте формат .xlsx.") from None
        try:
            sheet = workbook.worksheets[0]
            if (sheet.max_row or 0) > self.max_rows + 20 or (sheet.max_column or 0) > 30:
                raise ValueError("В файле допускается до 2000 строк товаров и 30 колонок.")
            headers = None
            products = []
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if headers is None:
                    candidate = self._headers(row)
                    if len(candidate) >= 8:
                        headers = candidate
                    elif row_number > 10:
                        raise ValueError("Не найдены заголовки. Используйте шаблон из памятки.")
                    continue
                if not any(value is not None for value in row) or str(row[0]).upper().startswith("ИТОГО"):
                    continue
                try:
                    values = {field: row[column] for field, column in headers.items()}
                    if any(isinstance(value, str) and value.startswith("=") for value in values.values()):
                        raise ValueError("Формулы не поддерживаются: вставьте их значения.")
                    product = NewProduct(
                        position=self._integer(values["position"]),
                        article=self._text(values["article"]),
                        name=self._text(values["name"]),
                        volume=self._text(values["volume"]),
                        expiry=self._expiry(values["expiry"]),
                        central_bank_price=self._text(values["central_bank_price"]),
                        wholesale_price=self._text(values["wholesale_price"]),
                        market_price=self._text(values["market_price"]),
                        quantity=self._integer(values.get("quantity", 2)),
                    )
                    if len(product.article) > 64 or len(product.name) > 300 or len(product.volume) > 64:
                        raise ValueError("Слишком длинный артикул, название или объём.")
                    product.to_cells()
                    products.append(product)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError(f"Строка {row_number}: {exc}") from None
            if not products:
                raise ValueError("В файле нет товаров.")
            if len(products) > self.max_rows or sum(product.quantity for product in products) > 10000:
                raise ValueError("За один импорт допускается до 2000 позиций и 10000 штук.")
            return products
        finally:
            workbook.close()

    @staticmethod
    def _validate_archive(content: bytes) -> None:
        try:
            with ZipFile(BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 20 * 1024 * 1024:
                    raise ValueError("Excel слишком большой в распакованном виде.")
        except BadZipFile:
            raise ValueError("Некорректный файл .xlsx.") from None

    @staticmethod
    def _headers(row: tuple[object, ...]) -> dict[str, int]:
        aliases = {
            "position": ("№", "№п/п"),
            "article": ("арт.", "артикул"),
            "name": ("наименование", "наименованиепрепарата"),
            "volume": ("объем",),
            "expiry": ("годендо", "годендо(окончание)"),
            "quantity": ("количество", "количествошт."),
            "central_bank_price": ("ценацб", "ценапоцбрфна27.05(1шт.,₽)"),
            "wholesale_price": ("ценаопт", "ценаоптemansi(1шт.,₽)"),
            "market_price": ("ценамагазина", "средняяценанарынкевмагазинах(1шт.,₽)"),
        }
        result = {}
        for column, value in enumerate(row):
            name = re.sub(r"\s+", "", str(value or "")).casefold().replace("ё", "е")
            for field, names in aliases.items():
                if name in names:
                    if field in result:
                        raise ValueError("В Excel повторяются колонки.")
                    result[field] = column
        required = set(aliases) - {"quantity"}
        return result if required <= result.keys() else {}

    @staticmethod
    def _text(value: object) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _integer(value: object) -> int:
        text = str(value)
        if not re.fullmatch(r"\d+(?:\.0+)?", text):
            raise ValueError("Номер и количество должны быть целыми положительными числами.")
        return int(text.split(".", 1)[0])

    @staticmethod
    def _expiry(value: object) -> str:
        if isinstance(value, date):
            return value.strftime("%Y-%m")
        text = str(value)
        if re.fullmatch(r"\d{2}\.\d{4}", text):
            return datetime.strptime(text, "%m.%Y").strftime("%Y-%m")
        return text
