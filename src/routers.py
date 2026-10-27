import base64
import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from src.auth import AuthenticationService
from src.utils.doctor_form.doctor_form_handler import DoctorFormGenerator, DoctorFormRequest
from src.utils.gen_cert.gen_cert_handler import CertificateGenerator, CertificateRequest
from src.utils.inventory.inventory_handler import InventoryHandler
from src.utils.one_alma.models import NewProduct
from src.utils.one_alma.one_alma_handler import OneAlmaHandler
from src.utils.remove_bg.remove_bg_handler import RemoveBackgroundHandler
from src.utils.send_email.email_handler import EmailHandler

logger = logging.getLogger(__name__)


class ApplicationRouter:
    def __init__(self, auth: AuthenticationService) -> None:
        self.auth = auth
        self.email = EmailHandler()
        self.certificates = CertificateGenerator()
        self.doctor_forms = DoctorFormGenerator()
        self.images = RemoveBackgroundHandler()
        self.one_alma = OneAlmaHandler()
        self.inventory = InventoryHandler()
        self.templates = Jinja2Templates(directory="templates")
        self.dependencies = [auth.dependency()]
        self.router = APIRouter()
        self._register_routes()

    def login(self, request: Request, username: str = Form(...), password: str = Form(...)) -> Response:
        logger.debug("Обработка запроса авторизации")
        return self.auth.login(request, username, password)

    def logout(self, request: Request) -> Response:
        logger.debug("Обработка запроса выхода из системы")
        return self.auth.logout(request)

    def refresh_token(self, request: Request) -> Response:
        logger.debug("Обработка запроса обновления токена")
        return self.auth.refresh(request)

    def root(self, request: Request) -> Response:
        logger.debug("Обработка запроса главной страницы")
        if request.method == "HEAD":
            return Response(status_code=200)
        return self.auth.check_status(request)

    def home_page(self, request: Request) -> Response:
        logger.debug("Отображение домашней страницы")
        return self.templates.TemplateResponse(request, "home.html")

    def send_email(self, request: Request) -> Response:
        return self._status_page(
            request, template="send_email.html", cookie="email_status", error="Не удалось декодировать статус отправки письма"
        )

    def send_email_endpoint(
        self,
        qr_pay: str | None = Form(None),
        cashless_pay: str | None = Form(None),
        card_pay: str | None = Form(None),
        cash_pay: str | None = Form(None),
        attachment: UploadFile = File(...),
    ) -> Response:
        return self.email.handle(
            qr_pay=qr_pay,
            cashless_pay=cashless_pay,
            card_pay=card_pay,
            cash_pay=cash_pay,
            attachment=attachment,
        )

    def gen_rit_cert_page(self, request: Request) -> Response:
        return self._status_page(
            request,
            template="gen_rit_cert.html",
            cookie="gen_cert_status",
            error="Не удалось декодировать статус генерации сертификата",
        )

    def gen_rit_cert_endpoint(self, name: str | None = Form(None), price: str | None = Form(None)) -> Response:
        return self.certificates.generate(CertificateRequest(name=name, price=price))

    def doctor_form_page(self, request: Request) -> Response:
        return self._status_page(
            request,
            template="doctor_form.html",
            cookie="doctor_form_status",
            error="Не удалось декодировать статус создания бланка врача",
        )

    def doctor_form_endpoint(
        self,
        doctor_1: str | None = Form(None),
        doctor_2: str | None = Form(None),
        doctor_3: str | None = Form(None),
        doctor_4: str | None = Form(None),
        patient_1: str | None = Form(None),
        patient_2: str | None = Form(None),
        patient_3: str | None = Form(None),
        patient_4: str | None = Form(None),
        date: str | None = Form(None),
    ) -> Response:
        return self.doctor_forms.generate(
            DoctorFormRequest(
                doctors=(doctor_1, doctor_2, doctor_3, doctor_4),
                patients=(patient_1, patient_2, patient_3, patient_4),
                date=date,
            ),
        )

    def remove_bg_page(self, request: Request) -> Response:
        return self._status_page(
            request, template="remove_bg.html", cookie="remove_bg_status", error="Не удалось декодировать статус удаления фона"
        )

    def remove_bg_endpoint(
        self, background_tasks: BackgroundTasks, file: UploadFile = File(...), color: str | None = Form(None)
    ) -> Response:
        return self.images.handle(background_tasks=background_tasks, file=file, color=color)

    def one_alma_page(self, request: Request) -> Response:
        return self.one_alma.page(request)

    def one_alma_sale(self, request: Request, unit_id: int, sold: bool = Form(...), csrf_token: str = Form(...)) -> Response:
        return self.one_alma.set_sold(request, unit_id, sold, csrf_token)

    def one_alma_sold_count(
        self, request: Request, product_id: int, quantity: int = Form(..., ge=0, le=1000), csrf_token: str = Form(...)
    ) -> Response:
        return self.one_alma.set_product_count(request, product_id, quantity, csrf_token)

    def one_alma_showcase(
        self, request: Request, product_id: int, quantity: int = Form(..., ge=0, le=1000), csrf_token: str = Form(...)
    ) -> Response:
        return self.one_alma.set_product_count(request, product_id, quantity, csrf_token, showcase=True)

    def one_alma_record_sale(
        self,
        request: Request,
        product_id: int,
        quantity: int = Form(..., ge=1, le=1000),
        customer: str = Form("", max_length=200),
        unit_price: str = Form("", max_length=32),
        request_id: str = Form(..., max_length=64),
        csrf_token: str = Form(...),
    ) -> Response:
        return self.one_alma.record_sale(request, product_id, quantity, customer, unit_price, request_id, csrf_token)

    def one_alma_cancel_sale(self, request: Request, sale_id: int, csrf_token: str = Form(...)) -> Response:
        return self.one_alma.cancel_sale(request, sale_id, csrf_token)

    def one_alma_history(self, product_id: int) -> Response:
        return self.one_alma.history(product_id)

    def one_alma_add_product(
        self,
        request: Request,
        article: str = Form(..., min_length=1, max_length=64),
        name: str = Form(..., min_length=1, max_length=300),
        volume: str = Form(..., min_length=1, max_length=64),
        expiry: str = Form(..., max_length=7),
        central_bank_price: str = Form("", max_length=32),
        wholesale_price: str = Form("", max_length=32),
        market_price: str = Form("", max_length=32),
        quantity: int = Form(2, ge=1, le=1000),
        csrf_token: str = Form(...),
    ) -> Response:
        product = NewProduct(
            position=1,
            article=article,
            name=name,
            volume=volume,
            expiry=expiry,
            central_bank_price=central_bank_price,
            wholesale_price=wholesale_price,
            market_price=market_price,
            quantity=quantity,
        )
        return self.one_alma.add_product(request, product, csrf_token)

    def one_alma_pdf(self, sort: int = Query(0, ge=0, le=9), descending: bool = Query(False)) -> Response:
        return self.one_alma.download_pdf(sort, descending)

    def one_alma_update_product(
        self,
        request: Request,
        product_id: int,
        position: int = Form(..., ge=1, le=999999),
        article: str = Form(..., min_length=1, max_length=64),
        name: str = Form(..., min_length=1, max_length=300),
        volume: str = Form(..., min_length=1, max_length=64),
        expiry: str = Form(..., max_length=7),
        central_bank_price: str = Form("", max_length=32),
        wholesale_price: str = Form("", max_length=32),
        market_price: str = Form("", max_length=32),
        quantity: int = Form(2, ge=1, le=1000),
        csrf_token: str = Form(...),
    ) -> Response:
        product = NewProduct(
            position=position,
            article=article,
            name=name,
            volume=volume,
            expiry=expiry,
            central_bank_price=central_bank_price,
            wholesale_price=wholesale_price,
            market_price=market_price,
            quantity=quantity,
        )
        return self.one_alma.update_product(request, product_id, product, csrf_token)

    def one_alma_delete_products(
        self, request: Request, product_ids: list[int] = Form(...), csrf_token: str = Form(...)
    ) -> Response:
        return self.one_alma.delete_products(request, product_ids, csrf_token)

    def one_alma_import(
        self,
        request: Request,
        file: UploadFile = File(...),
        csrf_token: str = Form(...),
        fingerprint: str = Form("", max_length=64),
    ) -> Response:
        return self.one_alma.import_products(request, file, csrf_token, fingerprint)

    def one_alma_import_template(self) -> Response:
        return self.one_alma.import_template()

    def _register_routes(self) -> None:
        self.router.include_router(self.inventory.router, dependencies=self.dependencies)
        routes: list[tuple[str, Callable[..., Response], list[str], bool, str, list[str]]] = [
            ("/login", self.login, ["POST"], False, "Авторизация", ["Авторизация"]),
            ("/logout", self.logout, ["POST"], True, "Выйти из системы", ["Выход из системы"]),
            ("/refresh", self.refresh_token, ["POST"], False, "Обновить токен доступа", ["Авторизация"]),
            ("/", self.root, ["GET", "HEAD"], False, "Отображает домашнюю страницу", ["Главная страница"]),
            ("/home", self.home_page, ["GET"], True, "Отобразить домашнюю страницу", ["Домашняя страница"]),
            ("/send_email", self.send_email, ["GET"], True, "Страница отправки отчета", ["Отправка отчета"]),
            ("/send_email", self.send_email_endpoint, ["POST"], True, "Отправить отчет на почту", ["Отправка отчета"]),
            (
                "/gen_rit_cert",
                self.gen_rit_cert_page,
                ["GET"],
                True,
                "Страница генерации подарочного сертификата",
                ["Генерация сертификата"],
            ),
            (
                "/gen_rit_cert",
                self.gen_rit_cert_endpoint,
                ["POST"],
                True,
                "Сгенерировать подарочный сертификат",
                ["Генерация сертификата"],
            ),
            (
                "/doctor_form",
                self.doctor_form_page,
                ["GET"],
                True,
                "Страница генерации карточек клиентов",
                ["Генерация карточек"],
            ),
            (
                "/doctor_form",
                self.doctor_form_endpoint,
                ["POST"],
                True,
                "Сгенерировать карточки клиентов",
                ["Генерация карточек"],
            ),
            ("/remove_bg", self.remove_bg_page, ["GET"], True, "Страница удаления фона с изображений", ["Удаление фона"]),
            ("/remove_bg", self.remove_bg_endpoint, ["POST"], True, "Удалить фон с изображения", ["Удаление фона"]),
            ("/one_alma", self.one_alma_page, ["GET"], True, "Учет OneAlma", ["OneAlma"]),
            (
                "/one_alma/products/{product_id}/sales",
                self.one_alma_record_sale,
                ["POST"],
                True,
                "Оформить продажу",
                ["OneAlma"],
            ),
            ("/one_alma/products/{product_id}/history", self.one_alma_history, ["GET"], True, "История товара", ["OneAlma"]),
            ("/one_alma/sales/{sale_id}/cancel", self.one_alma_cancel_sale, ["POST"], True, "Отменить продажу", ["OneAlma"]),
            ("/one_alma/units/{unit_id}", self.one_alma_sale, ["POST"], True, "Отметить продажу товара", ["OneAlma"]),
            ("/one_alma/products/{product_id}/sold", self.one_alma_sold_count, ["POST"], True, "Количество продаж", ["OneAlma"]),
            (
                "/one_alma/products/{product_id}/showcase",
                self.one_alma_showcase,
                ["POST"],
                True,
                "Количество на витрине",
                ["OneAlma"],
            ),
            ("/one_alma/pdf", self.one_alma_pdf, ["GET"], True, "Скачать учёт товаров в PDF", ["OneAlma"]),
            ("/one_alma/products", self.one_alma_add_product, ["POST"], True, "Добавить товар", ["OneAlma"]),
            ("/one_alma/products/{product_id}", self.one_alma_update_product, ["PUT"], True, "Изменить товар", ["OneAlma"]),
            ("/one_alma/products", self.one_alma_delete_products, ["DELETE"], True, "Удалить товары", ["OneAlma"]),
            ("/one_alma/import/template", self.one_alma_import_template, ["GET"], True, "Шаблон поставки", ["OneAlma"]),
            ("/one_alma/import", self.one_alma_import, ["POST"], True, "Импорт товаров из Excel", ["OneAlma"]),
        ]
        for path, endpoint, methods, protected, summary, tags in routes:
            self.router.add_api_route(
                path,
                endpoint,
                methods=methods,
                dependencies=self.dependencies if protected else [],
                summary=summary,
                tags=list(tags),
                response_model=None,
            )

    def _status_page(self, request: Request, *, template: str, cookie: str, error: str) -> Response:
        encoded_status = request.cookies.get(cookie)
        status = None
        if encoded_status:
            try:
                status = base64.b64decode(encoded_status.encode("ascii")).decode("utf-8")
            except Exception as exc:
                logger.exception(error)
                status = f"Ошибка декодирования статуса, {exc}"
        response = self.templates.TemplateResponse(request, template, {"status": status})
        if encoded_status:
            response.delete_cookie(cookie)
        return response
