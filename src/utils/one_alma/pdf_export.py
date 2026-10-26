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
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import COLUMNS, Inventory

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
        cb_summary = f"Стоимость по цене ЦБ РФ, ₽. Всего: {cb.amounts[0]}. Продано: {cb.amounts[1]}. В наличии: {cb.amounts[2]}."
        if cb.unpriced_total:
            cb_summary += f" Без цены: {cb.unpriced_total} шт. (продано {cb.unpriced_sold}, в наличии {cb.unpriced_available})."
        data = [[self._paragraph(column, header) for column in (*COLUMNS, "Витрина, шт.", "Продано")]]
        for product in inventory.products:
            sold = f"{product.sold_count} из {len(product.units)}\nВ наличии: {product.available}"
            showcase = str(product.showcase_quantity) if product.showcase_quantity else "—"
            data.append(
                [self._paragraph(cell, body) for cell in product.cells]
                + [self._paragraph(showcase, sold_style), self._paragraph(sold, sold_style)]
            )
        widths = [9, 17, 61, 17, 19, 29, 29, 34, 20, 28]
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
                f"Всего товаров: {inventory.total}. Продано: {inventory.sold}. В наличии: {inventory.available}.", subtitle
            ),
            Paragraph(f"На витрине: {inventory.showcase_quantity} шт. Входит в количество в наличии.", subtitle),
            Spacer(1, 5 * mm),
            Paragraph(cb_summary, subtitle),
            Spacer(1, 5 * mm),
            table,
        ]
        if inventory.history:
            history_data = [
                [
                    self._paragraph(label, header)
                    for label in ("Дата", "Товар", "Действие", "Кому", "Кол-во, шт.", "Цена за шт., ₽", "Сумма, ₽")
                ]
            ]
            for entry in inventory.history:
                history_data.append([self._paragraph(value, body) for value in entry.values])
            history_widths = [34, 22, 43, 48, 20, 28, 29]
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
            unpriced = f" Без цены: {inventory.sales_unpriced} шт. В сумму не входят." if inventory.sales_unpriced else ""
            story.extend(
                [
                    PageBreak(),
                    Paragraph("История изменений", title),
                    Paragraph(f"Продажи за вычетом отмен: {inventory.sales_amount} ₽.{unpriced}", subtitle),
                    Spacer(1, 5 * mm),
                    history_table,
                ]
            )
        document.build(story)
        logger.info("PDF учёта OneAlma сформирован: %s позиций", len(inventory.products))
        return output.getvalue()

    @staticmethod
    def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(text.replace("−", "-")).replace("\n", "<br/>"), style)

    @staticmethod
    def _register_fonts() -> None:
        with _font_lock:
            if "OneAlma" not in pdfmetrics.getRegisteredFontNames():
                fonts = Path(__file__).with_name("fonts")
                pdfmetrics.registerFont(TTFont("OneAlma", str(fonts / "NotoSans-Regular.ttf")))
                pdfmetrics.registerFont(TTFont("OneAlmaBold", str(fonts / "NotoSans-Bold.ttf")))
