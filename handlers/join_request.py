import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from services.watermark_service import get_watermark
from services.cross_promo_service import get_cross_promo_text
from services.language_service import get_welcome_for_language

logger = logging.getLogger(__name__)

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """THE CORE HANDLER - must never crash"""
    try:
        join_request = update.chat_join_request
        user = join_request.from_user
        chat = join_request.chat
        chat_id = chat.id
        user_id = user.id

        db = context.application.bot_data.get('db')
        if not db:
            logger.error('Database not available in join_request_handler')
            try:
                await join_request.approve()
            except Exception:
                pass
            return

        # Step 1: Save the request
        try:
            await db.save_join_request(
                user_id=user_id,
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name,
                user_language=user.language_code,
            )
        except Exception as e:
            logger.error(f'Error saving join request: {e}')

        # Step 2: Save/update end user
        try:
            await db.upsert_end_user(
                user_id=user_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                source='join_request',
                source_channel=chat_id,
            )
        except Exception as e:
            logger.error(f'Error upserting end user: {e}')

        # Step 3: Check approval mode
        channel = await db.get_channel(chat_id)
        # Increment pending counter
        if channel:
            try:
                pending_count = await db.get_pending_count(chat_id)
                await db.update_channel_setting(chat_id, 'pending_requests', pending_count)
            except Exception as e:
                logger.error(f'Error updating pending count: {e}')
        if not channel:
            # Channel not registered - auto approve
            try:
                await join_request.approve()
            except Exception:
                pass
            return

        approve_mode = channel.get('approve_mode', 'instant')
        auto_approve = channel.get('auto_approve', True)
        # ALWAYS check force subscribe BEFORE approve mode logic
        if channel.get('force_subscribe_enabled') and channel.get('force_subscribe_channels'):
            required_channels_raw = channel['force_subscribe_channels']
            if isinstance(required_channels_raw, str):
                import json as _json
                try:
                    required_channels = _json.loads(required_channels_raw)
                except (ValueError, TypeError):
                    required_channels = []
            elif isinstance(required_channels_raw, list):
                required_channels = required_channels_raw
            else:
                required_channels = []

            if required_channels:
                all_joined = True
                not_joined = []
                for req_ch in required_channels:
                    try:
                        member = await context.bot.get_chat_member(req_ch['chat_id'], user_id)
                        if member.status in ('left', 'kicked'):
                            all_joined = False
                            not_joined.append(req_ch)
                    except Exception:
                        all_joined = False
                        not_joined.append(req_ch)

                if not all_joined:
                    try:
                        text = (f'\U0001f44b Welcome! To join {chat.title}, '
                                f'please join these channels first:\n\n')
                        buttons = []
                        for ch in not_joined:
                            text += f"\u2022 {ch.get('title', 'Channel')}\n"
                            if ch.get('url'):
                                buttons.append([InlineKeyboardButton(
                                    f"\U0001f4e2 Join {ch.get('title', '')}",
                                    url=ch['url']
                                )])
                        buttons.append([InlineKeyboardButton(
                            "\u2705 I've Joined \u2014 Verify Me",
                            callback_data=f'verify_force_sub:{chat_id}'
                        )])
                        watermark = await get_watermark(db, chat_id)
                        text += watermark
                        await context.bot.send_message(
                            user_id, text,
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
                        await db.update_join_request_force_sub(user_id, chat_id, True)
                    except Exception as e:
                        logger.warning(f'Could not send force sub DM to {user_id}: {e}')
                        try:
                            await db.update_join_request_force_sub(user_id, chat_id, True)
                        except Exception:
                            pass
                    # ALWAYS return here - never fall through to auto-approve
                    return

        if not auto_approve or approve_mode == 'manual':
            # Notify owner about manual request
            try:
                owner_id = channel['owner_id']
                await context.bot.send_message(
                    owner_id,
                    f'\U0001f4cb New join request for {chat.title}\n'
                    f'User: {user.first_name} (@{user.username or "no_username"})\n'
                    f'ID: {user_id}',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('\u2705 Approve', callback_data=f'approve_one:{chat_id}:{user_id}'),
                         InlineKeyboardButton('\u274c Decline', callback_data=f'decline_one:{chat_id}:{user_id}')]
                    ])
                )
            except Exception as e:
                logger.warning(f'Could not notify owner: {e}')
            return

        if approve_mode == 'drip':
            # Saved as pending, drip scheduler will handle
            return

        # Step 5 & 6: Send welcome DM then approve
        await _approve_and_dm(join_request, user, chat, channel, db, context)

    except Exception as e:
        logger.exception(f'CRITICAL: Error in join_request_handler: {e}')
        # Do NOT auto-approve on error - it would bypass force subscribe
        # Only approve if force_sub is not enabled for this channel
        try:
            _db = context.application.bot_data.get('db')
            if _db:
                _ch = await _db.get_channel(update.chat_join_request.chat.id)
                if _ch and _ch.get('force_subscribe_enabled'):
                    logger.warning('Skipping fallback approve - force sub is enabled')
                    return
            await update.chat_join_request.approve()
        except Exception:
            pass
