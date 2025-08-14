"""Утилиты для работы с cookie с автоматической адаптацией к HTTP/HTTPS"""

from fastapi import Request
from fastapi.responses import Response


def get_cookie_settings(request: Request) -> dict:
    """
    Возвращает настройки cookie в зависимости от протокола (HTTP/HTTPS)
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        dict: Настройки для cookie (secure, samesite)
    """
    # Проверяем протокол
    is_secure = request.url.scheme == "https"
    
    # Также проверяем заголовки от reverse proxy (nginx)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    if forwarded_proto == "https":
        is_secure = True
    
    return {
        "secure": is_secure,
        "samesite": "strict" if is_secure else "lax",
        "httponly": True
    }


def set_secure_cookie(
    response: Response, 
    request: Request, 
    key: str, 
    value: str, 
    max_age: int = None
) -> None:
    """
    Устанавливает cookie с автоматическими настройками безопасности
    
    Args:
        response: FastAPI Response объект
        request: FastAPI Request объект  
        key: Имя cookie
        value: Значение cookie
        max_age: Время жизни cookie в секундах (опционально)
    """
    cookie_settings = get_cookie_settings(request)
    
    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        **cookie_settings
    )


def delete_secure_cookie(response: Response, request: Request, key: str) -> None:
    """
    Удаляет cookie с корректными настройками безопасности
    
    Args:
        response: FastAPI Response объект
        request: FastAPI Request объект
        key: Имя cookie для удаления
    """
    cookie_settings = get_cookie_settings(request)
    
    response.delete_cookie(
        key, 
        secure=cookie_settings["secure"], 
        samesite=cookie_settings["samesite"]
    )
