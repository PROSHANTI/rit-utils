#!/usr/bin/env python3
"""
Отладочный скрипт для проверки 2FA кодов
"""

import os
import hashlib
import base64
import pyotp
from datetime import datetime

# Загрузить TOTP_SECRET из .env
def load_env():
    env_vars = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
    except FileNotFoundError:
        print("❌ .env файл не найден")
        return None
    return env_vars.get('TOTP_SECRET')

def get_user_secret(username="admin"):
    """Генерирует секрет пользователя"""
    totp_secret = load_env()
    if not totp_secret:
        return None
    
    combined = f"{totp_secret}:{username}"
    hash_bytes = hashlib.sha256(combined.encode()).digest()
    secret = base64.b32encode(hash_bytes[:20]).decode()
    return secret

def main():
    print("🔐 2FA Debug Tool")
    print("=" * 40)
    
    # Получаем секрет
    secret = get_user_secret()
    if not secret:
        print("❌ Не удалось получить TOTP_SECRET")
        return
    
    print(f"📱 Секрет пользователя: {secret}")
    print(f"📱 Первые 8 символов: {secret[:8]}...")
    
    # Генерируем текущий код
    totp = pyotp.TOTP(secret)
    current_code = totp.now()
    
    print(f"⏰ Текущее время: {datetime.now()}")
    print(f"🔢 Текущий код сервера: {current_code}")
    
    # Генерируем QR код URI
    uri = totp.provisioning_uri(
        name="admin",
        issuer_name="RIT-UTILS"
    )
    print(f"🔗 QR код URI: {uri}")
    
    # Проверяем несколько кодов
    print("\n🧪 Тестирование кодов:")
    test_token = input("Введите код из приложения: ").strip()
    
    if test_token:
        # Проверяем с разными окнами
        for window in [0, 1, 2, 3]:
            result = totp.verify(test_token, valid_window=window)
            print(f"   Window {window}: {result}")
        
        # Показываем соседние коды
        import time
        current_time = int(time.time())
        print(f"\n⏰ Коды по времени:")
        for offset in [-2, -1, 0, 1, 2]:
            test_time = current_time + (offset * 30)
            code_at_time = totp.at(test_time)
            print(f"   {offset*30:+3}s: {code_at_time}")

if __name__ == "__main__":
    main()
