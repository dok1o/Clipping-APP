"""Fernet roundtrip for platform credentials (CONTRACTS §9)."""
import pytest

from app.core.errors import AppError
from app.core.security import decrypt_str, encrypt_str, mask_secret
from app.infra.crypto import decrypt_str as reexported_decrypt
from app.infra.crypto import encrypt_str as reexported_encrypt


def test_roundtrip() -> None:
    secret = "tiktok-access-token-abc123"
    encrypted = encrypt_str(secret)
    assert encrypted != secret
    assert "tiktok" not in encrypted
    assert decrypt_str(encrypted) == secret


def test_infra_crypto_is_reexport() -> None:
    assert reexported_encrypt is encrypt_str
    assert reexported_decrypt is decrypt_str


def test_mask_secret_never_leaks() -> None:
    assert mask_secret("super-secret-value") == "***"
    assert mask_secret(None) == "***"
    assert mask_secret("") == "***"


def test_tampered_ciphertext_fails() -> None:
    encrypted = encrypt_str("value")
    with pytest.raises(AppError) as exc_info:
        decrypt_str(encrypted[:-4] + "AAAA")
    assert exc_info.value.code == "decrypt_failed"


def test_missing_key_raises(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.core.security import get_fernet

    monkeypatch.setattr(get_settings(), "encryption_key", "")
    with pytest.raises(AppError) as exc_info:
        get_fernet()
    assert exc_info.value.code == "encryption_key_missing"
