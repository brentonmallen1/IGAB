from cryptography.fernet import Fernet

from igab.config import settings


def _fernet() -> Fernet:
    key = settings.SIMPLEFIN_ENCRYPTION_KEY
    if not key:
        raise ValueError("SIMPLEFIN_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
