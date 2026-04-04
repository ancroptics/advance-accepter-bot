import logging
import random

logger = logging.getLogger(__name__)


async def get_cross_promo_text(db, chat_id, owner_id):
    try:
        channel = await db.get_channel(chat_id)
        if not channel or not channel.get('cross_promo_enabled'):
            return None
        category = channel.get('cross_promo_category')
        if not category:
            return None
        candidates = await db.get_cross_promo_candidates(category, chat_id, owner_id)
        if not candidates:
            return None
        chosen = random.choice(candidates)
        promo_text = chosen.get('cross_promo_text', '')
        promo_username = chosen.get('chat_username', '')
        if not promo_username:
            return None
        await db.log_cross_promo(chat_id, chosen['chat_id'])
        return f'\n\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4e2 {promo_text}\n\U0001f449 @{promo_username}'
    except Exception as e:
        logger.error(f'Cross-promo error: {e}')
        return None
