from database.models import get_cross_promo_channel
from database.connection import DatabasePool
import logging
import random

logger = logging.getLogger(__name__)


async def get_promo_for_channel(db: DatabasePool, owner_id: int):
    try:
        channels = await get_cross_promo_channel(db, owner_id)
        if not channels:
            return None
        promo = random.choice(channels)
        return {
            'channel_id': promo['channel_id'],
            'channel_name': promo['channel_name'],
            'description': promo.get('promo_text', ''),
        }
    except Exception as e:
        logger.error(f'Cross promo error: {e}')
        return None


async def format_promo_message(promo: dict) -> str:
    if not promo:
        return ''
    name = promo.get('channel_name', 'Partner Channel')
    desc = promo.get('description', 'Check out our partner!')
    cid = promo.get('channel_id', '')
    return f"\n\n📢 *{name}*\n{desc}\n👉 [Join Now](https://t.me/{cid})"
