import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

logger = logging.getLogger(__name__)

WAITING_CONTENT, WAITING_TARGET, WAITING_BUTTONS, CONFIRM = range(4)


async def start_broadcast(update, context):
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    owner = await db.get_owner(user_id)
    if not owner:
        msg = 'You need to add the bot to a channel first.'
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    context.user_data['broadcast'] = {}
    msg = '\U0001f4e2 BROADCAST\n\nSend me the content to broadcast.\nAccepted: text, photo, video, document, animation.\n\nType /cancel to cancel.'
    if update.callback_query:
        await update.callback_query.edit_message_text(msg)
    else:
        await update.message.reply_text(msg)
    return WAITING_CONTENT


async def receive_content(update, context):
    msg = update.message
    bc = context.user_data.get('broadcast', {})
    if msg.text:
        bc['content_type'] = 'text'
        bc['content'] = msg.text
    elif msg.photo:
        bc['content_type'] = 'photo'
        bc['media_file_id'] = msg.photo[-1].file_id
        bc['caption'] = msg.caption or ''
    elif msg.video:
        bc['content_type'] = 'video'
        bc['media_file_id'] = msg.video.file_id
        bc['caption'] = msg.caption or ''
    elif msg.document:
        bc['content_type'] = 'document'
        bc['media_file_id'] = msg.document.file_id
        bc['caption'] = msg.caption or ''
    elif msg.animation:
        bc['content_type'] = 'animation'
        bc['media_file_id'] = msg.animation.file_id
        bc['caption'] = msg.caption or ''
    else:
        await msg.reply_text('Unsupported content type. Please send text, photo, video, or document.')
        return WAITING_CONTENT

    context.user_data['broadcast'] = bc
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    channels = await db.get_owner_channels(user_id)
    all_count = await db.get_owner_user_count(user_id)
    buttons = [[InlineKeyboardButton(f'\U0001f465 All My Users ({all_count})', callback_data='bc_target:all')]]
    for ch in (channels or []):
        ch_count = await db.get_channel_user_count(ch['chat_id'])
        buttons.append([InlineKeyboardButton(f"\U0001f4e2 {ch['chat_title']} ({ch_count})", callback_data=f"bc_target:ch:{ch['chat_id']}")])
    buttons.append([InlineKeyboardButton('\u274c Cancel', callback_data='bc_cancel')])
    await msg.reply_text('Select target audience:', reply_markup=InlineKeyboardMarkup(buttons))
    return WAITING_TARGET


