import logging
import asyncio
from telegram import Update, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)


async def get_telegram_pending_count(bot_token, chat_id):
    """Get pending_join_request_count via raw Telegram Bot API.

    python-telegram-bot v21.x does NOT map this field to Chat/ChatFullInfo,
    so getattr(chat_info, 'pending_join_request_count', 0) always returns 0.
    We must call the raw HTTP API and read the JSON directly.
    """
    import aiohttp
    url = f'https://api.telegram.org/bot{bot_token}/getChat'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={'chat_id': chat_id},
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if data.get('ok'):
                    count = data['result'].get('pending_join_request_count', 0) or 0
                    logger.info(f'Raw API pending_join_request_count for {chat_id}: {count}')
                    return count
                else:
                    logger.warning(f'getChat failed for {chat_id}: {data}')
                    return 0
    except Exception as e:
        logger.error(f'Error getting telegram pending count for {chat_id}: {e}')
        return 0


async def channel_detection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot being added/removed from channels."""
    my_member = update.my_chat_member
    if not my_member:
        return

    chat = my_member.chat
    old_status = my_member.old_chat_member.status if my_member.old_chat_member else 'left'
    new_status = my_member.new_chat_member.status if my_member.new_chat_member else 'left'

    db = context.application.bot_data.get('db')
    if not db:
        logger.error('Database not available in channel_detection_handler')
        return

    # Bot was added as admin to a channel
    if new_status in ('administrator', 'creator') and old_status not in ('administrator', 'creator'):
        await _handle_bot_added(update, context, chat, db)
    # Bot was removed from a channel
    elif new_status in ('left', 'kicked') and old_status in ('administrator', 'creator', 'member'):
        await _handle_bot_removed(update, context, chat, db)
    # Bot's permissions were updated
    elif new_status == 'administrator' and old_status == 'administrator':
        await _handle_permissions_updated(update, context, chat, db)

async def _handle_bot_added(update, context, chat, db):
    """Handle bot being added as admin to a channel."""
    user = update.my_chat_member.from_user
    logger.info(f'Bot added to channel: {chat.title} ({chat.id}) by user {user.id}')

    try:
        # Check permissions
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        can_invite = getattr(bot_member, 'can_invite_users', False)

        # Save channel to database
        await db.save_channel(
            chat_id=chat.id,
            chat_title=chat.title or 'Unknown',
            chat_type=chat.type,
            owner_id=user.id,
            username=chat.username
        )

        # Get channel info
        try:
            chat_info = await context.bot.get_chat(chat.id)
            member_count = await context.bot.get_chat_member_count(chat.id)
            await db.update_channel_setting(chat.id, 'member_count', member_count)
        except Exception as e:
            logger.warning(f'Could not get chat info: {e}')
            member_count = 0

        # Fetch existing pending join requests using Telethon (MTProto)
        pending_count = 0
        telethon = context.application.bot_data.get('telethon')
        if telethon and telethon.available:
            try:
                logger.info(f'Fetching existing pending requests for {chat.id} via Telethon...')
                requests = await telethon.get_pending_join_requests(chat.id, limit=50000)
                if requests:
                    pending_count = len(requests)
                    logger.info(f'Found {pending_count} pending join requests for {chat.title}')
                    # Save all pending requests to database
                    saved = 0
                    for req in requests:
                        try:
                            await db.save_join_request(
                                user_id=req['user_id'],
                                chat_id=chat.id,
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
                                source='telethon_detection',
                                source_channel=chat.id,
                            )
                        except Exception:
                            pass
                    logger.info(f'Saved {saved} pending requests for {chat.title}')
                else:
                    logger.info(f'No pending requests found for {chat.title} via Telethon')
            except Exception as e:
                logger.warning(f'Telethon fetch pending failed for {chat.id}: {e}')
        else:
            # Fallback: use raw API to get count + check DB
            pending_count = await get_telegram_pending_count(context.bot.token, chat.id)
            db_count = await db.get_pending_count(chat.id)
            pending_count = max(pending_count, db_count)
            logger.info(f'Telethon not available, using API count: {pending_count}')

        await db.update_channel_setting(chat.id, 'pending_requests', pending_count)

        # Send notification to the user who added the bot
        status_parts = []
        status_parts.append(f'\u2705 Bot added to <b>{chat.title}</b>')
        status_parts.append(f'\n\U0001f4ca Members: {member_count}')
        status_parts.append(f'\u23f3 Pending requests: <b>{pending_count}</b>')

        if can_invite:
            status_parts.append('\n\u2705 Permission: Can manage join requests')
        else:
            status_parts.append('\n\u26a0\ufe0f Permission: Cannot invite users - please grant "Invite Users" permission')

        if pending_count > 0:
            status_parts.append(f'\n\n\U0001f389 Found <b>{pending_count}</b> existing pending join requests!')
            status_parts.append('Use /batch to approve or decline them.')
        elif not telethon or not telethon.available:
            status_parts.append('\n\n\u26a0\ufe0f Telethon (MTProto) is not configured.')
            status_parts.append('Without it, the bot <b>cannot detect</b> pre-existing pending requests.')
            status_parts.append('Use /scan after Telethon is configured to fetch them.')

        buttons = []
        buttons.append([InlineKeyboardButton('\U0001f4ca Dashboard', callback_data='dashboard')])
        buttons.append([InlineKeyboardButton(f'\u2699\ufe0f Manage {chat.title}', callback_data=f'manage_channel:{chat.id}')])
        if pending_count > 0:
            buttons.append([InlineKeyboardButton(f'\u2705 Batch Approve ({pending_count})', callback_data=f'batch_approve:{chat.id}')])

        try:
            await context.bot.send_message(
                chat_id=user.id,
                text='\n'.join(status_parts),
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.warning(f'Could not notify user {user.id}: {e}')

    except Exception as e:
        logger.exception(f'Error handling bot added to {chat.id}: {e}')

async def _handle_bot_removed(update, context, chat, db):
    """Handle bot being removed from a channel."""
    user = update.my_chat_member.from_user
    logger.info(f'Bot removed from channel: {chat.title} ({chat.id}) by user {user.id}')

    try:
        await db.update_channel_setting(chat.id, 'is_active', False)

        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f'\u274c Bot was removed from <b>{chat.title}</b>.\n\n'
                     'The channel has been deactivated. Add the bot back as admin to reactivate.',
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\U0001f4ca Dashboard', callback_data='dashboard')]
                ])
            )
        except Exception as e:
            logger.warning(f'Could not notify user {user.id}: {e}')

    except Exception as e:
        logger.exception(f'Error handling bot removed from {chat.id}: {e}')

async def _handle_permissions_updated(update, context, chat, db):
    """Handle bot permissions being updated in a channel."""
    user = update.my_chat_member.from_user
    logger.info(f'Bot permissions updated in: {chat.title} ({chat.id})')

    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        can_invite = getattr(bot_member, 'can_invite_users', False)

        if can_invite:
            msg = f'\u2705 Bot now has invite permission in <b>{chat.title}</b>.\nJoin requests can be managed.'
        else:
            msg = f'\u26a0\ufe0f Bot lost invite permission in <b>{chat.title}</b>.\nPlease grant "Invite Users" permission.'

        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=msg,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f'\u2699\ufe0f Manage {chat.title}', callback_data=f'manage_channel:{chat.id}')]
                ])
            )
        except Exception:
            pass

    except Exception as e:
        logger.exception(f'Error handling permissions update for {chat.id}: {e}')

async def process_existing_pending_requests(context, chat_id, db, action='approve', limit=None):
    """Process existing pending join requests for a channel.
    Uses Telethon to fetch real pending requests from Telegram.
    """
    result = {'processed': 0, 'success': 0, 'failed': 0, 'total_pending': 0}

    try:
        # First, sync pending requests from Telethon if available
        telethon = context.application.bot_data.get('telethon')
        if telethon and telethon.available:
            try:
                requests = await telethon.get_pending_join_requests(chat_id, limit=50000)
                if requests:
                    for req in requests:
                        try:
                            await db.save_join_request(
                                user_id=req['user_id'],
                                chat_id=chat_id,
                                username=req.get('username'),
                                first_name=req.get('first_name'),
                            )
                        except Exception:
                            pass
                    logger.info(f'Synced {len(requests)} pending requests from Telethon for {chat_id}')
            except Exception as e:
                logger.warning(f'Telethon sync failed for {chat_id}: {e}')

        # Get pending requests from database
        pending = await db.get_pending_requests(chat_id, limit=limit)
        result['total_pending'] = await db.get_pending_count(chat_id)

        if not pending:
            return result

        for req in pending:
            user_id = req['user_id']
            result['processed'] += 1
            try:
                if action == 'approve':
                    await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
                else:
                    await context.bot.decline_chat_join_request(chat_id=chat_id, user_id=user_id)

                await db.update_join_request_status(user_id, chat_id, 'approved' if action == 'approve' else 'declined', 'batch')
                result['success'] += 1
            except Exception as e:
                error_msg = str(e).lower()
                if 'user_already_participant' in error_msg or 'hide_requester_missing' in error_msg:
                    await db.update_join_request_status(user_id, chat_id, 'approved' if 'participant' in error_msg else 'expired', 'batch')
                    result['success'] += 1
                else:
                    result['failed'] += 1
                    logger.debug(f'Failed to {action} {user_id} in {chat_id}: {e}')

            # Rate limit protection
            if result['processed'] % 30 == 0:
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(0.05)

        final_pending = await db.get_pending_count(chat_id)
        await db.update_channel_setting(chat_id, 'pending_requests', final_pending)
        logger.info(f'Batch {action}: processed={result["processed"]}, success={result["success"]}, failed={result["failed"]}, remaining_pending={final_pending}')

        return result

    except Exception as e:
        logger.error(f'Error in process_existing_pending_requests: {e}')
        return result
