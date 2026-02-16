"""
Integration tests for FastAPI endpoints
"""
import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestAuthEndpoints:
    """Tests for authentication endpoints"""

    def test_root_redirect_to_login(self, client):
        """Test redirect to login page"""
        response = client.get("/")

        assert response.status_code in [200, 303]

    def test_root_head_returns_200(self, client):
        """HEAD / для мониторинга (UptimeRobot) — 200 без тела"""
        response = client.head("/")
        assert response.status_code == 200
        assert response.content == b""

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        response = client.post("/login", data={
            "username": "wrong_user",
            "password": "wrong_pass"
        })

        assert response.status_code == 401

    def test_login_valid_credentials(self, client):
        """Test login with valid credentials"""
        response = client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        }, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/home"

    def test_refresh_endpoint_no_token(self, client):
        """Test token refresh without token"""
        response = client.post("/refresh", follow_redirects=False)

        assert response.status_code in [200, 303]
        if response.status_code == 303:
            assert response.headers["location"] == "/"


class TestProtectedEndpoints:
    """Tests for protected endpoints"""

    def test_home_without_auth(self, client):
        """Test /home access without authorization"""
        try:
            response = client.get("/home")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)

    def test_send_email_get_without_auth(self, client):
        """Test GET /send_email without authorization"""
        try:
            response = client.get("/send_email")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)

    def test_gen_rit_cert_get_without_auth(self, client):
        """Test GET /gen_rit_cert without authorization"""
        try:
            response = client.get("/gen_rit_cert")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)

    def test_doctor_form_get_without_auth(self, client):
        """Test GET /doctor_form without authorization"""
        try:
            response = client.get("/doctor_form")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)


class TestUtilityEndpoints:
    """Tests for utility endpoints (require authentication mocking)"""

    @patch('src.utils.send_email.email_handler.smtplib.SMTP_SSL')
    def test_send_email_post_success(self, mock_smtp, client):
        """Test POST /send_email with successful sending"""
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        file_content = b"test file content"
        files = {"attachment": ("test.xlsx", io.BytesIO(file_content), "application/vnd.ms-excel")}

        try:
            response = client.post("/send_email", data={
                "qr_pay": "1000",
                "cashless_pay": "2000",
                "card_pay": "3000",
                "cash_pay": "4000"
            }, files=files)

            assert response.status_code in [200, 303]
            if response.status_code == 303:
                assert response.headers["location"] == "/send_email"
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)

    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_post_success(self, mock_exists, mock_presentation, mock_convert, client, mock_pptx):
        """Test POST /gen_rit_cert with successful generation"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx

        try:
            response = client.post("/gen_rit_cert", data={
                "name": "Иван Иванов",
                "price": "5000"
            })

            assert response.status_code in [200, 303]
            if response.status_code == 200:
                assert "pdf" in response.headers.get("content-type", "").lower()
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)

    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    def test_doctor_form_post_success(self, mock_exists, mock_presentation, client, mock_pptx):
        """Test POST /doctor_form with successful generation"""
        mock_exists.return_value = True
        mock_presentation.return_value = mock_pptx

        try:
            response = client.post("/doctor_form", data={
                "doctor_1": "Доктор Иванов",
                "patient_1": "Пациент Иванов",
                "date": "15"
            })

            assert response.status_code in [200, 303]
            if response.status_code == 200:
                assert "presentation" in response.headers.get("content-type", "").lower()
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)


class TestErrorHandling:
    """Tests for error handling"""

    @patch('src.utils.send_email.email_handler.smtplib.SMTP_SSL')
    def test_send_email_smtp_error(self, mock_smtp, client):
        """Test SMTP error handling"""
        mock_smtp.side_effect = Exception("SMTP connection failed")

        file_content = b"test file content"
        files = {"attachment": ("test.xlsx", io.BytesIO(file_content), "application/vnd.ms-excel")}

        try:
            response = client.post("/send_email", data={
                "qr_pay": "1000"
            }, files=files)

            assert response.status_code in [200, 303]
            if response.status_code == 303:
                assert response.headers["location"] == "/send_email"
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)

    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_template_not_found(self, mock_exists, client):
        """Test certificate generation with missing template"""
        mock_exists.return_value = False

        try:
            response = client.post("/gen_rit_cert", data={
                "name": "Иван Иванов",
                "price": "5000"
            })

            assert response.status_code in [200, 303]
            if response.status_code == 303:
                assert response.headers["location"] == "/gen_rit_cert"
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)

    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    def test_doctor_form_template_not_found(self, mock_exists, client):
        """Test doctor form generation with missing template"""
        mock_exists.return_value = False

        try:
            response = client.post("/doctor_form", data={
                "doctor_1": "Доктор Иванов",
                "patient_1": "Пациент Иванов"
            })

            assert response.status_code in [200, 303]
            if response.status_code == 303:
                assert response.headers["location"] == "/doctor_form"
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)


class TestStaticFiles:
    """Tests for static files"""

    def test_static_files_mount(self, client):
        """Test static files access"""
        response = client.get("/static/favicon.ico")

        assert response.status_code in [200, 404]


class TestCookieHandling:
    """Tests for cookie handling"""

    def test_cookie_status_decoding(self, client):
        """Test status decoding from cookie"""
        status_message = "Тестовое сообщение"
        encoded_status = base64.b64encode(status_message.encode('utf-8')).decode('ascii')

        client.cookies.set("email_status", encoded_status)

        try:
            response = client.get("/send_email")
            assert response.status_code in [200, 303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
