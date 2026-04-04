import logging
import config

logger = logging.getLogger(__name__)


async def get_watermark(db, chat_id, clone_id=None):
    try:
        channel = await db.get_channel(chat_id)
        if not channel:
            return ''
        owner_id = channel.get('owner_id')
        owner = await db.get_owner(owner_id)
        if not owner:
            return f'\n\n\u26a1 Powered by @{config.BOT_USERNAME} \u2014 Free channel growth tool'

        tier = owner.get('tier', 'free')
        watermark_enabled = channel.get('watermark_enabled', True)

        if tier == 'free':
            return f'\n\n\u26a1 Powered by @{config.BOT_USERNAME} \u2014 Free channel growth tool'
        elif tier in ('premium', 'business'):
            if watermark_enabled:
                return f'\n\n\u26a1 Powered by @{config.BOT_USERNAME}'
            return ''
        return ''
    except Exception as e:
        logger.error(f'Watermark error: {e}')
        return ''
