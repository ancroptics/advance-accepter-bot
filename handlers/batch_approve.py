import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.models import db, TIER_LIMITS

logger = logging.getLogger(__name__)

# Batch sizes for processing
BATCH_SIZES = [10, 50, 100, 500, 1000]


async def batch_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/batch - Show batch approval panel for all channels with pending requests."""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)

    if not user:
        await update.message.reply_text("\u26a0\ufe0f Please /start first.")
        return

    if user.get('is_banned'):
        await update.message.reply_text("\u26a0\ufe0f You are banned.")
        return

    channels = await db.get_user_channels(user_id)
    if not channels:
        await update.message.reply_text("No channels found. Use /start to add one.")
        return

    # Filter channels with pending requests
    pending_channels = [c for c in channels if c.get('pending_requests', 0) > 0]

    if not pending_channels:
        await update.message.reply_text("\u2728 No pending requests in any channel!")
        return

    text = "<b>\ud83d\udccb Batch Approval Panel</b>\n\n"
    keyboard = []

    for ch in pending_channels:
        title = ch.get('chat_title', 'Unknown')
        pending = ch.get('pending_requests', 0)
        chat_id = ch['chat_id']
        text += f"\u2022 <b>{title}</b> \u2014 {pending} pending\n"
        keyboard.append([
            InlineKeyboardButton(f"\u2705 {title}", callback_data=f"batch_select:{chat_id}")
        ])

    keyboard.append([InlineKeyboardButton("\u26a0\ufe0f Approve ALL Channels", callback_data="batch_all")])

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def batch_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle batch approval buttons."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith('batch_select:'):
        chat_id = int(data.split(':')[1])
        channel = await db.get_channel(chat_id)
        if not channel:
            await query.edit_message_text("Channel not found.")
            return

        title = channel.get('chat_title', 'Unknown')
        pending = channel.get('pending_requests', 0)

        keyboard = []
        for size in BATCH_SIZES:
            if size <= pending:
                keyboard.append([
                    InlineKeyboardButton(
                        f"\u2705 Approve {size}",
                        callback_data=f"batch_approve:{chat_id}:{size}"
                    ),
                    InlineKeyboardButton(
                        f"\u274c Decline {size}",
                        callback_data=f"batch_decline:{chat_id}:{size}"
                    )
                ])

        keyboard.append([
            InlineKeyboardButton(
                f"\u2705 Approve ALL ({pending})",
                callback_data=f"batch_approve:{chat_id}:-1"
            ),
            InlineKeyboardButton(
                f"\u274c Decline ALL ({pending})",
                callback_data=f"batch_decline:{chat_id}:-1"
            )
        ])
        keyboard.append([InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="batch_back")])

        await query.edit_message_text(
            f"<b>\ud83d\udccb {title}</b>\n\n"
            f"Pending requests: <b>{pending}</b>\n\n"
            f"Select batch size:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif data == 'batch_all':
        await _execute_batch_all(query, context, user_id)

    elif data.startswith('batch_approve:'):
        parts = data.split(':')
        chat_id = int(parts[1])
        count = int(parts[2])
        await _execute_batch_approve(query, context, user_id, chat_id, count)

    elif data.startswith('batch_decline:'):
        parts = data.split(':')
        chat_id = int(parts[1])
        count = int(parts[2])
        await _execute_batch_decline(query, context, user_id, chat_id, count)

    elif data == 'batch_back':
        await batch_approve_command(update, context)


async def _execute_batch_all(query, context, user_id):
    """Approve all pending requests across all channels."""
    channels = await db.get_user_channels(user_id)
    pending_channels = [c for c in channels if c.get('pending_requests', 0) > 0]

    if not pending_channels:
        await query.edit_message_text("\u2728 No pending requests!")
        return

    total_approved = 0
    total_failed = 0
    results = []

    status_msg = await query.edit_message_text(
        "<b>\u26a1 Batch approving all channels...</b>\nPlease wait...",
        parse_mode='HTML'
    )

    for ch in pending_channels:
        chat_id = ch['chat_id']
        title = ch.get('chat_title', 'Unknown')
        pending = await db.get_pending_requests(chat_id, limit=10000)

        approved = 0
        failed = 0
        for req in pending:
            try:
                await context.bot.approve_chat_join_request(
                    chat_id=chat_id, user_id=req['user_id'])
                await db.approve_request(chat_id, req['user_id'])
                approved += 1
            except Exception as e:
                logger.warning(f"Failed to approve {req['user_id']}: {e}")
                failed += 1

            if approved % 30 == 0:
                await asyncio.sleep(1)

        total_approved += approved
        total_failed += failed
        results.append(f"\u2022 {title}: {approved} approved, {failed} failed")

    if total_approved > 0:
        await db.increment_approvals(user_id, total_approved)

    result_text = (
        f"<b>\u2714 Batch Approve Complete!</b>\n\n"
        + "\n".join(results) + "\n\n"
        f"Total: <b>{total_approved}</b> approved"
    )
    if total_failed:
        result_text += f", <b>{total_failed}</b> failed"

    await status_msg.edit_text(text=result_text, parse_mode='HTML')


async def _execute_batch_approve(query, context, user_id, chat_id, count):
    """Execute batch approve for a specific channel."""
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text("Channel not found.")
        return

    user = await db.get_user(user_id)
    tier = user.get('tier', 'free') if user else 'free'
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    monthly_limit = limits.get('monthly_approvals', 500)
    used = user.get('monthly_approvals', 0) if user else 0
    remaining = monthly_limit - used

    fetch_limit = count if count > 0 else 10000
    pending = await db.get_pending_requests(chat_id, limit=fetch_limit)

    if not pending:
        await query.edit_message_text("\u2728 No pending requests!")
        return

    # Limit by remaining quota
    if monthly_limit != -1:
        pending = pending[:remaining]

    title = channel.get('chat_title', 'Unknown')
    total = len(pending)

    status_msg = await query.edit_message_text(
        f"<b>\u26a1 Approving {total} requests in {title}...</b>\nPlease wait...",
        parse_mode='HTML'
    )

    approved = 0
    failed = 0
    limit = monthly_limit

    for req in pending:
        try:
            await context.bot.approve_chat_join_request(
                chat_id=chat_id, user_id=req['user_id'])
            await db.approve_request(chat_id, req['user_id'])
            approved += 1
        except Exception as e:
            logger.warning(f"Failed to approve {req['user_id']}: {e}")
            failed += 1

        # Rate limit
        if approved % 30 == 0:
            await asyncio.sleep(1)

    if approved > 0:
        await db.increment_approvals(user_id, approved)

    result_text = (
        f"<b>\u2714 Batch Approve Complete!</b>\n\n"
        f"\ud83d\udcec {title}\n"
        f"\u2705 Approved: <b>{approved}</b>\n"
    )
    if failed:
        result_text += f"\u274c Failed: <b>{failed}</b>\n"
    if remaining <= 0 and limit != -1:
        result_text += f"\n\u26a0Limit reached ({limit}/month)"

    await status_msg.edit_text(text=result_text, parse_mode='HTML')


async def _execute_batch_decline(query, context, user_id, chat_id, count):
    """Execute batch decline for a channel."""
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text("Channel not found.")
        return

    fetch_limit = count if count > 0 else 10000
    pending = await db.get_pending_requests(chat_id, limit=fetch_limit)

    if not pending:
        await query.edit_message_text("\u2728 No pending requests!")
        return

    title = channel.get('chat_title', 'Unknown')
    total = len(pending)

    status_msg = await query.edit_message_text(
        f"<b>\u26b3\ufe0f Declining {total} requests in {title}...</b>\nPlease wait...",
        parse_mode='HTML'
    )

    declined = 0
    failed = 0

    for req in pending:
        try:
            await context.bot.decline_chat_join_request(
                chat_id=chat_id, user_id=req['user_id'])
            await db.decline_request(chat_id, req['user_id'])
            declined += 1
        except Exception as e:
            logger.warning(f"Failed to decline {req['user_id']}: {e}")
            failed += 1

        # Rate limit
        if declined % 30 == 0:
            await asyncio.sleep(1)

    result_text = (
        f"<b>\u2714 Batch Decline Complete!</b>\n\n"
        f"\ud83c\udf2c {title}\n"
        f"\u274c Declined: <b>{declined}</b>\n"
    )
    if failed:
        result_text += f"\u26a0 Failed: <b>{failed}</b>\n"

    await status_msg.edit_text(text=result_text, parse_mode='HTML')
