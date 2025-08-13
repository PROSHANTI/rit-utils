import os
from email_templates import get_email_template
import datetime
import smtplib
import base64

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from authx import AuthX, AuthXConfig
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

load_dotenv()

# Авторизация
config = AuthXConfig()
config.JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
config.JWT_ACCESS_COOKIE_NAME = "JWT_ACCESS_TOKEN_COOKIE"
config.JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=30)
config.JWT_TOKEN_LOCATION = ["cookies"]
config.JWT_COOKIE_CSRF_PROTECT = False
security: AuthX = AuthX(config=config)

# Переменные
LOGIN = os.getenv('LOGIN')
PASSWORD = os.getenv('PASSWORD')
SEND_FROM = os.getenv('SEND_FROM')
EMAIL_PASS = os.getenv('EMAIL_PASS')
ADDR_TO = os.getenv('ADDR_TO')
BCC_TO = os.getenv('BCC_TO ')
EMAIL_TEMPLATE = os.getenv('EMAIL_TEMPLATE')
time_now = datetime.datetime.now().strftime("%H:%M")
date_now = datetime.datetime.now().strftime("%d.%m.%y")
dependencies=[Depends(security.access_token_required)]

# Настройки FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend/templates"), name="static")

# Шаблонизатор
templates = Jinja2Templates(directory="frontend/templates")


@app.post("/login", summary='Авторизация', tags=['Авторизация'])
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == LOGIN and password == PASSWORD:
        response = RedirectResponse(url="/home", status_code=303)
        
        access_token = security.create_access_token(uid='1')
        response.set_cookie(
            key=config.JWT_ACCESS_COOKIE_NAME,
            value=access_token,
            httponly=True,
            samesite="lax"
        )
        
        refresh_token = security.create_refresh_token(uid='1')
        response.set_cookie(
            key=config.JWT_REFRESH_COOKIE_NAME,
            value=refresh_token,
            httponly=True,
            samesite="lax",
            max_age=30*24*60*60
        )
        
        return response
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неверный логин или пароль"},
        status_code=401
    )
    
@app.post("/logout",
          dependencies=dependencies,
          summary='Выйти из системы',
          tags=['Выход из системы']
          )
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(
        key=config.JWT_ACCESS_COOKIE_NAME,
        path="/",
        domain=None,
        secure=False,
        httponly=True,
        samesite="lax"
    )
    return response

@app.post("/refresh", tags=['Авторизация'], summary='Обновить токен доступа')
def refresh_token(request: Request):
    refresh_token = request.cookies.get(config.JWT_REFRESH_COOKIE_NAME)
    
    if not refresh_token:
        return RedirectResponse(url="/", status_code=303)
    
    try:        
        payload = security._decode_token(refresh_token)
        new_access_token = security.create_access_token(uid=payload.sub)
        response = RedirectResponse(url="/home", status_code=303)
        response.set_cookie(
            key=config.JWT_ACCESS_COOKIE_NAME,
            value=new_access_token,
            httponly=True,
            samesite="lax"
        )
        return response
    except Exception as e:

        print(f"Refresh token error: {str(e)}")
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(config.JWT_ACCESS_COOKIE_NAME)
        response.delete_cookie(config.JWT_REFRESH_COOKIE_NAME)
        return response



@app.get("/", 
         tags=['Главная страница'], 
         summary='Отображает домашнюю страницу'
         )
def root(request: Request):
    if request.cookies.get(config.JWT_ACCESS_COOKIE_NAME):
        return RedirectResponse(url="/home", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})

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
def send_email_post(
    request: Request,
    qr_pay: str | None = Form(None),
    cashless_pay: str | None = Form(None),
    card_pay: str | None = Form(None),
    cash_pay: str | None = Form(None),
    attachment: UploadFile = File(...)
):
    template = get_email_template()
    cashless_payment = str(cashless_pay)
    card_pay = str(card_pay)
    cash_pay = str(cash_pay)
    qr_pay = str(qr_pay)
    body_cashless = ''
    body_card = ''
    body_cash = ''
    body_qr = ''
    
    if cashless_payment:
        body_cashless = f'Безналичная оплата: {cashless_payment}\n'
    if card_pay:
        body_card = f'На карту: {card_pay}\n'
    if cash_pay:
        body_cash = f'Наличные: {cash_pay}\n'
    if qr_pay:
        body_qr = f'QR-код: {qr_pay}\n'
    try:
        msg = MIMEMultipart()
        msg['From'] = SEND_FROM or ""
        msg['To'] = ADDR_TO or ""
        msg['Subject'] = date_now
        msg['Bcc'] = BCC_TO or ""
        
        body = template.format(
            body_cashless=body_cashless,
            body_card=body_card,
            body_qr=body_qr,
            body_cash=body_cash
        )
        msg.attach(MIMEText(body, 'plain'))
        file_data = attachment.file.read()
        part = MIMEApplication(file_data, Name=date_now + '.xlsx')
        part['Content-Disposition'] = f'attachment; filename="{date_now}.xlsx"'
        msg.attach(part)

        server = smtplib.SMTP_SSL('smtp.yandex.ru', 465)  # SMTP
        server.login(SEND_FROM or "", EMAIL_PASS or "")
        server.send_message(msg)
        server.quit()

    except smtplib.SMTPAuthenticationError:
        status = "Ошибка отправки: неверные учетные данные"
    except Exception as e:
        status = f"Ошибка отправки: {str(e)}"
    else:
        status = f"Письмо успешно отправлено в {time_now}"
    response = RedirectResponse(url="/send_email", status_code=303)
    encoded_status = base64.b64encode(status.encode('utf-8')).decode('ascii')
    response.set_cookie("email_status", encoded_status, max_age=10)
    return response


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

