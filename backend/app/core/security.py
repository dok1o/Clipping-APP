"""Fernet encryption of platform credentials.

Single implementation point (master spec §9); app/infra/crypto.py re-exports it.
The key comes from ENCRYPTION_KEY env; plaintext credentials never appear in logs.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.errors import AppError


def get_fernet(encryption_key: str | None = None) -> Fernet:
    from app.core.config import get_settings

    key = encryption_key or get_settings().encryption_key
    if not key:
        raise AppError(500, "encryption_key_missing", "ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise AppError(500, "encryption_key_invalid", f"ENCRYPTION_KEY is invalid: {exc}") from exc


def encrypt_str(value: str) -> str:
    return get_fernet().encrypt(value.encode()).decode()


def decrypt_str(value: str) -> str:
    try:
        return get_fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise AppError(500, "decrypt_failed", "Failed to decrypt credentials") from exc


def mask_secret(value: str | None) -> str:
    """Credentials are always shown masked in logs/API."""
    return "***"
