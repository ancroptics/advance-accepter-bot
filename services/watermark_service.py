import logging

logger = logging.getLogger(__name__)

EM_DASH_LINE = '\u2014' * 20


async def get_watermark(db, chat_id):
    """Get watermark text for a channel. Returns empty string if disabled."""
    try:
        channel = await db.get_channel(chat_id)
        if not channel or not channel.get('watermark_enabled', True):
            return ''
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
