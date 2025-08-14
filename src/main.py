import os
import datetime
import base64

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv


from src.auth import (
    get_auth_dependency,
    login_handler,
    logout_handler,
    refresh_token_handler,
    jwt_decode_exception_handler,
    check_auth_status,
    setup_2fa_session,
    two_factor_handler,
    show_two_factor_page,
    generate_qr_code,
    get_totp_uri,
    get_user_secret,
    JWTDecodeError
)
from src.utils.email_handler import send_email_handler


load_dotenv()


date_now = datetime.datetime.now().strftime("%d.%m.%y")
dependencies = [get_auth_dependency()]

# FastAPI app
app = FastAPI()
app.mount("/static", StaticFiles(directory="templates"), name="static")
templates = Jinja2Templates(directory="templates")
app.add_exception_handler(JWTDecodeError, jwt_decode_exception_handler)


@app.post("/login",
          summary='Авторизация',
          tags=['Авторизация']
          )
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    return login_handler(request, username, password)
    
@app.post("/logout",
          dependencies=dependencies,
          summary='Выйти из системы',
          tags=['Выход из системы']
          )
def logout(request: Request):
    return logout_handler(request)

@app.post("/refresh", tags=['Авторизация'], summary='Обновить токен доступа')
def refresh_token(request: Request):
    return refresh_token_handler(request)

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
    
    username = os.getenv('USERNAME') or "admin"
    
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
    
    response.set_cookie(
        key="user_totp_secret",
        value=user_secret,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=300  # 5 минут
    )
    
    response.set_cookie(
        key="2fa_configured",
        value="true",
        httponly=True,
        secure=True,
        samesite="strict"
        
    )
    
    return response

@app.get("/", 
         tags=['Главная страница'], 
         summary='Отображает домашнюю страницу'
         )
def root(request: Request):
    return check_auth_status(request)

@app.get("/home", 
         dependencies=dependencies, 
         tags=['Домашняя страница'],
         summary='Отобразить домашнюю страницу'
         )
def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/send_email",
         dependencies=dependencies,
         tags=['Отправка отчета'],
         summary='Страница отправки отчета'
         )
def send_email(request: Request):
    encoded_status = request.cookies.get("email_status")
    status = None
    if encoded_status:
        try:
            status = base64.b64decode(encoded_status.encode('ascii')).decode('utf-8')
        except Exception as e: 
            status = f"Ошибка декодирования статуса, {e}"
    
    response = templates.TemplateResponse(
        "send_email.html", {"request": request, "status": status}
        )
    if encoded_status:
        response.delete_cookie("email_status")
    return response

@app.post("/send_email",
         dependencies=dependencies,
         tags=['Отправка отчета'],
         summary='Отправить отчет на почту'
         )
def send_email_endpoint(
    request: Request,
    qr_pay: str | None = Form(None),
    cashless_pay: str | None = Form(None),
    card_pay: str | None = Form(None),
    cash_pay: str | None = Form(None),
    attachment: UploadFile = File(...)
):
    return send_email_handler(
        request=request,
        qr_pay=qr_pay,
        cashless_pay=cashless_pay,
        card_pay=card_pay,
        cash_pay=cash_pay,
        attachment=attachment
    )


@app.get("/gen_rit_cert",
         dependencies=dependencies,
         tags=['Генерация сертификата'],
         summary='Сгенерировать подарочный сертификат'
         )
def gen_rit_cert(request: Request):
        return templates.TemplateResponse(
        "gen_rit_cert.html", {"request": request}
        )

@app.get("/doctor_form",
         dependencies=dependencies,
         tags=['Генерация карточек'],
         summary='Сгенерировать карточки клиентов'
         )
def doctor_form(request: Request):
    return templates.TemplateResponse("doctor_form.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)

