import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scan - Scan all channels for existing pending join requests using Telethon MTProto."""
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    telethon = context.application.bot_data.get('telethon')

    if not db:
        await update.message.reply_text("Bot not ready.")
        return

    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text("Please /start first.")
        return

    if not telethon or not telethon.available:
        await update.message.reply_text(
            "Telethon (MTProto) is not configured.\n\n"
            "The Telegram Bot API <b>cannot list</b> pending join requests. "
            "To fetch old/existing pending requests, the bot needs Telethon credentials.\n\n"
            "Ask the bot admin to set these env vars:\n"
            "<code>TELETHON_API_ID</code>\n"
            "<code>TELETHON_API_HASH</code>\n"
            "<code>TELETHON_SESSION_STRING</code>\n\n"
            "Get API ID/Hash from: https://my.telegram.org/apps\n"
            "Generate session with: <code>python generate_session.py</code>",
            parse_mode='HTML'
        )
        return

    channels = await db.get_user_channels(user_id)
    if not channels:
        await update.message.reply_text("No channels found. Add the bot as admin to a channel first.")
        return

    status_msg = await update.message.reply_text(
        f"Scanning {len(channels)} channel(s) for pending join requests via MTProto...\n"
        "This may take a while for large channels.",
        parse_mode='HTML'
    )

    total_found = 0
    total_saved = 0
    results = []

    for ch in channels:
        chat_id = ch['chat_id']
        title = ch.get('chat_title', 'Unknown')
        try:
            requests = await telethon.get_pending_join_requests(chat_id, limit=50000)
            if requests is None:
                results.append(f"- {title}: could not fetch")
                continue

            found = len(requests)
            total_found += found
            saved = 0

            for req in requests:
                try:
                    await db.save_join_request(
                        user_id=req['user_id'],
                        chat_id=chat_id,
                        username=req.get('username'),
                        first_name=req.get('first_name'),
                    )
                    saved += 1
                except Exception:
                    pass

                try:
                    await db.upsert_end_user(
                        user_id=req['user_id'],
                        username=req.get('username'),
                        first_name=req.get('first_name'),
                        source='telethon_scan',
                        source_channel=chat_id,
                    )
                except Exception:
                    pass

            total_saved += saved

            pending = await db.get_pending_count(chat_id)
            await db.update_channel_setting(chat_id, 'pending_requests', pending)

            results.append(f"- <b>{title}</b>: {found} found, {saved} new saved, {pending} total pending")
        except Exception as e:
            logger.warning(f'Scan error for {chat_id}: {e}')
            results.append(f"- {title}: error: {str(e)[:50]}")

    result_text = (
        f"<b>Scan Complete!</b>\n\n"
        + "\n".join(results) + "\n\n"
        f"<b>Total found:</b> {total_found}\n"
        f"<b>New saved:</b> {total_saved}\n\n"
        "Use /batch to approve/decline pending requests."
    )

    try:
        await status_msg.edit_text(result_text, parse_mode='HTML')
    except Exception:
        await update.message.reply_text(result_text, parse_mode='HTML')
