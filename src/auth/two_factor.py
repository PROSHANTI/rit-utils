import os
import pyotp
import qrcode
import base64
import hashlib
from io import BytesIO
from fastapi import Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import src.config  # noqa: F401

templates = Jinja2Templates(directory="templates")

TOTP_SECRET = os.getenv('TOTP_SECRET')
if not TOTP_SECRET:
    raise ValueError(
        "TOTP_SECRET не задан в переменных окружения. "
        "Добавьте TOTP_SECRET в .env файл. "
        "Сгенерировать секрет: python -c 'import pyotp; print(pyotp.random_base32())'"
    )

USER_SECRETS: dict[str, str] = {}

def generate_totp_secret() -> str:
    """Генерирует новый секретный ключ для TOTP"""
    return pyotp.random_base32()

def get_user_secret(username: str, generate_if_missing: bool = True) -> str:
    """
    Получает или генерирует персональный секрет для пользователя
    
    Args:
        username: имя пользователя
        generate_if_missing: генерировать ли новый секрет, если его нет
    
    Returns:
        Base32 секрет для данного пользователя
    """
    if username not in USER_SECRETS:
        if generate_if_missing:
            combined = f"{TOTP_SECRET}:{username}"
            hash_bytes = hashlib.sha256(combined.encode()).digest()
            
            secret = base64.b32encode(hash_bytes[:20]).decode()
            USER_SECRETS[username] = secret
        else:
            return TOTP_SECRET or ""
    
    return USER_SECRETS[username]

def get_totp_uri(username: str, secret: str | None = None) -> str:
    """
    Генерирует URI для QR-кода
    
    Args:
        username: имя пользователя
        secret: конкретный секрет или None для автоматического получения
    
    Returns:
        URI для QR-кода
    """
    if secret is None:
        secret = get_user_secret(username)
    
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=username,
        issuer_name="RIT-UTILS"
    )
    return uri

def generate_qr_code(uri: str) -> str:
    """Генерирует QR-код в base64"""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, "PNG")  # Убираем параметр format=
        buffer.seek(0)
        
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        return qr_base64
    except Exception:
        return ""

def verify_totp(token: str, username: str = "admin", secret: str | None = None) -> bool:
    """
    Проверяет TOTP токен
    
    Args:
        token: 6-значный код из приложения
        username: имя пользователя (для получения персонального секрета)
        secret: конкретный секрет или None для автоматического получения
    
    Returns:
        True если токен валиден
    """
    try:
        if secret is None:
            secret = get_user_secret(username, generate_if_missing=False)
        
        totp = pyotp.TOTP(secret)
        result = totp.verify(token)
        return result
    except Exception:
        return False

def two_factor_handler(request: Request, token: str = Form(...)):
    """Обработчик 2FA"""
    username = "admin"

    user_secret = request.cookies.get("user_totp_secret")
    
    if user_secret:
        if verify_totp(token, username, user_secret):
            response = RedirectResponse(url="/setup-session", status_code=303)
            response.set_cookie(
                "2fa_verified", "true", httponly=True, secure=True, samesite="strict"
                )
            return response
    else:
        # Пробуем персональный секрет пользователя
        if verify_totp(token, username):
            response = RedirectResponse(url="/setup-session", status_code=303)
            response.set_cookie(
                "2fa_verified", "true", httponly=True, secure=True, samesite="strict"
                )
            return response
    
    return templates.TemplateResponse(
        "two_factor.html",
        {"request": request, "error": "Неверный код 2FA"},
        status_code=401
    )

def show_two_factor_page(request: Request):
    """Показывает страницу ввода 2FA"""
    return templates.TemplateResponse(
        "two_factor.html",
        {"request": request}
    )

def is_2fa_verified(request: Request) -> bool:
    """Проверяет, прошла ли пользователь 2FA"""
    return request.cookies.get("2fa_verified") == "true"

def clear_2fa_verification(request: Request) -> RedirectResponse:
    """Очищает 2FA верификацию при выходе"""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        "2fa_verified", httponly=True, secure=True, samesite="strict"
        )
    return response
