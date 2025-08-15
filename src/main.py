import datetime
import base64

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import src.config  # noqa: F401

from src.auth import (
    get_auth_dependency,
    login_handler,
    logout_handler,
    refresh_token_handler,
    jwt_decode_exception_handler,
    check_auth_status,
    setup_2fa_routes,
    JWTDecodeError
)
from src.utils.send_email.email_handler import send_email_handler
from src.utils.doctor_form.doctor_form_handler import doctor_form_handler
from src.utils.gen_cert.gen_cert_handler import gen_cert_handler


date_now = datetime.datetime.now().strftime("%d.%m.%y")
dependencies = [get_auth_dependency()]

# FastAPI app
app = FastAPI(docs_url=None, redoc_url=None)
setup_2fa_routes(app)
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

@app.post("/refresh", 
          tags=['Авторизация'], 
          summary='Обновить токен доступа'
          )
def refresh_token(request: Request):
    return refresh_token_handler(request)


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
         summary='Страница генерации подарочного сертификата'
         )
def gen_rit_cert_page(request: Request):
    encoded_status = request.cookies.get("gen_cert_status")
    status = None
    if encoded_status:
        try:
            status = base64.b64decode(encoded_status.encode('ascii')).decode('utf-8')
        except Exception as e: 
            status = f"Ошибка декодирования статуса, {e}"
    
    response = templates.TemplateResponse(
        "gen_rit_cert.html", {"request": request, "status": status}
        )
    if encoded_status:
        response.delete_cookie("gen_cert_status")
    return response

@app.post("/gen_rit_cert",
         dependencies=dependencies,
         tags=['Генерация сертификата'],
         summary='Сгенерировать подарочный сертификат'
         )
def gen_rit_cert_endpoint(
    request: Request,
    name: str | None = Form(None),
    price: str | None = Form(None)
):
    return gen_cert_handler(
        request=request,
        name=name,
        price=price
    )

@app.get("/doctor_form",
         dependencies=dependencies,
         tags=['Генерация карточек'],
         summary='Страница генерации карточек клиентов'
         )
def doctor_form_page(request: Request):
    encoded_status = request.cookies.get("doctor_form_status")
    status = None
    if encoded_status:
        try:
            status = base64.b64decode(encoded_status.encode('ascii')).decode('utf-8')
        except Exception as e: 
            status = f"Ошибка декодирования статуса, {e}"
    
    response = templates.TemplateResponse(
        "doctor_form.html", {"request": request, "status": status}
        )
    if encoded_status:
        response.delete_cookie("doctor_form_status")
    return response

@app.post("/doctor_form",
         dependencies=dependencies,
         tags=['Генерация карточек'],
         summary='Сгенерировать карточки клиентов'
         )
def doctor_form_endpoint(
    request: Request,
    doctor_1: str | None = Form(None),
    doctor_2: str | None = Form(None), 
    doctor_3: str | None = Form(None),
    doctor_4: str | None = Form(None),
    patient_1: str | None = Form(None),
    patient_2: str | None = Form(None),
    patient_3: str | None = Form(None),
    patient_4: str | None = Form(None),
    date: str | None = Form(None)
):
    return doctor_form_handler(
        request=request,
        doctor_1=doctor_1,
        doctor_2=doctor_2,
        doctor_3=doctor_3,
        doctor_4=doctor_4,
        patient_1=patient_1,
        patient_2=patient_2,
        patient_3=patient_3,
        patient_4=patient_4,
        date=date
    )


if __name__ == "__main__":
    uvicorn.run("src.main:app", reload=True, host="0.0.0.0", port=8000)

