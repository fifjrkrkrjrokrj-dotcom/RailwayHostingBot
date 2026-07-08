import hashlib
import hmac
import json
import os
import re
import zipfile
from cryptography.fernet import Fernet
from bot.config.settings import settings


def generate_encryption_key() -> bytes:
    return Fernet.generate_key()


def get_cipher() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if len(key) < 32:
        key = hashlib.sha256(key.encode()).hexdigest()[:43] + "="
    return Fernet(base64_encode(key.encode()))


def base64_encode(data: bytes) -> bytes:
    import base64
    return base64.urlsafe_b64encode(data)


def encrypt_value(value: str) -> str:
    cipher = get_cipher()
    return cipher.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    cipher = get_cipher()
    return cipher.decrypt(encrypted.encode()).decode()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_railway_token(token: str) -> bool:
    pattern = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', re.I)
    return bool(pattern.match(token))


def scan_zip_for_threats(zip_path: str) -> list:
    threats = []
    dangerous_extensions = [".exe", ".dll", ".so", ".dylib", ".bat", ".bin", ".msi", ".vbs", ".ps1"]
    dangerous_files = ["__pycache__", ".git", "node_modules", "docker-compose.yml"]

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                name = info.filename.lower()
                ext = os.path.splitext(name)[1]
                if ext in dangerous_extensions:
                    threats.append(f"Dangerous extension detected: {info.filename}")
                for danger in dangerous_files:
                    if danger.lower() in name:
                        threats.append(f"Restricted file: {info.filename}")
                if info.file_size > 10 * 1024 * 1024:
                    threats.append(f"File too large: {info.filename} ({info.file_size} bytes)")
    except Exception as e:
        threats.append(f"ZIP scan error: {str(e)}")

    return threats


def is_rate_limited(user_id: int, cache) -> bool:
    key = f"ratelimit:{user_id}"
    current = cache.get(key)
    if current is None:
        cache.set(key, 1, ex=settings.RATE_LIMIT_WINDOW)
        return False
    if current >= settings.RATE_LIMIT:
        return True
    cache.incr(key)
    return False
