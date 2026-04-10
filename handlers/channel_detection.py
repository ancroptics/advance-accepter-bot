import logging
import asyncio
from telegram import Update, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)

def extract_status_change(chat_member_update: ChatMemberUpdated):
    status_change = chat_member_update.difference().get('status')
    if status_change is None:
        return None, None
    old_status, new_status = status_change
    return old_status, new_status

async def channel_detection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = extract_status_change(update.my_chat_member)
        if result is None:
            return
        old_status, new_status = result
        if old_status is None:
            return
        chat = update.my_chat_member.chat
        from_user = update.my_chat_member.from_user
        db = context.application.bot_data.get('db')
        if not db:
            return

        # Bot was ADDED to a channel/group as admin
        if new_status in ('administrator', 'member') and old_status in ('left', 'kicked', None):
            logger.info(f'Bot added to {chat.type} {chat.title} (ID: {chat.id}) by user {from_user.id}')
            # Create/update channel owner
            await db.upsert_owner(
                user_id=from_user.id,
                username=from_user.username,
                first_name=from_user.first_name,
                last_name=from_user.last_name,
            )
            # Create managed channel
            await db.upsert_channel(
                chat_id=chat.id,
                owner_id=from_user.id,
                chat_title=chat.title,
                chat_username=chat.username,
                chat_type=chat.type,
            )
            # Try to get member count
            try:
                count = await context.bot.get_chat_member_count(chat.id)
                await db.update_channel_setting(chat.id, 'member_count', count)
            except Exception:
                pass

            # Scan for existing pending requests BEFORE notifying owner
            # so the pending count is accurate in the notification
            scan_result = await process_existing_pending_requests(context, chat.id, from_user.id)

            # Now get the accurate pending count AFTER scanning
            pending = await db.get_pending_count(chat.id)
            # Also sync the pending_requests column on the channel row
            await db.update_channel_setting(chat.id, 'pending_requests', pending)

            # Notify owner with accurate count
            try:
                text = (
                    f'\u2705 Channel Connected!\n'
                    f'\U0001f4e2 {chat.title}\n\n'
                    f"I\'m now managing join requests for this channel.\n\n"
                    f'\U0001f4cb Pending Requests: {pending}\n'
                    f'\u2699\ufe0f Auto-Approve: ON\n'
                )
                if scan_result and scan_result.get('saved', 0) > 0:
                    text += (
                        f'\n\U0001f50d Found {scan_result["saved"]} existing pending request(s)!\n'
                        f'\u2705 Auto-approved: {scan_result.get("approved", 0)}\n'
                    )
                buttons = [
                    [InlineKeyboardButton('\u2699\ufe0f Configure Channel', callback_data=f'manage_channel:{chat.id}')],
                    [InlineKeyboardButton('\U0001f4ca View Analytics', callback_data=f'analytics:{chat.id}')],
                    [InlineKeyboardButton('\U0001f4e2 Manage All Channels', callback_data='dashboard')],
                ]
                await context.bot.send_message(from_user.id, text, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                logger.warning(f'Could not DM owner {from_user.id}: {e}')
            # Log event
            await db.log_event('channel_connected', owner_id=from_user.id, channel_id=chat.id)

        # Bot was REMOVED from a channel/group
        elif new_status in ('left', 'kicked') and old_status in ('administrator', 'member'):
            logger.info(f'Bot removed from {chat.title} (ID: {chat.id})')
            await db.update_channel_setting(chat.id, 'is_active', False)
            await db.update_channel_setting(chat.id, 'bot_is_admin', False)
            # Try to notify owner
            channel = await db.get_channel(chat.id)
            if channel:
                try:
                    await context.bot.send_message(
                        channel['owner_id'],
                        f'\u26a0\ufe0f Bot was removed from {chat.title}'
                    )
                except Exception:
                    pass
            await db.log_event('channel_disconnected', channel_id=chat.id)
    except Exception as e:
        logger.exception(f'Error in channel_detection_handler: {e}')


async def get_telegram_pending_count(bot_token, chat_id):
    """Get pending_join_request_count via raw Telegram API.

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


async def process_existing_pending_requests(context, chat_id, owner_id):
    """Process join requests that were already pending before bot became admin.

    Returns dict with 'saved' and 'approved' counts.
    Runs synchronously (awaited) so the caller can use accurate counts afterward.
    """
    db = context.application.bot_data.get('db')
    if not db:
        return {'saved': 0, 'approved': 0}

    result = {'saved': 0, 'approved': 0}

    try:
        # Verify bot is admin first
        try:
            await context.bot.get_chat_administrators(chat_id)
            logger.info(f'Bot is admin in {chat_id}, scanning for existing pending requests')
        except Exception as e:
            logger.warning(f'Cannot verify admin status for {chat_id}: {e}')
            # Still try to fetch - bot might have limited permissions

        # Get real pending count from Telegram raw API
        tg_count = await get_telegram_pending_count(context.bot.token, chat_id)
        db_count = await db.get_pending_count(chat_id)

        if tg_count == 0:
            logger.info(f'No existing pending requests found in {chat_id} (Telegram reports 0)')
            # Sync count to channel
            await db.update_channel_setting(chat_id, 'pending_requests', db_count)
            await db.update_channel_setting(chat_id, 'telegram_pending', 0)
            return result

        # Store the real TG count so the UI can show it
        await db.update_channel_setting(chat_id, 'telegram_pending', tg_count)

        logger.info(f'Telegram reports {tg_count} pending requests in {chat_id} (DB has {db_count})')

        # NOTE: Telegram Bot API has NO endpoint to enumerate individual pending requests.
        # We can only know the count. Individual requests are captured via chat_join_request updates.
        # So we can't "import" old ones we missed - we can only report the discrepancy.

        # We still proceed with DB-tracked requests for auto-approve
        pending_users_raw = await db.get_pending_requests(chat_id, limit=500)
        pending_users = [{'user': {'id': r.get('user_id'), 'username': r.get('username'),
                          'first_name': r.get('first_name'), 'last_name': r.get('last_name'),
                          'language_code': r.get('user_language')}} for r in pending_users_raw]

        if not pending_users:
            logger.info(f'No DB-tracked pending requests to process in {chat_id} (TG has {tg_count})')
            return result

        logger.info(f'Processing {len(pending_users)} DB-tracked pending requests in {chat_id}')

        # Get channel settings for approve logic
        channel = await db.get_channel(chat_id)
        auto_approve = channel.get('auto_approve', True) if channel else True
        approve_mode = channel.get('approve_mode', 'instant') if channel else 'instant'

        for req in pending_users:
            user = req.get('user', {})
            user_id = user.get('id')
            if not user_id:
                continue

            # Save the join request to DB
            try:
                await db.save_join_request(
                    user_id=user_id,
                    chat_id=chat_id,
                    username=user.get('username'),
                    first_name=user.get('first_name'),
                    user_language=user.get('language_code'),
                )
                result['saved'] += 1
            except Exception as e:
                logger.debug(f'Error saving existing request {user_id}: {e}')
                continue

            # Also upsert the end user so they show up in analytics/broadcast
            try:
                await db.upsert_end_user(
                    user_id=user_id,
                    username=user.get('username'),
                    first_name=user.get('first_name'),
                    last_name=user.get('last_name'),
                    language_code=user.get('language_code'),
                    source='existing_pending',
                    source_channel=chat_id,
                )
            except Exception as e:
                logger.debug(f'Error upserting end user {user_id}: {e}')

            # Auto-approve if configured for instant mode
            if auto_approve and approve_mode == 'instant':
                try:
                    await context.bot.approve_chat_join_request(chat_id, user_id)
                    await db.update_join_request_after_approve(
                        user_id=user_id, chat_id=chat_id,
                        dm_sent=False, processed_by='auto_existing'
                    )
                    result['approved'] += 1
                except Exception as e:
                    logger.debug(f'Could not approve existing request {user_id}: {e}')

                # Small delay to avoid Telegram rate limits
                if result['approved'] % 30 == 0:
                    await asyncio.sleep(1)

        # Update the pending_requests counter on the channel to be accurate
        final_pending = await db.get_pending_count(chat_id)
        await db.update_channel_setting(chat_id, 'pending_requests', final_pending)

        logger.info(f'Processed existing requests in {chat_id}: saved={result["saved"]}, approved={result["approved"]}, remaining_pending={final_pending}')

        return result

    except Exception as e:
        logger.error(f'Error in process_existing_pending_requests: {e}')
        return result
