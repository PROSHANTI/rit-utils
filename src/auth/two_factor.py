import os
import pyotp
import qrcode
import base64
import hashlib
from io import BytesIO
from fastapi import Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from .cookie_utils import set_secure_cookie, delete_secure_cookie, get_cookie_settings

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
        
        print(f"🔐 TOTP Debug:")
        print(f"   Token: {token}")
        print(f"   Secret: {secret}")
        print(f"   Username: {username}")
        
        totp = pyotp.TOTP(secret)
        
        # Проверяем с расширенным окном времени (±2 периода = ±60 секунд)
        result = totp.verify(token, valid_window=2)
        
        print(f"   Current server code: {totp.now()}")
        print(f"   Verification result: {result}")
        
        return result
    except Exception as e:
        print(f"❌ TOTP Error: {e}")
        return False

def two_factor_handler(request: Request, token: str = Form(...)):
    """Обработчик 2FA"""
    username = "admin"

    user_secret = request.cookies.get("user_totp_secret")
    
    print(f"🍪 2FA Handler Debug:")
    print(f"   Token from form: {token}")
    print(f"   User secret from cookie: {user_secret}")
    
    # Всегда используем детерминистичный секрет для надежности
    global_secret = get_user_secret(username)
    print(f"   Global secret: {global_secret}")
    
    # Проверяем сначала cookie секрет, потом глобальный
    if user_secret and verify_totp(token, username, user_secret):
        print("✅ Verification successful with cookie secret")
        response = RedirectResponse(url="/setup-session", status_code=303)
        set_secure_cookie(response, request, "2fa_verified", "true")
        return response
    elif verify_totp(token, username, global_secret):
        print("✅ Verification successful with global secret")
        response = RedirectResponse(url="/setup-session", status_code=303)
        set_secure_cookie(response, request, "2fa_verified", "true")
        return response
    
    print("❌ Both verification attempts failed")
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
