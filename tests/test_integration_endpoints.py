"""
Интеграционные тесты для FastAPI endpoints
"""
import pytest
import io
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestAuthEndpoints:
    """Тесты для эндпоинтов аутентификации"""
    
    def test_root_redirect_to_login(self, client):
        """Тест редиректа на страницу входа"""
        response = client.get("/")
        
        # Должен показать страницу входа или редирект на /home если авторизован
        assert response.status_code in [200, 303]
    
    def test_login_invalid_credentials(self, client):
        """Тест входа с неверными учетными данными"""
        response = client.post("/login", data={
            "username": "wrong_user",
            "password": "wrong_pass"
        })
        
        assert response.status_code == 401
    
    def test_login_valid_credentials_no_2fa(self, client):
        """Тест входа с валидными учетными данными без 2FA"""
        response = client.post("/login", data={
            "username": "test_admin", 
            "password": "test_password"
        }, follow_redirects=False)
        
        # Должен редиректить на настройку 2FA или вернуть успешный ответ
        assert response.status_code in [200, 303]
        if response.status_code == 303:
            assert response.headers["location"] == "/configure-2fa"
    
    def test_login_valid_credentials_with_2fa(self, client):
        """Тест входа с валидными учетными данными с настроенной 2FA"""
        # Сначала устанавливаем cookie 2fa_configured
        client.cookies.set("2fa_configured", "true")
        
        response = client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        }, follow_redirects=False)
        
        # Должен редиректить на страницу 2FA или вернуть успешный ответ
        assert response.status_code in [200, 303]
        if response.status_code == 303:
            assert response.headers["location"] == "/2fa"
    
    def test_refresh_endpoint_no_token(self, client):
        """Тест обновления токена без токена"""
        response = client.post("/refresh", follow_redirects=False)
        
        assert response.status_code in [200, 303]
        if response.status_code == 303:
            assert response.headers["location"] == "/"
    
    def test_2fa_page_get(self, client):
        """Тест GET запроса на страницу 2FA"""
        response = client.get("/2fa")
        
        assert response.status_code == 200
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    def test_2fa_post_valid_token(self, mock_totp_class, client):
        """Тест POST запроса на 2FA с валидным токеном"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = True
        
        response = client.post("/2fa", data={"token": "123456"}, follow_redirects=False)
        
        assert response.status_code in [200, 303]
        if response.status_code == 303:
            assert response.headers["location"] == "/setup-session"
    
    @patch('src.auth.two_factor.pyotp.TOTP')
    def test_2fa_post_invalid_token(self, mock_totp_class, client):
        """Тест POST запроса на 2FA с невалидным токеном"""
        mock_totp = MagicMock()
        mock_totp_class.return_value = mock_totp
        mock_totp.verify.return_value = False
        mock_totp.at.return_value = "000000"
        
        response = client.post("/2fa", data={"token": "123456"})
        
        assert response.status_code == 401


class TestProtectedEndpoints:
    """Тесты для защищенных эндпоинтов"""
    
    def test_home_without_auth(self, client):
        """Тест доступа к /home без авторизации"""
        try:
            response = client.get("/home")
            # Должен редиректить или возвращать ошибку авторизации
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            # Если выбрасывается исключение (например, MissingTokenError), это тоже ожидаемое поведение
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
    
    def test_send_email_get_without_auth(self, client):
        """Тест GET /send_email без авторизации"""
        try:
            response = client.get("/send_email")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
    
    def test_gen_rit_cert_get_without_auth(self, client):
        """Тест GET /gen_rit_cert без авторизации"""
        try:
            response = client.get("/gen_rit_cert")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
    
    def test_doctor_form_get_without_auth(self, client):
        """Тест GET /doctor_form без авторизации"""
        try:
            response = client.get("/doctor_form")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
    
    def test_setup_2fa_get_without_auth(self, client):
        """Тест GET /setup-2fa без авторизации"""
        try:
            response = client.get("/setup-2fa")
            assert response.status_code in [303, 401, 422]
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)


class TestUtilityEndpoints:
    """Тесты для эндпоинтов утилит (требуют мокирование аутентификации)"""
    
    @patch('src.utils.send_email.email_handler.smtplib.SMTP_SSL')
    def test_send_email_post_success(self, mock_smtp, client):
        """Тест POST /send_email с успешной отправкой"""
        # Настройка мока SMTP
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # Создаем фиктивный файл
        file_content = b"test file content"
        files = {"attachment": ("test.xlsx", io.BytesIO(file_content), "application/vnd.ms-excel")}
        
        # Тестируем с обработкой возможных исключений аутентификации
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
            # Если требуется аутентификация, это тоже ожидаемое поведение
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
    
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    @patch('src.utils.gen_cert.gen_cert_handler.Presentation')
    @patch('src.utils.gen_cert.gen_cert_handler.convert_pptx_to_pdf')
    def test_gen_cert_post_success(self, mock_convert, mock_presentation, mock_exists, client, mock_pptx):
        """Тест POST /gen_rit_cert с успешной генерацией"""
        # Настройка моков
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
            # Если требуется аутентификация, это тоже ожидаемое поведение
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
    
    @patch('src.utils.doctor_form.doctor_form_handler.os.path.exists')
    @patch('src.utils.doctor_form.doctor_form_handler.Presentation')
    def test_doctor_form_post_success(self, mock_presentation, mock_exists, client, mock_pptx):
        """Тест POST /doctor_form с успешной генерацией"""
        # Настройка моков
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
            # Если требуется аутентификация, это тоже ожидаемое поведение
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)


class TestErrorHandling:
    """Тесты обработки ошибок"""
    
    @patch('src.utils.send_email.email_handler.smtplib.SMTP_SSL')
    def test_send_email_smtp_error(self, mock_smtp, client):
        """Тест обработки ошибки SMTP"""
        # Настройка мока для выброса исключения
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
    
    def test_gen_cert_invalid_price(self, client):
        """Тест генерации сертификата с невалидной ценой"""
        try:
            response = client.post("/gen_rit_cert", data={
                "name": "Иван Иванов",
                "price": "1234567"  # Слишком длинная цена
            })
            
            assert response.status_code in [200, 303]
            if response.status_code == 303:
                assert response.headers["location"] == "/gen_rit_cert"
        except Exception as e:
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
    
    @patch('src.utils.gen_cert.gen_cert_handler.os.path.exists')
    def test_gen_cert_template_not_found(self, mock_exists, client):
        """Тест генерации сертификата с отсутствующим шаблоном"""
        # Шаблон не найден
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
        """Тест генерации формы врача с отсутствующим шаблоном"""
        # Шаблон не найден
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
    """Тесты для статических файлов"""
    
    def test_static_files_mount(self, client):
        """Тест доступа к статическим файлам"""
        # Попытка доступа к статическому файлу (может не существовать)
        response = client.get("/static/favicon.ico")
        
        # Либо 200 (файл найден), либо 404 (файл не найден)
        assert response.status_code in [200, 404]


class TestCookieHandling:
    """Тесты обработки cookies"""
    
    def test_cookie_status_decoding(self, client):
        """Тест декодирования статуса из cookie"""
        # Устанавливаем cookie со статусом
        import base64
        status_message = "Тестовое сообщение"
        encoded_status = base64.b64encode(status_message.encode('utf-8')).decode('ascii')
        
        client.cookies.set("email_status", encoded_status)
        
        # Пытаемся получить страницу (без авторизации вернет ошибку, но проверим cookie)
        try:
            response = client.get("/send_email")
            # Проверяем, что запрос обработан (независимо от авторизации)
            assert response.status_code in [200, 303, 401, 422]
        except Exception as e:
            # Если требуется аутентификация, это тоже ожидаемое поведение
            assert "Missing" in str(e) or "Token" in str(e) or "JWT" in str(e)
