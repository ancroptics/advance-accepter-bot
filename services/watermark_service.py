import logging

logger = logging.getLogger(__name__)

EM_DASH_LINE = '\u2014' * 20

async def get_watermark(db, chat_id):
    """Get watermark text for a channel.
    Supports per-channel watermark @username set by channel owner.
    Also supports global watermark for free-plan users."""
    try:
        channel = await db.get_channel(chat_id)
        if not channel:
            return ''

        # Check per-channel watermark first
        if channel.get('watermark_enabled') and channel.get('watermark_username'):
            username = channel['watermark_username']
            return f"\n\n{EM_DASH_LINE}\n@{username}"

        # Check global watermark setting (superadmin)
        try:
            global_enabled = await db.get_platform_setting('global_watermark_enabled', 'false')
            if global_enabled.lower() != 'true':
                return ''
        except Exception:
            return ''

        # Check if owner is on a paid plan (exempt from global watermark)
        owner_id = channel.get('owner_id')
        if owner_id:
            owner = await db.get_owner(owner_id)
            if owner and owner.get('tier', 'free').lower() in ('premium', 'business'):
                return ''

        # Get custom watermark message from superadmin, or use default
        try:
            custom_message = await db.get_platform_setting('global_watermark_message', '')
        except Exception:
            custom_message = ''

        if custom_message:
            name = channel.get('chat_title', '')
            custom_message = custom_message.replace('{channel_name}', name)
            custom_message = custom_message.replace('{bot_name}', 'Growth Engine')
            return f"\n\n{EM_DASH_LINE}\n{custom_message}"

        return ''
    except Exception as e:
        logger.warning(f'Watermark error: {e}')
        return ''

async def add_watermark(text, channel_name=None, owner_name=None):
    if not text:
        return text
    watermark_parts = []
    if channel_name:
        watermark_parts.append(f'\U0001f4e2 {channel_name}')
    if owner_name:
        watermark_parts.append(f'by {owner_name}')
    if not watermark_parts:
        return text
    watermark = ' | '.join(watermark_parts)
    return f"{text}\n\n{EM_DASH_LINE}\n{watermark}"

async def add_media_caption_watermark(caption, channel_name=None):
    if not caption:
        caption = ''
    if channel_name:
        return f"{caption}\n\n\U0001f4e2 {channel_name}"
    return caption
