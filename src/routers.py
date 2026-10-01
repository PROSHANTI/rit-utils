import base64
import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from src.auth import AuthenticationService
from src.utils.doctor_form.doctor_form_handler import DoctorFormGenerator, DoctorFormRequest
from src.utils.gen_cert.gen_cert_handler import CertificateGenerator, CertificateRequest
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

    def _register_routes(self) -> None:
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
