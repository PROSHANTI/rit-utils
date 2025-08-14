import os
import datetime
import uuid
from typing import Set
from fastapi import Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from authx import AuthX, AuthXConfig
from .cookie_utils import set_secure_cookie, delete_secure_cookie, get_cookie_settings
from authx.exceptions import JWTDecodeError
from dotenv import load_dotenv
from .two_factor import is_2fa_verified

load_dotenv()

REVOKED_TOKENS: Set[str] = set()

config = AuthXConfig()
config.JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
config.JWT_ACCESS_COOKIE_NAME = "JWT_ACCESS_TOKEN_COOKIE"
config.JWT_REFRESH_COOKIE_NAME = "JWT_REFRESH_TOKEN_COOKIE"
config.JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=15) 
config.JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=7) 
config.JWT_TOKEN_LOCATION = ["cookies"]
config.JWT_COOKIE_CSRF_PROTECT = False
config.JWT_COOKIE_SECURE = True
config.JWT_COOKIE_SAMESITE = "strict" 
security: AuthX = AuthX(config=config)

LOGIN = os.getenv('LOGIN')
PASSWORD = os.getenv('PASSWORD')

templates = Jinja2Templates(directory="templates")

def get_auth_dependency():
    return Depends(security.access_token_required)

def login_handler(
    request: Request, username: str = Form(...), password: str = Form(...)
    ):
    """Обработчик авторизации"""
    if username == LOGIN and password == PASSWORD:
        twofa_configured = request.cookies.get("2fa_configured")
        
        if twofa_configured:
            response = RedirectResponse(url="/2fa", status_code=303)
        else:
            response = RedirectResponse(url="/configure-2fa", status_code=303)
            
        set_secure_cookie(response, request, "auth_pending", "true", max_age=300)
        
        return response
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неверный логин или пароль"},
        status_code=401
    )

def logout_handler(request: Request):
    """Обработчик выхода из системы"""
    refresh_token = request.cookies.get(config.JWT_REFRESH_COOKIE_NAME)
    if refresh_token:
        REVOKED_TOKENS.add(refresh_token)
    
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        key=config.JWT_ACCESS_COOKIE_NAME,
        path="/",
        domain=None,
        secure=True,
        httponly=True,
        samesite="strict"
    )
    response.delete_cookie(
        key=config.JWT_REFRESH_COOKIE_NAME,
        path="/",
        domain=None,
        secure=True,
        httponly=True,
        samesite="strict"
    )
    response.delete_cookie(
        "2fa_verified", httponly=True, secure=True, samesite="strict"
        )
    response.delete_cookie(
        "auth_pending", httponly=True, secure=True, samesite="strict"
        )
    response.delete_cookie(
        "user_totp_secret", httponly=True, secure=True, samesite="strict"
        )
    return response

def refresh_token_handler(request: Request):
    """Обработчик обновления токена доступа"""
    refresh_token = request.cookies.get(config.JWT_REFRESH_COOKIE_NAME)
    
    if not refresh_token:
        return RedirectResponse(url="/", status_code=303)
    
    if refresh_token in REVOKED_TOKENS:
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(
            config.JWT_ACCESS_COOKIE_NAME, secure=True, samesite="strict"
            )
        response.delete_cookie(
            config.JWT_REFRESH_COOKIE_NAME,secure=True, samesite="strict"
            )
        return response
    
    try:        
        payload = security._decode_token(refresh_token)
        if not hasattr(payload, 'jti'):
            raise Exception("Invalid token format")
            
        new_access_token = security.create_access_token(
            uid=payload.sub,
            jti=str(uuid.uuid4())
        )
        response = RedirectResponse(url="/home", status_code=303)
        response.set_cookie(
            key=config.JWT_ACCESS_COOKIE_NAME,
            value=new_access_token,
            httponly=True,
            secure=True,
            samesite="strict"
        )
        return response
    except Exception:
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(
            config.JWT_ACCESS_COOKIE_NAME, secure=True, samesite="strict"
            )
        response.delete_cookie(
            config.JWT_REFRESH_COOKIE_NAME, secure=True, samesite="strict"
            )
        return response

async def jwt_decode_exception_handler(request: Request, exc: Exception):
    """Обработчик ошибок JWT декодирования"""
    if isinstance(exc, JWTDecodeError) and "expired" in str(exc).lower():
        if request.headers.get("accept") == "application/json":
            return JSONResponse(
                status_code=401,
                content={"detail": "Token expired"}
            )
        
        refresh_response = RedirectResponse(url="/", status_code=303)
        refresh_response.delete_cookie(config.JWT_ACCESS_COOKIE_NAME)
        return refresh_response
    
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(config.JWT_ACCESS_COOKIE_NAME)
    response.delete_cookie(config.JWT_REFRESH_COOKIE_NAME)
    return response

def check_auth_status(request: Request):
    """Проверка статуса авторизации"""
    if request.cookies.get(config.JWT_ACCESS_COOKIE_NAME):
        return RedirectResponse(url="/home", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})

def setup_2fa_session(request: Request):
    """Настройка сессии после успешной 2FA"""
    if not is_2fa_verified(request):
        return RedirectResponse(url="/2fa", status_code=303)
    
    response = RedirectResponse(url="/home", status_code=303)
    
    access_token = security.create_access_token(
        uid='1',
        jti=str(uuid.uuid4())
    )
    set_secure_cookie(response, request, config.JWT_ACCESS_COOKIE_NAME, access_token)
    
    refresh_token = security.create_refresh_token(
        uid='1',
        jti=str(uuid.uuid4())
    )
    set_secure_cookie(
        response, request, config.JWT_REFRESH_COOKIE_NAME, refresh_token, 
        max_age=7*24*60*60
    )
    
    delete_secure_cookie(response, request, "auth_pending")
    return response