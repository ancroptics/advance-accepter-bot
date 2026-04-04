import logging
import random

logger = logging.getLogger(__name__)


async def get_promo_for_channel(db, chat_id):
    """Get a random cross-promo suggestion for a channel."""
    try:
        channel = await db.get_channel(chat_id)
        if not channel or not channel.get('cross_promo_enabled'):
            return None
        category = channel.get('cross_promo_category', 'general')
        all_channels = await db.get_all_channels(limit=50)
        candidates = [
            c for c in all_channels
            if c['chat_id'] != chat_id
            and c.get('cross_promo_enabled')
            and c.get('cross_promo_category', 'general') == category
        ]
        if not candidates:
            return None
        promo = random.choice(candidates)
        return {
            'channel_id': promo['chat_id'],
            'channel_name': promo.get('chat_title', 'Partner Channel'),
            'description': promo.get('cross_promo_text', 'Check out our partner!'),
            'username': promo.get('chat_username', ''),
        }
    except Exception as e:
        logger.error(f'Cross promo error: {e}')
        return None


async def get_cross_promo_text(db, chat_id, owner_id=None):
    """Get formatted cross-promo text to append to welcome messages."""
    try:
        promo = await get_promo_for_channel(db, chat_id)
        if not promo:
            return ''
        return await format_promo_message(promo)
    except Exception:
        return ''


async def format_promo_message(promo: dict) -> str:
    if not promo:
        return ''
    name = promo.get('channel_name', 'Partner Channel')
    desc = promo.get('description', 'Check out our partner!')
    username = promo.get('username', '')
    link = f'https://t.me/{username}' if username else ''
    return f"\n\n\U0001f4e2 *{name}*\n{desc}\n\U0001f449 [Join Now]({link})"
