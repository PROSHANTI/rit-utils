from fastapi import Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from .login import get_auth_dependency, setup_2fa_session
from .cookie_utils import set_secure_cookie, delete_secure_cookie, get_cookie_settings
from .two_factor import (
    two_factor_handler,
    show_two_factor_page,
    generate_qr_code,
    get_totp_uri,
    get_user_secret
)

templates = Jinja2Templates(directory="templates")
dependencies = [get_auth_dependency()]


def setup_2fa_routes(app):
    """Настройка всех маршрутов связанных с 2FA"""
    
    @app.get("/2fa", tags=['2FA'], summary='Страница двухфакторной аутентификации')
    def two_factor_page(request: Request):
        return show_two_factor_page(request)

    @app.post("/2fa", tags=['2FA'], summary='Проверка кода 2FA')
    def two_factor_verify(request: Request, token: str = Form(...)):
        return two_factor_handler(request, token)

    @app.get("/setup-session", tags=['2FA'], summary='Настройка сессии после 2FA')
    def setup_session(request: Request):
        return setup_2fa_session(request)

    @app.get("/setup-2fa", 
             dependencies=dependencies,
             tags=['2FA'], 
             summary='Страница настройки 2FA')
    def setup_2fa_page(request: Request):
        username = "admin"
        user_secret = get_user_secret(username)
        uri = get_totp_uri(username) 
        qr_code = generate_qr_code(uri)
        
        return templates.TemplateResponse(
            "setup_2fa.html",
            {
                "request": request,
                "qr_code": qr_code,
                "manual_code": user_secret
            }
        )

    @app.get("/configure-2fa", 
             tags=['2FA'], 
             summary='Страница настройки 2FA (доступна после входа)')
    def configure_2fa_page(request: Request):
        if not request.cookies.get("auth_pending"):
            return RedirectResponse(url="/", status_code=303)
        
        username = "admin"
        user_secret = get_user_secret(username)
        uri = get_totp_uri(username)
        qr_code = generate_qr_code(uri)
        
        response = templates.TemplateResponse(
            "setup_2fa.html",
            {
                "request": request,
                "qr_code": qr_code,
                "manual_code": user_secret
            }
        )
        
        set_secure_cookie(response, request, "user_totp_secret", user_secret, max_age=300)
        
        set_secure_cookie(response, request, "2fa_configured", "true")
        
        return response
