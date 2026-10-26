import json
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from src.utils.one_alma.pdf_export import InventoryPdfExporter as OneAlmaPdfExporter

from .models import COLUMNS, ExpiryPolicy, StoredItem


class InventoryPdfExporter:
    def export(
        self, items: list[StoredItem], history: list[dict[str, object]] | None = None, today: date | None = None
    ) -> bytes:
        OneAlmaPdfExporter._register_fonts()
        output = BytesIO()
        title = ParagraphStyle("ClinicInventoryTitle", fontName="OneAlmaBold", fontSize=20, leading=27, keepWithNext=True)
        subtitle = ParagraphStyle("ClinicInventorySnapshot", fontName="OneAlmaBold", fontSize=11, leading=17, keepWithNext=True)
        story: list[Flowable] = [Paragraph("Инвентаризация", title), Spacer(1, 7 * mm), self._table(items, today)]
        story.extend([PageBreak(), Paragraph("Истории инвентаризации", title), Spacer(1, 7 * mm)])
        for snapshot in history or []:
            created = datetime.fromisoformat(str(snapshot["created_at"]))
            ended = datetime.fromisoformat(str(snapshot["ended_at"])) if snapshot["ended_at"] else None
            label = (
                f"#{snapshot['id']} - {created:%d.%m.%Y %H:%M} - {ended:%d.%m.%Y %H:%M}"
                if ended
                else (f"#{snapshot['id']} - {created:%d.%m.%Y %H:%M} - по настоящее время")
            )
            historical = [StoredItem(**item) for item in json.loads(str(snapshot["products_json"]))]
            story.extend(
                [
                    Paragraph(escape(label), subtitle),
                    Spacer(1, 3 * mm),
                    self._table(historical, created.date()),
                    Spacer(1, 8 * mm),
                ]
            )
        if not history:
            story.append(Paragraph("Инвентаризаций пока нет", subtitle))
        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            leftMargin=9 * mm,
            rightMargin=9 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="Инвентаризация",
            author="ReInTa Clinic",
        )
        document.build(story, onFirstPage=self._page_number, onLaterPages=self._page_number)
        return output.getvalue()

    @staticmethod
    def _table(items: list[StoredItem], today: date | None) -> LongTable:
        body = ParagraphStyle("ClinicInventoryCell", fontName="OneAlma", fontSize=8, leading=11, splitLongWords=True)
        header = ParagraphStyle("ClinicInventoryHeader", parent=body, fontName="OneAlmaBold", textColor=colors.white)
        rows = [[Paragraph(escape(value), header) for value in COLUMNS]]
        for item in items:
            rows.append([Paragraph(escape(value or "—"), body) for value in item.cells])
        if not items:
            rows.append([Paragraph("Товаров пока нет", body)] + [Paragraph("", body) for _ in range(7)])
        table = LongTable(rows, colWidths=[10 * mm, 25 * mm, 28 * mm, 68 * mm, 36 * mm, 34 * mm, 30 * mm, 30 * mm], repeatRows=1)
        style = TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9d233f")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d2d2d2")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
        for index, item in enumerate(items, 1):
            status = ExpiryPolicy.status(item.expiry, today)
            if status != "normal":
                style.add(
                    "BACKGROUND", (0, index), (-1, index), colors.HexColor("#f7c8cf" if status == "expired" else "#fff0bd")
                )
        table.setStyle(style)
        return table

    @staticmethod
    def _page_number(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("OneAlma", 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(landscape(A4)[0] - 12 * mm, 6 * mm, str(document.page))
        canvas.restoreState()
