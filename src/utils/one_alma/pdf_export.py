import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import COLUMNS, Inventory, format_cents

logger = logging.getLogger(__name__)
_font_lock = Lock()


class InventoryPdfExporter:
    def export(self, inventory: Inventory) -> bytes:
        self._register_fonts()
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="Учет OneAlma",
            author="ReInTa Clinic",
        )
        body = ParagraphStyle("InventoryCell", fontName="OneAlma", fontSize=8, leading=11)
        header = ParagraphStyle("InventoryHeader", parent=body, fontName="OneAlmaBold", textColor=colors.white)
        title = ParagraphStyle("InventoryTitle", parent=body, fontName="OneAlmaBold", fontSize=18, leading=23)
        subtitle = ParagraphStyle("InventorySubtitle", parent=body, fontSize=10, leading=15)
        sold_style = ParagraphStyle("SoldCell", parent=body, alignment=TA_CENTER)
        cb = inventory.valuations[0]
        cb_summary = (
            f"Стоимость по цене TheOneAlma +10%, ₽. Всего: {cb.amounts[0]}. "
            f"Продано: {cb.amounts[1]}. В наличии: {cb.amounts[2]}."
        )
        if cb.unpriced_total:
            cb_summary += f" Без цены: {cb.unpriced_total} шт. (продано {cb.unpriced_sold}, в наличии {cb.unpriced_available})."
        data = [[self._paragraph(column, header) for column in (*COLUMNS, "Витрина, шт.", "Продано", "Списано")]]
        for product in inventory.products:
            sold = f"{product.sold_count} из {len(product.units)}\nВ наличии: {product.available}"
            showcase = str(product.showcase_quantity) if product.showcase_quantity else "—"
            data.append(
                [self._paragraph(cell, body) for cell in product.cells]
                + [
                    self._paragraph(showcase, sold_style),
                    self._paragraph(sold, sold_style),
                    self._paragraph(str(product.written_off_count), sold_style),
                ]
            )
        widths = [9, 17, 59, 17, 19, 29, 29, 31, 19, 28, 19]
        table = Table(data, colWidths=[width * document.width / sum(widths) for width in widths], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9d233f")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d2d2d2")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story = [
            Paragraph("Учет OneAlma", title),
            Paragraph(f"Учет продажи товаров. Состояние на {datetime.now(ZoneInfo('Europe/Moscow')):%d.%m.%Y %H:%M}", subtitle),
            Spacer(1, 3 * mm),
            Paragraph(
                f"Всего товаров: {inventory.total}. Продано: {inventory.sold}. "
                f"Списано: {inventory.written_off}. В наличии: {inventory.available}.",
                subtitle,
            ),
            Paragraph(f"На витрине: {inventory.showcase_quantity} шт. Входит в количество в наличии.", subtitle),
            Spacer(1, 5 * mm),
            Paragraph(cb_summary, subtitle),
            Spacer(1, 5 * mm),
            table,
        ]
        if inventory.writeoffs:
            writeoff_data = [
                [
                    self._paragraph(label, header)
                    for label in ("Дата", "Артикул", "Наименование", "Кол-во, шт.", "Комментарий", "Статус")
                ]
            ]
            for writeoff in reversed(inventory.writeoffs):
                status = (
                    ("Отменено " + writeoff.cancelled_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M"))
                    if writeoff.cancelled_at
                    else "Списано"
                )
                values = (
                    writeoff.created_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M"),
                    writeoff.cells[1],
                    writeoff.cells[2],
                    str(writeoff.quantity),
                    writeoff.comment or "—",
                    status,
                )
                writeoff_data.append([self._paragraph(value, body) for value in values])
            writeoff_table = self._table(writeoff_data, [31, 19, 77, 19, 85, 40], document.width)
            story.extend(
                [
                    PageBreak(),
                    Paragraph("Списанные товары", title),
                    Paragraph(f"Списано за вычетом отмен: {inventory.written_off} шт.", subtitle),
                    Spacer(1, 5 * mm),
                    writeoff_table,
                ]
            )
        changes = [
            entry
            for entry in inventory.history
            if entry.sale_id is None
            and entry.writeoff_id is None
            and entry.kind not in ("sale", "cancel", "writeoff", "cancel_writeoff")
        ]
        if changes:
            history_data = [
                [self._paragraph(label, header) for label in ("Дата", "Товар", "Действие", "Кол-во, шт.", "Цена, ₽")]
            ]
            for entry in changes:
                history_data.append([self._paragraph(entry.values[index], body) for index in (0, 1, 2, 4, 5)])
            history_widths = [34, 25, 80, 35, 50]
            history_table = Table(
                history_data, colWidths=[width * document.width / sum(history_widths) for width in history_widths], repeatRows=1
            )
            history_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9d233f")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d2d2d2")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.extend(
                [
                    PageBreak(),
                    Paragraph("История изменений", title),
                    Spacer(1, 5 * mm),
                    history_table,
                ]
            )
        document.build(story)
        logger.info("PDF учёта OneAlma сформирован: %s позиций", len(inventory.products))
        return output.getvalue()

    @staticmethod
    def _table(data: list, widths: list[int], width: float) -> Table:
        table = Table(data, colWidths=[part * width / sum(widths) for part in widths], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9d233f")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d2d2d2")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    @staticmethod
    def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(text.replace("−", "-").replace("→", " -> ")).replace("\n", "<br/>"), style)

    @staticmethod
    def _register_fonts() -> None:
        with _font_lock:
            if "OneAlma" not in pdfmetrics.getRegisteredFontNames():
                fonts = Path(__file__).with_name("fonts")
                pdfmetrics.registerFont(TTFont("OneAlma", str(fonts / "NotoSans-Regular.ttf")))
                pdfmetrics.registerFont(TTFont("OneAlmaBold", str(fonts / "NotoSans-Bold.ttf")))


