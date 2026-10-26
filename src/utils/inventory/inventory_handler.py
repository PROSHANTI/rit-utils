import hashlib
import hmac
import json
import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .excel_import import InventoryExcelImporter
from .models import COLUMNS, InventoryItem, QuantityChange, StoredItem
from .ordering import InventoryOrdering, SortColumn
from .pdf_export import InventoryPdfExporter
from .repository import InventoryRepository

logger = logging.getLogger(__name__)
T = TypeVar("T")


class InventoryHandler:
    def __init__(self, repository: InventoryRepository | None = None) -> None:
        self.repository = repository or InventoryRepository()
        self.templates = Jinja2Templates(directory="templates")
        self.pdf = InventoryPdfExporter()
        self.router = APIRouter(prefix="/inventory", tags=["Инвентаризация"], dependencies=[Depends(self._guard_csrf)])
        self.router.add_api_route("", self.page, methods=["GET"], response_model=None)
        self.router.add_api_route("/items", self.items, methods=["GET"], response_model=None)
        self.router.add_api_route("/products", self.add, methods=["POST"], response_model=None)
        self.router.add_api_route("/products/{item_id}", self.update, methods=["PUT"], response_model=None)
        self.router.add_api_route("/products/{item_id}", self.delete, methods=["DELETE"], response_model=None)
        self.router.add_api_route("/products/{item_id}/quantity", self.quantity, methods=["POST"], response_model=None)
        self.router.add_api_route("/snapshots", self.create_snapshot, methods=["POST"], response_model=None)
        self.router.add_api_route("/history", self.history, methods=["GET"], response_model=None)
        self.router.add_api_route("/history/{snapshot_id}", self.delete_snapshot, methods=["DELETE"], response_model=None)
        self.router.add_api_route("/import", self.import_excel, methods=["POST"], response_model=None)
        self.router.add_api_route("/pdf", self.download_pdf, methods=["GET"], response_model=None)

    @staticmethod
    def _csrf_token(request: Request) -> str:
        session = (
            getattr(request.state, "inventory_demo_session", None)
            or request.cookies.get("JWT_REFRESH_TOKEN_COOKIE")
            or request.cookies.get("JWT_ACCESS_TOKEN_COOKIE")
        )
        if not session:
            raise HTTPException(status_code=401, detail="Войдите в систему.")
        return hmac.new(session.encode(), b"clinic-inventory", hashlib.sha256).hexdigest()

    def _guard_csrf(self, request: Request) -> None:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        supplied = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(supplied.encode(), self._csrf_token(request).encode()):
            logger.warning("Запрос к инвентаризации отклонён: проверка CSRF не пройдена")
            raise HTTPException(status_code=403, detail="Обновите страницу и повторите действие.")

    def _call(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except LookupError as exc:
            logger.warning("Операция инвентаризации отклонена: объект не найден")
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValidationError:
            logger.warning("Операция инвентаризации отклонена: некорректные поля товара")
            raise HTTPException(status_code=422, detail="Проверьте поля товара и целое неотрицательное количество.") from None
        except ValueError as exc:
            logger.warning("Операция инвентаризации отклонена: входные данные не прошли проверку")
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except (sqlite3.Error, OSError):
            logger.exception("Ошибка базы или резервной копии инвентаризации")
            raise HTTPException(status_code=503, detail="Не удалось сохранить или прочитать данные. Попробуйте позже.") from None

    def page(self, request: Request) -> Response:
        items = self._call(self.repository.items)
        logger.debug("Отображение инвентаризации: позиций %s", len(items))
        return self.templates.TemplateResponse(
            request,
            "inventory.html",
            {
                "items": items,
                "columns": COLUMNS,
                "sort_fields": InventoryOrdering.fields,
                "csrf_token": self._csrf_token(request),
            },
            headers={"Cache-Control": "no-store"},
        )

    def items(self, sort: SortColumn = "id", descending: bool = False) -> Response:
        def read() -> list[dict[str, object]]:
            return [item.view() for item in InventoryOrdering.apply(self.repository.items(), sort, descending)]

        return JSONResponse({"items": self._call(read)}, headers={"Cache-Control": "no-store"})

    def _changed(
        self, operation: Callable[[], object], message: str, status: int = 200, *, object_id: int | None = None
    ) -> Response:
        result = self._call(operation)
        logger.info("%s: id=%s", message, object_id if object_id is not None else result)
        return JSONResponse({"detail": message}, status_code=status, headers={"Cache-Control": "no-store"})

    def add(self, item: InventoryItem) -> Response:
        return self._changed(lambda: self.repository.add(item), "Товар добавлен", 201)

    def update(self, item_id: int, item: InventoryItem) -> Response:
        return self._changed(lambda: self.repository.update(item_id, item), "Товар изменён", object_id=item_id)

    def delete(self, item_id: int) -> Response:
        return self._changed(lambda: self.repository.delete(item_id), "Товар удалён", object_id=item_id)

    def quantity(self, item_id: int, change: QuantityChange) -> Response:
        return self._changed(
            lambda: self.repository.set_quantity(item_id, **change.model_dump()), "Количество сохранено", object_id=item_id
        )

    def create_snapshot(self) -> Response:
        snapshot_id = self._call(self.repository.create_snapshot)
        logger.info("Инвентаризация сохранена: id=%s", snapshot_id)
        return JSONResponse({"detail": f"Инвентаризация #{snapshot_id} сохранена", "id": snapshot_id}, status_code=201)

    def history(self) -> Response:
        def read() -> list[dict[str, object]]:
            result = []
            for row in self.repository.history():
                created = datetime.fromisoformat(str(row["created_at"]))
                ended = datetime.fromisoformat(str(row["ended_at"])) if row["ended_at"] else None
                result.append(
                    {
                        "id": row["id"],
                        "created_at": created.strftime("%d.%m.%Y %H:%M"),
                        "ended_at": ended.strftime("%d.%m.%Y %H:%M") if ended else None,
                        "items": [StoredItem(**item).view(created.date()) for item in json.loads(str(row["products_json"]))],
                    }
                )
            return result

        return JSONResponse({"snapshots": self._call(read)}, headers={"Cache-Control": "no-store"})

    def delete_snapshot(self, snapshot_id: int) -> Response:
        return self._changed(
            lambda: self.repository.delete_snapshot(snapshot_id), "Инвентаризация удалена", object_id=snapshot_id
        )

    def import_excel(
        self,
        file: UploadFile = File(...),
        fingerprint: str = Form("", max_length=64),
    ) -> Response:
        def run() -> dict[str, object]:
            importer = InventoryExcelImporter()
            items = importer.parse(file.file.read(importer.max_file_size + 1), file.filename or "")
            if not fingerprint:
                logger.debug("Предварительная сверка импорта: строк %s", len(items))
                return {"preview": self.repository.preview_import(items)}
            result = self.repository.import_items(items, fingerprint)
            logger.info("Импорт товаров завершён: добавлено %s, обновлено %s", result["added"], result["updated"])
            return {"detail": f"Добавлено: {result['added']}. Обновлено: {result['updated']}."}

        try:
            result = self._call(run)
        finally:
            file.file.close()
        return JSONResponse(result, status_code=201 if fingerprint else 200, headers={"Cache-Control": "no-store"})

    def download_pdf(self, sort: SortColumn = "id", descending: bool = False) -> Response:
        def export() -> bytes:
            items, history = self.repository.export_state()
            return self.pdf.export(InventoryOrdering.apply(items, sort, descending), history)

        content = self._call(export)
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="inventory.pdf"',
                "Cache-Control": "no-store",
            },
        )
