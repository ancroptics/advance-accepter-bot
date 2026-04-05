import logging

logger = logging.getLogger(__name__)

EM_DASH_LINE = '\u2014' * 20

async def get_watermark(db, chat_id):
    """Get watermark text for a channel.
    FIX 5: Uses global watermark message set by superadmin for free plan users.
    Returns empty string if disabled."""
    try:
        # Check global watermark setting
        global_enabled = await db.get_platform_setting('global_watermark_enabled', 'true')
        if global_enabled.lower() != 'true':
            return ''

        channel = await db.get_channel(chat_id)
        if not channel:
            return ''

        # Check if owner is on a paid plan (exempt from watermark)
        owner_id = channel.get('owner_id')
        if owner_id:
            owner = await db.get_owner(owner_id)
            if owner and owner.get('tier', 'free').lower() in ('premium', 'business'):
                return ''

        # Get custom watermark message from superadmin, or use default
        custom_message = await db.get_platform_setting('global_watermark_message', '')

        if custom_message:
            # Replace variables
            name = channel.get('chat_title', '')
            custom_message = custom_message.replace('{channel_name}', name)
            custom_message = custom_message.replace('{bot_name}', 'Growth Engine')
            return f"\n\n{EM_DASH_LINE}\n{custom_message}"

        # Default watermark: channel name
        name = channel.get('chat_title', '')
        if name:
            return f"\n\n{EM_DASH_LINE}\n\U0001f4e2 {name}"
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
