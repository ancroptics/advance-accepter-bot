import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

DRIP_PRESETS = {
    'slow': {'quantity': 10, 'interval': 60, 'label': '🐢 Slow (10/60min)'},
    'medium': {'quantity': 25, 'interval': 30, 'label': '🐕 Medium (25/30min)'},
    'fast': {'quantity': 50, 'interval': 15, 'label': '🇡 Fast (50/15min)'},
    'instant': {'quantity': 9999, 'interval': 0, 'label': '⚡ Instant (All at once)'},
}


async def start_batch_approve(query, db, chat_id, context):
    """Show batch approve menu with drip speed options."""
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text('Channel not found.')
        return

    pending = await db.get_pending_requests(chat_id)
    count = len(pending)

    if count == 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Sync Pending', callback_data=f'sync_pending:{chat_id}')],
            [InlineKeyboardButton('🔙 Back', callback_data=f'settings:{chat_id}')]
        ])
        await query.edit_message_text(
            f'📋 No pending requests for {channel.get("title", "Unknown")}\n\n'
            'Try syncing pending requests first.',
            reply_markup=keyboard
        )
        return

    buttons = []
    for key, preset in DRIP_PRESETS.items():
        buttons.append([InlineKeyboardButton(
            preset['label'],
            callback_data=f'drip_speed:{key}:{chat_id}'
        )])
    buttons.append([InlineKeyboardButton('🔙 Back', callback_data=f'settings:{chat_id}')])

    await query.edit_message_text(
        f'📋 Batch Approve\n\n'
        f'Channel: {channel.get("title", "Unknown")}\n'
        f'Pending: {count} requests\n\n'
        'Select approval speed:',
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def handle_batch_progress(query, db, chat_id, context):
    """Show current batch operation progress."""
    batch_status = context.bot_data.get(f'batch_{chat_id}', {})

    if not batch_status:
        await query.edit_message_text(
            'No active batch operation.',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton('🔙 Back', callback_data=f'settings:{chat_id}')
            ]])
        )
        return

    total = batch_status.get('total', 0)
    processed = batch_status.get('processed', 0)
    approved = batch_status.get('approved', 0)
    failed = batch_status.get('failed', 0)
    status = batch_status.get('status', 'unknown')

    progress = (processed / total * 100) if total > 0 else 0
    bar_filled = int(progress / 10)
    bar = '█' * bar_filled + '░' * (10 - bar_filled)

    text = (
        f'📊 Batch Progress\n\n'
        f'[{bar}] {progress:.1f}%\n\n'
        f'Total: {total}\n'
        f'Processed: {processed}\n'
        f'✅ Approved: {approved}\n'
        f'❌ Failed: {failed}\n'
        f'Status: {status}'
    )

    buttons = []
    if status == 'running':
        buttons.append([InlineKeyboardButton('🔄 Refresh', callback_data=f'batch_progress:{chat_id}')])
        buttons.append([InlineKeyboardButton('⏹ Stop', callback_data=f'batch_stop:{chat_id}')])
    else:
        buttons.append([InlineKeyboardButton('🔙 Back', callback_data=f'settings:{chat_id}')])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def execute_batch_approve(query, db, chat_id, context, speed_key):
    """Execute batch approval with selected drip speed."""
    preset = DRIP_PRESETS.get(speed_key)
    if not preset:
        return

    pending = await db.get_pending_requests(chat_id)
    total = len(pending)

    if total == 0:
        return

    batch_status = {
        'total': total, 'processed': 0, 'approved': 0,
        'failed': 0, 'status': 'running'
    }
    context.bot_data[f'batch_{chat_id}'] = batch_status

    quantity = preset['quantity']
    interval = preset['interval']

    for i in range(0, total, quantity):
        if context.bot_data.get(f'batch_{chat_id}', {}).get('status') == 'stopped':
            break

        batch = pending[i:i + quantity]

        for req in batch:
            try:
                user_id = req.get('user_id')
                if user_id:
                    await context.bot.approve_chat_join_request(
                        chat_id=chat_id, user_id=user_id
                    )
                    await db.update_request_status(chat_id, user_id, 'approved')
                    batch_status['approved'] += 1
            except Exception as e:
                logger.error(f"Failed to approve {user_id} for {chat_id}: {e}")
                batch_status['failed'] += 1

            batch_status['processed'] += 1

        if interval > 0 and i + quantity < total:
            await asyncio.sleep(interval * 60)

    batch_status['status'] = 'completed'

    try:
        await query.edit_message_text(
            f'✅ Batch Complete\n\n'
            f'Total: {total}\n'
            f'Approved: {batch_status["approved"]}\n'
            f'Failed: {batch_status["failed"]}',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton('🔙 Back', callback_data=f'settings:{chat_id}')
            ]])
        )
    except Exception:
        pass


async def sync_pending_requests(db, chat_id, context):
    """Sync pending join requests from Telegram API to database."""
    try:
        pending_count = 0
        # Use getChatJoinRequests to fetch pending requests
        pending_users = []

        try:
            # Fetch pending join requests from Telegram
            result = await context.bot.get_chat_join_requests(chat_id)
            if result:
                for request in result:
                    user_id = request.from_user.id
                    user_name = request.from_user.full_name
                    username = request.from_user.username
                    request_date = request.date

                    await db.add_pending_request(
                        chat_id=chat_id,
                        user_id=user_id,
                        user_name=user_name,
                        username=username,
                        request_date=request_date
                    )
                    pending_count += 1
        except Exception as e:
            logger.warning(f"Could not fetch join requests via API for {chat_id}: {e}")
            # Fall back to database count
            existing = await db.get_pending_requests(chat_id)
            pending_count = len(existing)

        return pending_count
    except Exception as e:
        logger.error(f"Error syncing pending requests for {chat_id}: {e}")
        return 0


async def decline_all_pending(db, chat_id, context):
    """Decline all pending join requests for a channel."""
    pending = await db.get_pending_requests(chat_id)
    total = len(pending)
    declined = 0
    failed = 0

    for req in pending:
        try:
            user_id = req.get('user_id')
            if user_id:
                await context.bot.decline_chat_join_request(
                    chat_id=chat_id, user_id=user_id
                )
                await db.update_request_status(chat_id, user_id, 'declined')
                declined += 1
        except Exception as e:
            logger.error(f"Failed to decline {user_id} for {chat_id}: {e}")
            failed += 1

    return {'total': total, 'declined': declined, 'failed': failed}
