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

async def _approve_and_dm(join_request, user, chat, channel, db, context):
    """Send welcome DM first, then approve the request"""
    chat_id = chat.id
    user_id = user.id
    dm_sent = False
    dm_failed_reason = None
    dm_message_id = None

    # Step 5: Send Welcome DM
    if channel.get('welcome_dm_enabled', True):
        try:
            # Get welcome message (check multi-language first)
            welcome_text = get_welcome_for_language(
                channel, user.language_code
            )
            if not welcome_text:
                welcome_text = channel.get('welcome_message', 'Welcome to {channel_name}! \U0001f389')

            # Replace variables
            welcome_text = welcome_text.replace('{first_name}', user.first_name or 'there')
            welcome_text = welcome_text.replace('{last_name}', user.last_name or '')
            welcome_text = welcome_text.replace('{username}', f'@{user.username}' if user.username else 'there')
            welcome_text = welcome_text.replace('{user_id}', str(user_id))
            welcome_text = welcome_text.replace('{channel_name}', chat.title or '')
            welcome_text = welcome_text.replace('{channel_username}', f'@{chat.username}' if chat.username else '')
            welcome_text = welcome_text.replace('{member_count}', str(channel.get('member_count', 0)))
            welcome_text = welcome_text.replace('{referral_link}', f'https://t.me/{config.BOT_USERNAME}?start=ref_{user_id}')

            # Get user coins
            end_user = await db.get_end_user(user_id)
            coins = end_user.get('coins', 0) if end_user else 0
            welcome_text = welcome_text.replace('{coins}', str(coins))
            welcome_text = welcome_text.replace('{date}', datetime.now().strftime('%Y-%m-%d'))

            # Add watermark
            watermark = await get_watermark(db, chat_id)
            welcome_text += watermark

            # Add cross-promotion
            if config.ENABLE_CROSS_PROMO:
                cross_promo = await get_cross_promo_text(db, chat_id, channel.get('owner_id'))
                if cross_promo:
                    welcome_text += cross_promo

            # Build inline buttons
            reply_markup = None
            btns_data = None
            if channel.get('welcome_buttons_json'):
                try:
                    btns_data = channel['welcome_buttons_json']
                    if isinstance(btns_data, str):
                        import json as _json_btns
                        btns_data = _json_btns.loads(btns_data)
                except Exception:
                    btns_data = None
            # Fallback to owner's default welcome buttons if channel has none
            if not btns_data and channel.get('owner_id'):
                try:
                    import json as _json_btns2
                    default_btns_raw = await db.get_platform_setting(
                        f'owner_{channel["owner_id"]}_welcome_buttons', '[]'
                    )
                    btns_data = _json_btns2.loads(default_btns_raw) if isinstance(default_btns_raw, str) else default_btns_raw
                except Exception:
                    btns_data = None
            if btns_data:
                try:
                    button_rows = []
                    for btn in btns_data:
                        button_rows.append([InlineKeyboardButton(
                            btn.get('text', 'Link'),
                            url=btn.get('url', 'https://t.me')
                        )])
                    reply_markup = InlineKeyboardMarkup(button_rows)
                except Exception as e:
                    logger.warning(f'Error building welcome buttons: {e}')

            # Send the DM - try with HTML first, fallback to plain text
            media_type = channel.get('welcome_media_type')
            media_fid = channel.get('welcome_media_file_id')
            sent_msg = None

            async def _send_dm(parse_mode_val):
                """Helper to send DM with given parse mode."""
                nonlocal sent_msg
                if media_type == 'photo' and media_fid:
                    sent_msg = await context.bot.send_photo(
                        user_id, media_fid, caption=welcome_text,
                        parse_mode=parse_mode_val, reply_markup=reply_markup
                    )
                elif media_type == 'video' and media_fid:
                    sent_msg = await context.bot.send_video(
                        user_id, media_fid, caption=welcome_text,
                        parse_mode=parse_mode_val, reply_markup=reply_markup
                    )
                elif media_type == 'animation' and media_fid:
                    sent_msg = await context.bot.send_animation(
                        user_id, media_fid, caption=welcome_text,
                        parse_mode=parse_mode_val, reply_markup=reply_markup
                    )
                elif media_type == 'document' and media_fid:
                    sent_msg = await context.bot.send_document(
                        user_id, media_fid, caption=welcome_text,
                        parse_mode=parse_mode_val, reply_markup=reply_markup
                    )
                else:
                    sent_msg = await context.bot.send_message(
                        user_id, welcome_text,
                        parse_mode=parse_mode_val, reply_markup=reply_markup
                    )

            try:
                await _send_dm('HTML')
                dm_sent = True
                dm_message_id = sent_msg.message_id if sent_msg else None
            except Exception as e1:
                err_str = str(e1).lower()
                if "can't parse" in err_str or 'parse entities' in err_str or 'bad request' in err_str:
                    # HTML parse error - retry without parse_mode
                    try:
                        await _send_dm(None)
                        dm_sent = True
                        dm_message_id = sent_msg.message_id if sent_msg else None
                    except Exception as e2:
                        logger.warning(f'Welcome DM retry without HTML also failed to {user_id}: {e2}')
                        dm_failed_reason = 'error'
                elif 'forbidden' in err_str or 'blocked' in err_str or 'chat not found' in err_str:
                    dm_failed_reason = 'blocked'
                    try:
                        await db.mark_user_blocked(user_id)
                    except Exception:
                        pass
                else:
                    dm_failed_reason = str(e1)[:200]
                if not dm_sent:
                    logger.warning(f'DM failed to {user_id}: {e1}')

        except Exception as e:
            dm_failed_reason = str(e)[:200]
            logger.warning(f'DM failed to {user_id}: {e}')

    # Step 6: Approve the join request
    try:
        await join_request.approve()
    except Exception as e:
        logger.error(f'Failed to approve join request {user_id} in {chat_id}: {e}')

    # Update database
    try:
        await db.update_join_request_after_approve(
            user_id=user_id,
            chat_id=chat_id,
            dm_sent=dm_sent,
            dm_failed_reason=dm_failed_reason,
            dm_message_id=dm_message_id,
            processed_by='auto',
        )
    except Exception as e:
        logger.error(f'Error updating join request after approve: {e}')

    # Step 7: Log analytics event
    try:
        await db.log_event(
            'join_request_processed',
            owner_id=channel.get('owner_id'),
            channel_id=chat_id,
            user_id=user_id,
            data={'dm_sent': dm_sent, 'approval_mode': 'instant'}
        )
    except Exception as e:
        logger.error(f'Error logging analytics: {e}')
