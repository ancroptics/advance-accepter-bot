import hashlib
import random
import string
from datetime import datetime


def generate_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def format_number(n):
    if n >= 1_000_000:
        return f'{n/1_000_000:.1f}M'
    if n >= 1_000:
        return f'{n/1_000:.1f}K'
    return str(n)


def truncate(text, max_len=4096):
    if not text:
        return ''
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def format_datetime(dt):
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M UTC')
    return str(dt)
