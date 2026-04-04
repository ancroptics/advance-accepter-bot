import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from services.watermark_service import get_watermark

logger = logging.getLogger(__name__)

WAITING_MESSAGE = 1


async def start_welcome_edit(update, context, chat_id):
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel or channel['owner_id'] != user_id:
        await query.answer('Unauthorized', show_alert=True)
        return
    context.user_data['editing_welcome_for'] = chat_id
    current = channel.get('welcome_message', 'Welcome to {channel_name}!')
    text = (
        f'\U0001f4ac EDIT WELCOME DM\nChannel: {channel["chat_title"]}\n\n'
        f'Current message:\n{current}\n\n'
        f'Available variables:\n'
        '{first_name} - User\'s first name\n'
        '{last_name} - User\'s last name\n'
        '{username} - User\'s @username\n'
        '{user_id} - User\'s ID\n'
        '{channel_name} - Channel title\n'
        '{channel_username} - @channel\n'
        '{member_count} - Member count\n'
        '{referral_link} - Referral link\n'
        '{coins} - Coin balance\n'
        '{date} - Today\'s date\n\n'
        'Send your new welcome message now.\n'
        'You can also send a photo/video with caption.\n'
        'Type /cancel to cancel.'
    )
    await query.edit_message_text(text)
    return WAITING_MESSAGE


async def receive_welcome_message(update, context):
    chat_id = context.user_data.get('editing_welcome_for')
    if not chat_id:
        await update.message.reply_text('No channel selected. Use /dashboard.')
        return ConversationHandler.END
    db = context.application.bot_data.get('db')
    msg = update.message
    if msg.text:
        await db.update_channel_setting(chat_id, 'welcome_message', msg.text)
        await db.update_channel_setting(chat_id, 'welcome_media_type', None)
        await db.update_channel_setting(chat_id, 'welcome_media_file_id', None)
    elif msg.photo:
        caption = msg.caption or ''
        await db.update_channel_setting(chat_id, 'welcome_message', caption)
        await db.update_channel_setting(chat_id, 'welcome_media_type', 'photo')
        await db.update_channel_setting(chat_id, 'welcome_media_file_id', msg.photo[-1].file_id)
    elif msg.video:
        caption = msg.caption or ''
        await db.update_channel_setting(chat_id, 'welcome_message', caption)
        await db.update_channel_setting(chat_id, 'welcome_media_type', 'video')
        await db.update_channel_setting(chat_id, 'welcome_media_file_id', msg.video.file_id)
    elif msg.animation:
        caption = msg.caption or ''
        await db.update_channel_setting(chat_id, 'welcome_message', caption)
        await db.update_channel_setting(chat_id, 'welcome_media_type', 'animation')
        await db.update_channel_setting(chat_id, 'welcome_media_file_id', msg.animation.file_id)
    elif msg.document:
        caption = msg.caption or ''
        await db.update_channel_setting(chat_id, 'welcome_message', caption)
        await db.update_channel_setting(chat_id, 'welcome_media_type', 'document')
        await db.update_channel_setting(chat_id, 'welcome_media_file_id', msg.document.file_id)
    else:
        await msg.reply_text('Unsupported format. Send text, photo, video, or document.')
        return WAITING_MESSAGE
    await msg.reply_text(
        '\u2705 Welcome message updated!',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('\U0001f441 Preview', callback_data=f'preview_welcome:{chat_id}')],
            [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]
        ])
    )
    context.user_data.pop('editing_welcome_for', None)
    return ConversationHandler.END


async def preview_welcome(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    user = query.from_user
    import config
    text = channel.get('welcome_message', 'Welcome!')
    text = text.replace('{first_name}', user.first_name or 'there')
    text = text.replace('{last_name}', user.last_name or '')
    text = text.replace('{username}', f'@{user.username}' if user.username else 'there')
    text = text.replace('{user_id}', str(user.id))
    text = text.replace('{channel_name}', channel.get('chat_title', ''))
    text = text.replace('{channel_username}', f'@{channel.get("chat_username", "")}' if channel.get('chat_username') else '')
    text = text.replace('{member_count}', str(channel.get('member_count', 0)))
    text = text.replace('{referral_link}', f'https://t.me/{config.BOT_USERNAME}?start=ref_{user.id}')
    text = text.replace('{coins}', '0')
    from datetime import datetime
    text = text.replace('{date}', datetime.now().strftime('%Y-%m-%d'))
    watermark = await get_watermark(db, chat_id)
    text += watermark
    media_type = channel.get('welcome_media_type')
    media_fid = channel.get('welcome_media_file_id')
    try:
        if media_type == 'photo' and media_fid:
            await context.bot.send_photo(user.id, media_fid, caption=text, parse_mode='HTML')
        elif media_type == 'video' and media_fid:
            await context.bot.send_video(user.id, media_fid, caption=text, parse_mode='HTML')
        elif media_type == 'animation' and media_fid:
            await context.bot.send_animation(user.id, media_fid, caption=text, parse_mode='HTML')
        elif media_type == 'document' and media_fid:
            await context.bot.send_document(user.id, media_fid, caption=text, parse_mode='HTML')
        else:
            await context.bot.send_message(user.id, f'\U0001f441 PREVIEW:\n\n{text}', parse_mode='HTML')
    except Exception as e:
        await query.answer(f'Preview error: {str(e)[:50]}', show_alert=True)


async def cancel_welcome(update, context):
    context.user_data.pop('editing_welcome_for', None)
    await update.message.reply_text('Cancelled.')
    return ConversationHandler.END


welcome_dm_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(lambda u, c: start_welcome_edit(u, c, c.user_data.get('editing_welcome_for')), pattern='^edit_welcome:')],
    states={WAITING_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_welcome_message)]},
    fallbacks=[MessageHandler(filters.Regex('^/cancel$'), cancel_welcome)],
    per_user=True, per_chat=True,
)
