from pydantic import BaseModel


class UserLoginSchema(BaseModel):
    username: str
    password: str
    
    
class SendEmailSchema(BaseModel):
    cashless_pay: str
    card_pay: str
    cash_pay: str
    qr_pay: str