import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


async def show_pending_menu(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    pending = channel.get('pending_requests', 0)
    text = (f'\U0001f4cb PENDING REQUESTS\n'
            f'Channel: {channel["chat_title"]}\n'
            f'Pending: {pending:,}\n\n')
    buttons = [
        [InlineKeyboardButton('\u2705 Approve 50', callback_data=f'batch_approve:{chat_id}:50'),
         InlineKeyboardButton('\u2705 Approve 100', callback_data=f'batch_approve:{chat_id}:100')],
        [InlineKeyboardButton('\u2705 Approve 500', callback_data=f'batch_approve:{chat_id}:500'),
         InlineKeyboardButton('\u2705 Approve 1000', callback_data=f'batch_approve:{chat_id}:1000')],
        [InlineKeyboardButton('\u2705 Approve ALL \u26a0\ufe0f', callback_data=f'batch_approve:{chat_id}:all')],
        [InlineKeyboardButton('\U0001f550 Start Drip', callback_data=f'start_drip:{chat_id}')],
        [InlineKeyboardButton('\u274c Decline All', callback_data=f'decline_all:{chat_id}')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def execute_batch_approve(update, context, chat_id, count):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    if count == -1:
        pending = await db.get_pending_requests(chat_id, limit=99999)
    else:
        pending = await db.get_pending_requests(chat_id, limit=count)
    if not pending:
        await query.edit_message_text('No pending requests.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]]))
        return
    total = len(pending)
    sent = 0
    failed = 0
    dm_sent = 0
    dm_failed = 0
    channel = await db.get_channel(chat_id)
    msg = await query.edit_message_text(f'\u23f3 Approving... 0/{total}')
    for i, req in enumerate(pending):
        try:
            # Try DM first
            if channel and channel.get('welcome_dm_enabled'):
                try:
                    welcome_text = channel.get('welcome_message', 'Welcome!')
                    welcome_text = welcome_text.replace('{first_name}', req.get('first_name', 'there'))
                    welcome_text = welcome_text.replace('{channel_name}', channel.get('chat_title', ''))
                    await context.bot.send_message(req['user_id'], welcome_text)
                    dm_sent += 1
                except Exception:
                    dm_failed += 1
            # Approve
            await context.bot.approve_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_status(req['user_id'], chat_id, 'approved', 'batch')
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f'Batch approve error: {e}')
        if (i + 1) % 25 == 0:
            try:
                await msg.edit_text(f'\u23f3 Approving... {i+1}/{total}\n\u2705 Sent: {sent} | \u274c Failed: {failed} | DMs: {dm_sent}')
            except Exception:
                pass
        await asyncio.sleep(0.5)
    await db.update_channel_stats_after_batch(chat_id, sent, dm_sent, dm_failed)
    await msg.edit_text(
        f'\u2705 Batch Complete!\n\nApproved: {sent}\nFailed: {failed}\nDMs Sent: {dm_sent}\nDMs Failed: {dm_failed}',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]])
    )


async def decline_all_pending(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    pending = await db.get_pending_requests(chat_id, limit=99999)
    count = 0
    for req in pending:
        try:
            await context.bot.decline_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_status(req['user_id'], chat_id, 'declined', 'batch')
            count += 1
        except Exception:
            pass
        await asyncio.sleep(0.3)
    await query.edit_message_text(f'\u274c Declined {count} requests.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]]))

batch_approve_conv_handler = None