class SalesPdfExporter:
    def export(self, inventory: Inventory, sale_id: int | None = None) -> bytes:
        InventoryPdfExporter._register_fonts()
        sales = [sale for sale in reversed(inventory.sales) if sale_id is None or sale.id == sale_id]
        if sale_id is not None and not sales:
            raise LookupError("Продажа не найдена.")
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=A4,
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="История продаж OneAlma",
        )
        body = ParagraphStyle("SalesBody", fontName="OneAlma", fontSize=10, leading=15)
        header = ParagraphStyle("SalesHeader", parent=body, fontName="OneAlmaBold", textColor=colors.white)
        title = ParagraphStyle("SalesTitle", parent=body, fontName="OneAlmaBold", fontSize=18, leading=24)
        receipt_title = ParagraphStyle("ReceiptTitle", parent=body, fontName="OneAlmaBold", fontSize=12, leading=18)
        paragraph = InventoryPdfExporter._paragraph
        story = [paragraph("История продаж" if sale_id is None else f"Продажа #{sale_id}", title), Spacer(1, 4 * mm)]
        if sale_id is None:
            active = [sale for sale in sales if sale.cancelled_at is None]
            story.extend(
                [
                    paragraph(f"Продано: {sum(sale.quantity for sale in active)} шт. Сумма: {inventory.sales_amount} ₽.", body),
                    Spacer(1, 5 * mm),
                ]
            )
        if not sales:
            story.append(paragraph("Продаж пока нет.", body))
        for sale in sales:
            created = sale.created_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M:%S")
            rows = [
                [paragraph(label, header) for label in ("Товар", "Кол-во", "Цена за шт., ₽", "Сумма, ₽")],
                [
                    paragraph(f"{sale.cells[1]} · {sale.cells[2]}\n{sale.cells[3]}", body),
                    paragraph(str(sale.quantity), body),
                    paragraph(format_cents(sale.price_cents), body),
                    paragraph(format_cents(sale.amount_cents), body),
                ],
            ]
            receipt = [
                paragraph(f"Продажа #{sale.id}", receipt_title),
                paragraph(created, body),
                paragraph(f"Кому: {sale.customer or 'Не указан'}", body),
                Spacer(1, 3 * mm),
                InventoryPdfExporter._table(rows, [92, 18, 32, 32], document.width),
                Spacer(1, 2 * mm),
                paragraph(f"Итого: {format_cents(sale.amount_cents)} ₽", receipt_title),
            ]
            if sale.cancelled_at:
                cancelled = sale.cancelled_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M:%S")
                receipt.append(paragraph(f"Отменена: {cancelled}", body))
            receipt.append(Spacer(1, 7 * mm))
            story.append(KeepTogether(receipt))
        document.build(story)
        return output.getvalue()
