import os
import datetime
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from fastapi import Form, UploadFile, File, Request
from fastapi.responses import RedirectResponse
from src.utils.send_email.email_templates import get_email_template


SEND_FROM = os.getenv('SEND_FROM')
EMAIL_PASS = os.getenv('EMAIL_PASS')
ADDR_TO = os.getenv('ADDR_TO')
BCC_TO = os.getenv('BCC_TO')
    
def send_email_handler(
    request: Request,
    qr_pay: str | None = Form(None),
    cashless_pay: str | None = Form(None),
    card_pay: str | None = Form(None),
    cash_pay: str | None = Form(None),
    attachment: UploadFile = File(...)
):
    
    time_now = datetime.datetime.now().strftime("%H:%M")
    date_now = datetime.datetime.now().strftime("%d.%m.%y")
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

        server = smtplib.SMTP_SSL('smtp.yandex.ru', 465)
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
