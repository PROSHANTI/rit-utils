import base64
import datetime
import smtplib
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.responses import Response
from httpx import Response as HttpResponse

from src.main import application
from src.utils.doctor_form.doctor_form_handler import DoctorFormRequest
from src.utils.gen_cert.gen_cert_handler import CertificateRequest


def _response_cookies(response: HttpResponse) -> SimpleCookie:
    cookies = SimpleCookie()

    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)

    return cookies


def _status_from_cookie(response: HttpResponse, name: str) -> str:
    encoded_status = _response_cookies(response)[name].value
    return base64.b64decode(encoded_status, validate=True).decode("utf-8")


class TestAuthEndpoints:
    def test_root_without_session_renders_login_page(self, client):
        response = client.get("/", follow_redirects=False)

        assert response.status_code == 200
        assert 'action="/login"' in response.text
        assert response.headers["content-type"].startswith("text/html")

    def test_root_with_session_redirects_home(self, authenticated_client):
        response = authenticated_client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_root_head_returns_empty_success_for_monitoring(self, client):
        response = client.head("/")

        assert response.status_code == 200
        assert response.content == b""

    def test_invalid_credentials_render_login_error(self, client):
        response = client.post("/login", data={"username": "wrong_user", "password": "wrong_pass"}, follow_redirects=False)

        assert response.status_code == 401
        assert "Неверный логин или пароль" in response.text
        assert not response.headers.get_list("set-cookie")

    def test_valid_credentials_set_protected_session_cookies(self, authenticated_client):
        response = authenticated_client.post(
            "/login", data={"username": "test_admin", "password": "test_password"}, follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/home"
        cookies = _response_cookies(response)
        access_name = application.auth.config.JWT_ACCESS_COOKIE_NAME
        refresh_name = application.auth.config.JWT_REFRESH_COOKIE_NAME
        assert set(cookies) == {access_name, refresh_name}

        for cookie in cookies.values():
            assert cookie.value
            assert cookie["secure"] is True
            assert cookie["httponly"] is True
            assert cookie["samesite"] == "lax"

        assert cookies[refresh_name]["max-age"] == f"{7 * 24 * 60 * 60}"
        assert authenticated_client.get("/home").status_code == 200

    def test_refresh_without_cookie_redirects_login(self, client):
        response = client.post("/refresh", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_refresh_rotates_access_token_and_preserves_refresh_token(self, authenticated_client):
        access_name = application.auth.config.JWT_ACCESS_COOKIE_NAME
        refresh_name = application.auth.config.JWT_REFRESH_COOKIE_NAME
        previous_access = authenticated_client.cookies.get(access_name)
        previous_refresh = authenticated_client.cookies.get(refresh_name)

        response = authenticated_client.post("/refresh", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/home"
        assert authenticated_client.cookies.get(access_name) != previous_access
        assert authenticated_client.cookies.get(refresh_name) == previous_refresh
        assert authenticated_client.get("/home").status_code == 200

    def test_logout_removes_cookies_and_rejects_replayed_refresh(self, authenticated_client):
        access_name = application.auth.config.JWT_ACCESS_COOKIE_NAME
        refresh_name = application.auth.config.JWT_REFRESH_COOKIE_NAME
        previous_refresh = authenticated_client.cookies.get(refresh_name)
        assert previous_refresh is not None

        response = authenticated_client.post("/logout", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        cookies = _response_cookies(response)
        assert set(cookies) == {access_name, refresh_name}
        assert all(cookie["max-age"] == "0" for cookie in cookies.values())
        assert authenticated_client.cookies.get(access_name) is None
        assert authenticated_client.cookies.get(refresh_name) is None
        authenticated_client.cookies.set(refresh_name, previous_refresh, domain="testserver.local", path="/")

        replay_response = authenticated_client.post("/refresh", follow_redirects=False)

        assert replay_response.status_code == 303
        assert replay_response.headers["location"] == "/"
        assert authenticated_client.cookies.get(refresh_name) is None


class TestProtectedEndpoints:
    @pytest.mark.parametrize(
        ("path", "method"),
        [
            pytest.param("/home", "GET", id="home-get"),
            pytest.param("/send_email", "GET", id="email-get"),
            pytest.param("/gen_rit_cert", "GET", id="certificate-get"),
            pytest.param("/doctor_form", "GET", id="doctor-get"),
            pytest.param("/remove_bg", "GET", id="image-get"),
            pytest.param("/logout", "POST", id="logout-post"),
            pytest.param("/send_email", "POST", id="email-post"),
            pytest.param("/gen_rit_cert", "POST", id="certificate-post"),
            pytest.param("/doctor_form", "POST", id="doctor-post"),
            pytest.param("/remove_bg", "POST", id="image-post"),
        ],
    )
    def test_missing_auth_redirects_login_and_clears_session(self, client, path, method):
        with (
            patch.object(application.auth, "logout") as logout,
            patch.object(application.routes, "email") as email,
            patch.object(application.routes, "certificates") as certificates,
            patch.object(application.routes, "doctor_forms") as doctor_forms,
            patch.object(application.routes, "images") as images,
        ):
            response = client.request(method, path, follow_redirects=False)

        logout.assert_not_called()
        email.handle.assert_not_called()
        certificates.generate.assert_not_called()
        doctor_forms.generate.assert_not_called()
        images.handle.assert_not_called()

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        cookies = _response_cookies(response)
        assert set(cookies) == {
            application.auth.config.JWT_ACCESS_COOKIE_NAME,
            application.auth.config.JWT_REFRESH_COOKIE_NAME,
        }
        assert all(cookie["max-age"] == "0" for cookie in cookies.values())

    @pytest.mark.parametrize(
        ("path", "page_content"),
        [
            pytest.param("/home", "Инструменты для автоматизации рабочих процессов", id="home"),
            pytest.param("/send_email", 'action="/send_email"', id="email"),
            pytest.param("/gen_rit_cert", 'action="/gen_rit_cert"', id="certificate"),
            pytest.param("/doctor_form", 'action="/doctor_form"', id="doctor-form"),
            pytest.param("/remove_bg", 'action="/remove_bg"', id="image"),
        ],
    )
    def test_authenticated_get_renders_expected_page(self, authenticated_client, path, page_content):
        response = authenticated_client.get(path, follow_redirects=False)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert page_content in response.text


class TestEmailEndpoints:
    @patch("src.utils.send_email.email_handler.datetime")
    def test_post_sends_formatted_report_and_displays_status_once(self, mock_datetime, authenticated_client, mock_smtp):
        mock_datetime.datetime.now.return_value = datetime.datetime(2024, 3, 15, 18, 45)

        response = authenticated_client.post(
            "/send_email",
            data={"qr_pay": "1000", "cashless_pay": "2000", "card_pay": "3000 ( долг )", "cash_pay": "4000"},
            files={"attachment": ("report.xlsx", b"test report", "application/vnd.ms-excel")},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/send_email"
        assert _status_from_cookie(response, "email_status") == "Письмо успешно отправлено в 18:45"
        assert _response_cookies(response)["email_status"]["max-age"] == "10"
        mock_smtp.send_message.assert_called_once()
        message = mock_smtp.send_message.call_args.args[0]
        body = message.get_payload(0).get_payload(decode=True).decode("utf-8")
        assert body == (
            "Добрый вечер!\n\nБезналичная оплата: 2000\nНа карту: 3000 (долг)\nQR-код: 1000\nНаличные: 4000\n\nС уважением"
        )
        attachment = message.get_payload(1)
        assert attachment.get_payload(decode=True) == b"test report"
        assert attachment.get_filename() == "15.03.24.xlsx"
        mock_smtp.quit.assert_called_once()
        mock_smtp.close.assert_called_once()

        status_page = authenticated_client.get("/send_email")

        assert status_page.status_code == 200
        assert "Письмо успешно отправлено в 18:45" in status_page.text
        assert _response_cookies(status_page)["email_status"]["max-age"] == "0"
        assert authenticated_client.cookies.get("email_status") is None
        assert "Письмо успешно отправлено в 18:45" not in authenticated_client.get("/send_email").text

    def test_partial_report_omits_empty_and_missing_payments(self, authenticated_client, mock_smtp):
        response = authenticated_client.post(
            "/send_email",
            data={"qr_pay": "1000", "cash_pay": ""},
            files={"attachment": ("report.xlsx", b"test report", "application/vnd.ms-excel")},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/send_email"
        message = mock_smtp.send_message.call_args.args[0]
        body = message.get_payload(0).get_payload(decode=True).decode("utf-8")
        assert body == "Добрый вечер!\n\nQR-код: 1000\n\nС уважением"

    @pytest.mark.parametrize(
        ("smtp_error", "expected_status"),
        [
            pytest.param(
                smtplib.SMTPAuthenticationError(525, b"SMTP disabled"),
                "Ошибка отправки: SMTP отключён для этого почтового ящика",
                id="smtp-disabled",
            ),
            pytest.param(
                smtplib.SMTPAuthenticationError(535, b"Invalid credentials"),
                "Ошибка отправки: проверьте настройки доступа к почте",
                id="invalid-credentials",
            ),
            pytest.param(
                RuntimeError("SMTP operation failed"),
                "Ошибка отправки письма. Подробности — в логах сервера",
                id="unexpected-smtp-error",
            ),
        ],
    )
    def test_smtp_failure_sets_status_cookie_and_does_not_send(
        self, authenticated_client, mock_smtp, smtp_error, expected_status
    ):
        mock_smtp.login.side_effect = smtp_error

        response = authenticated_client.post(
            "/send_email",
            data={"qr_pay": "1000"},
            files={"attachment": ("report.xlsx", b"test report", "application/vnd.ms-excel")},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/send_email"
        assert _status_from_cookie(response, "email_status") == expected_status
        assert _response_cookies(response)["email_status"]["max-age"] == "10"
        mock_smtp.send_message.assert_not_called()
        mock_smtp.close.assert_called_once()

    def test_missing_attachment_returns_validation_error(self, authenticated_client, mock_smtp):
        response = authenticated_client.post("/send_email", data={"qr_pay": "1000"}, follow_redirects=False)

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "attachment"]
        mock_smtp.send_message.assert_not_called()


class TestDocumentEndpoints:
    def test_certificate_post_passes_form_fields_to_generator(self, authenticated_client):
        with patch.object(
            application.routes.certificates, "generate", return_value=Response(b"PDF content", media_type="application/pdf")
        ) as generate:
            response = authenticated_client.post("/gen_rit_cert", data={"name": "recipient", "price": "5000"})

        assert response.status_code == 200
        assert response.content == b"PDF content"
        assert response.headers["content-type"] == "application/pdf"
        generate.assert_called_once_with(CertificateRequest(name="recipient", price="5000"))

    def test_doctor_form_post_passes_all_slots_to_generator(self, authenticated_client):
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        with patch.object(
            application.routes.doctor_forms, "generate", return_value=Response(b"PPTX content", media_type=media_type)
        ) as generate:
            response = authenticated_client.post(
                "/doctor_form",
                data={
                    "doctor_1": "doctor 1",
                    "doctor_2": "doctor 2",
                    "doctor_3": "doctor 3",
                    "doctor_4": "doctor 4",
                    "patient_1": "patient 1",
                    "patient_2": "patient 2",
                    "patient_3": "patient 3",
                    "patient_4": "patient 4",
                    "date": "20",
                },
            )

        assert response.status_code == 200
        assert response.content == b"PPTX content"
        assert response.headers["content-type"] == media_type
        generate.assert_called_once_with(
            DoctorFormRequest(
                doctors=("doctor 1", "doctor 2", "doctor 3", "doctor 4"),
                patients=("patient 1", "patient 2", "patient 3", "patient 4"),
                date="20",
            )
        )

    @pytest.mark.parametrize(
        ("generator_name", "path", "cookie_name", "status_prefix"),
        [
            pytest.param(
                "certificates",
                "/gen_rit_cert",
                "gen_cert_status",
                "Ошибка генерации сертификата: Файл шаблона не найден:",
                id="certificate",
            ),
            pytest.param(
                "doctor_forms",
                "/doctor_form",
                "doctor_form_status",
                "Ошибка обработки файла: Файл шаблона не найден:",
                id="doctor-form",
            ),
        ],
    )
    def test_missing_template_redirects_with_status(
        self, authenticated_client, monkeypatch, tmp_path, generator_name, path, cookie_name, status_prefix
    ):
        generator = getattr(application.routes, generator_name)
        monkeypatch.setattr(generator, "template_path", tmp_path / "missing-template.pptx")

        response = authenticated_client.post(path, data={"date": "15"}, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == path
        assert _status_from_cookie(response, cookie_name).startswith(status_prefix)
        assert _response_cookies(response)[cookie_name]["max-age"] == "10"


class TestStatusPages:
    @pytest.mark.parametrize(
        ("path", "cookie_name"),
        [
            ("/send_email", "email_status"),
            ("/gen_rit_cert", "gen_cert_status"),
            ("/doctor_form", "doctor_form_status"),
            ("/remove_bg", "remove_bg_status"),
        ],
    )
    def test_utf8_status_cookie_is_rendered_then_cleared(self, authenticated_client, path, cookie_name):
        status_message = "Тестовое сообщение: операция завершена"
        encoded_status = base64.b64encode(status_message.encode("utf-8")).decode("ascii")
        authenticated_client.cookies.set(cookie_name, encoded_status, domain="testserver.local", path="/")

        response = authenticated_client.get(path)

        assert response.status_code == 200
        assert status_message in response.text
        assert _response_cookies(response)[cookie_name]["max-age"] == "0"
        assert authenticated_client.cookies.get(cookie_name) is None
        assert status_message not in authenticated_client.get(path).text

    @pytest.mark.parametrize("cookie_value", ["not-base64", "/w=="])
    def test_invalid_status_cookie_displays_decode_error_and_is_cleared(self, authenticated_client, cookie_value):
        authenticated_client.cookies.set("email_status", cookie_value, domain="testserver.local", path="/")

        response = authenticated_client.get("/send_email")

        assert response.status_code == 200
        assert "Ошибка декодирования статуса" in response.text
        assert _response_cookies(response)["email_status"]["max-age"] == "0"
        assert authenticated_client.cookies.get("email_status") is None


class TestStaticFiles:
    def test_static_favicon_is_available(self, client):
        response = client.get("/static/favicon.ico")

        assert response.status_code == 200
        assert response.content == Path("templates/favicon.ico").read_bytes()

    def test_missing_static_file_returns_not_found(self, client):
        response = client.get("/static/missing-test-file.css")

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
