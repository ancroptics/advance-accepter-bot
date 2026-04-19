import logging
import asyncio
import re
import ssl
from urllib.parse import unquote
import asyncpg
import config

logger = logging.getLogger(__name__)

def _get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def _parse_dsn(dsn):
    # Regex-based parser to avoid Python 3.12 urlparse breakage
    # on DATABASE_URLs with special characters (brackets, dots) in credentials
    m = re.match(
        r'postgres(?:ql)?://([^:@]*):([^@]*)@([^.:/\[\]]+|\[[^\]]+\]):?(\d+)?/([^? ]*)',
        dsn
    )
    if m:
        return {
            'user': unquote(m.group(1)),
            'password': unquote(m.group(2)),
            'host': m.group(3).strip('[]'),
            'port': int(m.group(4)) if m.group(4) else 5432,
            'database': m.group(5) or 'postgres',
        }
    # Fallback: try urlparse (works on Python <3.12 or simple URLs)
    from urllib.parse import urlparse
    parsed = urlparse(dsn)
    return {
        'user': unquote(parsed.username or ''),
        'password': unquote(parsed.password or ''),
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 5432,
        'database': (parsed.path or '/postgres').lstrip('/') or 'postgres',
    }
