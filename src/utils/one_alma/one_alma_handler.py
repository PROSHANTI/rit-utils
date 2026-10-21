import hashlib
import hmac
import logging
import sqlite3

from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from .excel_import import ExcelProductImporter
from .models import COLUMNS, NewProduct
from .pdf_export import InventoryPdfExporter
from .repository import InventoryRepository

logger = logging.getLogger(__name__)


class OneAlmaHandler:
    def __init__(self, repository: InventoryRepository | None = None) -> None:
        self.repository = repository or InventoryRepository()
        self.templates = Jinja2Templates(directory="templates")
        self.pdf = InventoryPdfExporter()

    def page(self, request: Request) -> Response:
        try:
            inventory = self.repository.snapshot()
        except sqlite3.Error:
            logger.exception("Не удалось открыть учёт OneAlma")
            raise HTTPException(status_code=503, detail="Учёт временно недоступен. Попробуйте позже.") from None
        return self.templates.TemplateResponse(
            request,
            "one_alma.html",
            {
                "inventory": inventory,
                "columns": COLUMNS,
                "csrf_token": self._csrf_token(request),
            },
            headers={"Cache-Control": "no-store"},
        )

    def set_sold(self, request: Request, unit_id: int, sold: bool, csrf_token: str) -> Response:
        self._check_csrf(request, csrf_token)
        try:
            inventory = self.repository.set_sold(unit_id, sold)
        except LookupError:
            raise HTTPException(status_code=404, detail="Товар не найден") from None
        except sqlite3.Error:
            logger.exception("Не удалось сохранить отметку продажи OneAlma")
            raise HTTPException(status_code=503, detail="Не удалось сохранить продажу. Попробуйте позже.") from None
        return JSONResponse(
            {
                "total": inventory.total,
                "sold": inventory.sold,
                "available": inventory.available,
                "valuations": [
                    {"amounts": valuation.amounts, "unpriced": valuation.unpriced} for valuation in inventory.valuations
                ],
                "products": [
                    {
                        "id": product.id,
                        "cells": product.cells,
                        "sold": product.sold_count,
                        "available": product.available,
                        "units": [{"id": unit.id, "sold": unit.sold} for unit in product.units],
                    }
                    for product in inventory.products
                ],
            },
            headers={"Cache-Control": "no-store"},
        )

    def add_product(self, request: Request, product: NewProduct, csrf_token: str) -> Response:
        self._check_csrf(request, csrf_token)
        try:
            self.repository.add_product(product)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Позиция с таким номером уже существует.") from None
        except sqlite3.Error:
            logger.exception("Не удалось добавить товар OneAlma")
            raise HTTPException(status_code=503, detail="Не удалось добавить товар. Попробуйте позже.") from None
        return JSONResponse({"detail": "Товар добавлен"}, status_code=201)

    def update_product(self, request: Request, product_id: int, product: NewProduct, csrf_token: str) -> Response:
        self._check_csrf(request, csrf_token)
        try:
            self.repository.update_product(product_id, product)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Позиция с таким номером уже существует.") from None
        except sqlite3.Error:
            logger.exception("Не удалось изменить товар OneAlma")
            raise HTTPException(status_code=503, detail="Не удалось изменить товар. Попробуйте позже.") from None
        return JSONResponse({"detail": "Товар изменён"})

    def delete_products(self, request: Request, product_ids: list[int], csrf_token: str) -> Response:
        self._check_csrf(request, csrf_token)
        try:
            self.repository.delete_products(product_ids)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except sqlite3.Error:
            logger.exception("Не удалось удалить товары OneAlma")
            raise HTTPException(status_code=503, detail="Не удалось удалить товары. Попробуйте позже.") from None
        return JSONResponse({"detail": "Товары удалены"})

    def import_products(self, request: Request, file: UploadFile, csrf_token: str) -> Response:
        self._check_csrf(request, csrf_token)
        try:
            importer = ExcelProductImporter()
            content = file.file.read(importer.max_file_size + 1)
            products = importer.parse(content, file.filename or "")
            result = self.repository.import_products(products)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409, detail="Не удалось согласовать позиции. Обновите страницу и повторите импорт."
            ) from None
        except sqlite3.Error:
            logger.exception("Не удалось импортировать товары OneAlma")
            raise HTTPException(status_code=503, detail="Не удалось сохранить импорт. Попробуйте позже.") from None
        finally:
            file.file.close()
        return JSONResponse(
            {"detail": f"Добавлено позиций: {result.added}. Обновлено позиций: {result.updated}."}, status_code=201
        )

    def download_pdf(self, sort: int = 0, descending: bool = False) -> Response:
        try:
            content = self.pdf.export(self.repository.snapshot().sorted_by(sort, descending))
        except sqlite3.Error:
            logger.exception("Не удалось прочитать учёт OneAlma для PDF")
            raise HTTPException(status_code=503, detail="Учёт временно недоступен. Попробуйте позже.") from None
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="one_alma.pdf"',
                "Cache-Control": "no-store",
            },
        )

    @staticmethod
    def _check_csrf(request: Request, csrf_token: str) -> None:
        if not hmac.compare_digest(csrf_token.encode(), OneAlmaHandler._csrf_token(request).encode()):
            raise HTTPException(status_code=403, detail="Обновите страницу и повторите действие.")

    @staticmethod
    def _csrf_token(request: Request) -> str:
        session = request.cookies.get("JWT_REFRESH_TOKEN_COOKIE") or request.cookies.get("JWT_ACCESS_TOKEN_COOKIE")
        if not session:
            raise HTTPException(status_code=401, detail="Войдите в систему")
        return hmac.new(session.encode(), b"one-alma-sale", hashlib.sha256).hexdigest()