async def select_target(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    bc = context.user_data.get('broadcast', {})
    if data == 'bc_cancel':
        await query.edit_message_text('Broadcast cancelled.')
        return ConversationHandler.END
    if data == 'bc_target:all':
        bc['target_segment'] = 'all'
        bc['target_description'] = 'All users'
    elif data.startswith('bc_target:ch:'):
        chat_id = int(data.split(':')[2])
        bc['target_segment'] = f'channel:{chat_id}'
        bc['target_description'] = f'Channel {chat_id} users'
    context.user_data['broadcast'] = bc
    await query.edit_message_text(
        'Add inline buttons?\nFormat: Button Text - https://url.com (one per line)\n\nSend "skip" to skip.',
    )
    return WAITING_BUTTONS


async def receive_buttons(update, context):
    text = update.message.text.strip()
    bc = context.user_data.get('broadcast', {})
    if text.lower() != 'skip':
        buttons_json = []
        for line in text.split('\n'):
            if ' - ' in line:
                parts = line.split(' - ', 1)
                buttons_json.append({'text': parts[0].strip(), 'url': parts[1].strip()})
        bc['buttons_json'] = buttons_json
    context.user_data['broadcast'] = bc
    preview = f"\U0001f4e2 Broadcast Preview:\n\nType: {bc['content_type']}\nTarget: {bc.get('target_description', 'all')}\n"
    if bc['content_type'] == 'text':
        preview += f"Content: {bc['content'][:100]}..." if len(bc.get('content', '')) > 100 else f"Content: {bc.get('content', '')}"
    else:
        preview += f"Caption: {bc.get('caption', 'None')[:100]}"
    buttons = [
        [InlineKeyboardButton('\u2705 Send Now', callback_data='bc_confirm:now')],
        [InlineKeyboardButton('\u274c Cancel', callback_data='bc_cancel')],
    ]
    await update.message.reply_text(preview, reply_markup=InlineKeyboardMarkup(buttons))
    return CONFIRM


async def confirm_broadcast(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'bc_cancel':
        await query.edit_message_text('Broadcast cancelled.')
        return ConversationHandler.END

    user_id = query.from_user.id
    bc = context.user_data.get('broadcast', {})
    db = context.application.bot_data.get('db')
    broadcast_engine = context.application.bot_data.get('broadcast_engine')

    # Get target users
    if bc.get('target_segment') == 'all':
        users = await db.get_owner_users(user_id)
    elif bc.get('target_segment', '').startswith('channel:'):
        ch_id = int(bc['target_segment'].split(':')[1])
        users = await db.get_channel_users(ch_id)
    else:
        users = []

    total = len(users)
    if total == 0:
        await query.edit_message_text('No users to broadcast to.')
        return ConversationHandler.END

    # Create broadcast record
    broadcast_id = await db.create_broadcast(
        owner_id=user_id,
        content_type=bc.get('content_type', 'text'),
        content=bc.get('content'),
        media_file_id=bc.get('media_file_id'),
        caption=bc.get('caption'),
        buttons_json=bc.get('buttons_json'),
        target_segment=bc.get('target_segment', 'all'),
        total_targets=total,
    )

    msg = await query.edit_message_text(f'\U0001f4e4 Sending... 0/{total}')
    sent = 0
    failed = 0
    blocked = 0

    for i, user in enumerate(users):
        try:
            uid = user['user_id']
            if bc['content_type'] == 'text':
                buttons = None
                if bc.get('buttons_json'):
                    button_rows = [[InlineKeyboardButton(b['text'], url=b['url']) for b in bc['buttons_json']]]
                    buttons = InlineKeyboardMarkup(button_rows)
                await context.bot.send_message(uid, bc['content'], reply_markup=buttons)
            elif bc['content_type'] == 'photo':
                await context.bot.send_photo(uid, bc['media_file_id'], caption=bc.get('caption'))
            elif bc['content_type'] == 'video':
                await context.bot.send_video(uid, bc['media_file_id'], caption=bc.get('caption'))
            elif bc['content_type'] == 'document':
                await context.bot.send_document(uid, bc['media_file_id'], caption=bc.get('caption'))
            elif bc['content_type'] == 'animation':
                await context.bot.send_animation(uid, bc['media_file_id'], caption=bc.get('caption'))
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if 'forbidden' in err or 'blocked' in err or 'chat not found' in err:
                blocked += 1
                await db.mark_user_blocked(user['user_id'])
            else:
                failed += 1
        if (i + 1) % 25 == 0:
            try:
                pct = int((i + 1) / total * 100)
                await msg.edit_text(f'\U0001f4e4 Sending... {i+1}/{total} ({pct}%)\n\u2705 Sent: {sent} | \u274c Failed: {failed} | \U0001f6ab Blocked: {blocked}')
            except Exception:
                pass
        await asyncio.sleep(0.04)  # ~25/sec

    await db.update_broadcast_status(broadcast_id, 'completed', sent, failed, blocked)
    await msg.edit_text(
        f'\u2705 Broadcast Complete!\n\n'
        f'Total: {total}\n\u2705 Sent: {sent}\n\u274c Failed: {failed}\n\U0001f6ab Blocked: {blocked}',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]])
    )
    context.user_data.pop('broadcast', None)
    return ConversationHandler.END


async def cancel_broadcast(update, context):
    context.user_data.pop('broadcast', None)
    await update.message.reply_text('Broadcast cancelled.')
    return ConversationHandler.END


broadcast_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_broadcast, pattern='^broadcast$'),
        MessageHandler(filters.Regex('^/broadcast$'), start_broadcast),
    ],
    states={
        WAITING_CONTENT: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_content)],
        WAITING_TARGET: [CallbackQueryHandler(select_target, pattern='^bc_')],
        WAITING_BUTTONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_buttons)],
        CONFIRM: [CallbackQueryHandler(confirm_broadcast, pattern='^bc_')],
    },
    fallbacks=[MessageHandler(filters.Regex('^/cancel$'), cancel_broadcast)],
    per_user=True,
    per_chat=True,
)
