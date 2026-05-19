import base64
import hashlib
import os

from cryptography.fernet import Fernet

import config


def _derive_key():
    raw = (
        os.getenv('SESSION_ENCRYPTION_KEY', '')
        or config.CLONE_ENCRYPTION_KEY
        or f'{config.BOT_TOKEN}:{config.DATABASE_URL}'
    )
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())


def encrypt_text(value):
    if value is None:
        return None
    return Fernet(_derive_key()).encrypt(value.encode()).decode()


def decrypt_text(value):
    if not value:
        return None
    return Fernet(_derive_key()).decrypt(value.encode()).decode()
