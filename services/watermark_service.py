import logging

logger = logging.getLogger(__name__)


async def add_watermark(text, channel_name=None, owner_name=None):
    if not text:
        return text
    watermark_parts = []
    if channel_name:
        watermark_parts.append(f'📢 {channel_name}')
    if owner_name:
        watermark_parts.append(f'by {owner_name}')
    if not watermark_parts:
        return text
    watermark = ' | '.join(watermark_parts)
    return f"{text}\n\n{'—' * 20}\n{watermark}"


async def add_media_caption_watermark(caption, channel_name=None):
    if not caption:
        caption = ''
    if channel_name:
        return f"{caption}\n\n📢 {channel_name}"
    return caption
