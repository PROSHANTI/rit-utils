"""Утилиты для работы с secure cookies для HTTPS"""

from fastapi import Request
from fastapi.responses import Response


def get_cookie_settings(request: Request) -> dict:
    """
    Возвращает настройки cookie для HTTPS (secure cookies)
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        dict: Настройки для cookie (secure, samesite, httponly)
    """
    # Приложение работает только на HTTPS в продакшене
    return {
        "secure": True,      # Всегда secure для HTTPS
        "samesite": "lax",   # Более мягкие ограничения для лучшей совместимости
        "httponly": True     # Защита от XSS
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
