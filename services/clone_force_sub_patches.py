import json
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from handlers.force_subscribe import (
    _force_sub_requirement_satisfied,
    record_force_sub_join_request,
)
import services.clone_manager as clone_manager

logger = logging.getLogger(__name__)


async def _patched_clone_force_sub_verify(update, context, chat_id):
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    if not db:
        await update.message.reply_text('Bot is initializing, try again.')
        return

    channel = await db.get_channel(chat_id)
    if not channel:
        await update.message.reply_text('Channel not found.')
        return

    required_channels_raw = channel.get('force_subscribe_channels') or []
    if isinstance(required_channels_raw, str):
        try:
            required_channels = json.loads(required_channels_raw)
        except (ValueError, TypeError):
            required_channels = []
    else:
        required_channels = required_channels_raw if isinstance(required_channels_raw, list) else []

    not_joined = []
    for req_ch in required_channels:
        if not await _force_sub_requirement_satisfied(context, db, req_ch, user_id):
            not_joined.append(req_ch)

    if not not_joined:
        force_sub_mode = channel.get('force_sub_mode', 'auto')
        if force_sub_mode == 'manual':
            await db.update_join_request_force_sub(user_id, chat_id, False)
            await db.update_force_sub_completed(user_id, chat_id)
            await update.message.reply_text('✅ Verified! Your request is pending admin approval.')
            return
        if force_sub_mode == 'drip':
            await db.update_join_request_force_sub(user_id, chat_id, False)
            await db.update_force_sub_completed(user_id, chat_id)
            await update.message.reply_text('✅ Verified! Your request is queued for drip approval.')
            return

        try:
            await context.bot.approve_chat_join_request(chat_id, user_id)
            await db.update_join_request_status(user_id, chat_id, 'approved', 'force_sub_clone')
            await db.update_force_sub_completed(user_id, chat_id)
            await update.message.reply_text(
                f'✅ Verified! You\'ve been approved to join {channel.get("chat_title", "the channel")}!'
            )
        except Exception as e:
            logger.error(f'Error approving after clone force sub verify: {e}')
            await update.message.reply_text('✅ Verified! You should now have access.')
        return

    text = '❌ You haven\'t joined all required channels yet:\n\n'
    buttons = []
    for ch in not_joined:
        text += f"• {ch.get('title', 'Channel')}\n"
        if ch.get('url'):
            buttons.append([InlineKeyboardButton(
                f"📢 Join {ch.get('title', '')}",
                url=ch['url'],
            )])
    bot_info = await context.bot.get_me()
    buttons.append([InlineKeyboardButton(
        '✅ I\'ve Joined — Verify',
        url=f'https://t.me/{bot_info.username}?start=verify_{chat_id}',
    )])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def _patched_clone_callback_handler(update, context):
    query = update.callback_query
    data = query.data or ''
    if not data.startswith('clone_batch_approve:'):
        return await clone_manager._original_clone_callback_handler(update, context)

    try:
        await query.answer()
        db = context.application.bot_data.get('db')
        owner_id = context.application.bot_data.get('owner_id')
        user_id = query.from_user.id
        if user_id != owner_id:
            return

        chat_id = int(data.split(':')[1])
        pending = await db.get_pending_requests(chat_id)
        pending = [
            req for req in (pending or [])
            if req.get('force_sub_required') is None or req.get('force_sub_completed')
        ]

        approved = 0
        for req in pending:
            try:
                await context.bot.approve_chat_join_request(chat_id, req['user_id'])
                await db.update_join_request_after_approve(
                    user_id=req['user_id'],
                    chat_id=chat_id,
                    dm_sent=False,
                    processed_by='clone_batch',
                )
                approved += 1
            except Exception:
                pass

        await query.answer(f'Approved {approved} requests!', show_alert=True)
        await clone_manager._refresh_clone_channel_view(query, context, db, chat_id, owner_id)
    except Exception as e:
        logger.error(f'Error in patched clone batch approve: {e}')
        try:
            await query.edit_message_text(f'An error occurred: {str(e)[:200]}')
        except Exception:
            pass


async def _patched_clone_join_request_handler(update, context):
    try:
        join_request = update.chat_join_request
        user = join_request.from_user
        chat = join_request.chat
        chat_id = chat.id
        user_id = user.id

        db = context.application.bot_data.get('db')
        owner_id = context.application.bot_data.get('owner_id')
        clone_id = context.application.bot_data.get('clone_id')

        if not db:
            logger.error(f'Clone {clone_id}: DB not available')
            try:
                await join_request.approve()
            except Exception:
                pass
            return

        try:
            await record_force_sub_join_request(db, user_id, chat_id)
        except Exception as e:
            logger.warning(f'Clone {clone_id}: Could not record force-sub join request for {user_id} in {chat_id}: {e}')

        try:
            await db.save_join_request(
                user_id=user_id,
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name,
                user_language=user.language_code,
            )
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error saving join request: {e}')

        try:
            await db.upsert_end_user(
                user_id=user_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                source='clone_join_request',
                source_channel=chat_id,
            )
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error upserting end user: {e}')

        channel = await db.get_channel(chat_id)
        if not channel:
            try:
                await db.upsert_channel(
                    chat_id=chat_id,
                    owner_id=owner_id,
                    chat_title=chat.title,
                    chat_username=chat.username,
                )
                channel = await db.get_channel(chat_id)
            except Exception as e:
                logger.error(f'Clone {clone_id}: Error registering channel: {e}')

        if not channel:
            try:
                await join_request.approve()
            except Exception:
                pass
            return

        try:
            pending_count = await db.get_pending_count(chat_id)
            await db.update_channel_setting(chat_id, 'pending_requests', pending_count)
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error updating pending count: {e}')

        approve_mode = channel.get('approve_mode', 'instant')
        auto_approve = channel.get('auto_approve', True)

        if channel.get('force_subscribe_enabled') and channel.get('force_subscribe_channels'):
            required_channels_raw = channel['force_subscribe_channels']
            if isinstance(required_channels_raw, str):
                try:
                    required_channels = json.loads(required_channels_raw)
                except (ValueError, TypeError):
                    required_channels = []
            elif isinstance(required_channels_raw, list):
                required_channels = required_channels_raw
            else:
                required_channels = []

            not_joined = []
            for req_ch in required_channels:
                if not await _force_sub_requirement_satisfied(context, db, req_ch, user_id):
                    not_joined.append(req_ch)

            if not_joined:
                try:
                    fsub_text = (
                        f'👋 Welcome! To join {chat.title}, '
                        f'please join these channels first:\n\n'
                    )
                    buttons = []
                    for ch in not_joined:
                        fsub_text += f"• {ch.get('title', 'Channel')}\n"
                        if ch.get('url'):
                            buttons.append([InlineKeyboardButton(
                                f"📢 Join {ch.get('title', '')}",
                                url=ch['url'],
                            )])
                    bot_info = await context.bot.get_me()
                    buttons.append([InlineKeyboardButton(
                        "✅ I've Joined — Verify Me",
                        url=f'https://t.me/{bot_info.username}?start=verify_{chat_id}',
                    )])
                    await context.bot.send_message(
                        user_id,
                        fsub_text,
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
                    await db.update_join_request_force_sub(user_id, chat_id, True)
                except Exception as e:
                    logger.warning(f'Clone {clone_id}: Could not send force sub DM: {e}')
                    try:
                        await db.update_join_request_force_sub(user_id, chat_id, True)
                    except Exception:
                        pass
                return

        if not auto_approve or approve_mode == 'manual':
            try:
                parent_app = context.application.bot_data.get('parent_app')
                if parent_app:
                    await parent_app.bot.send_message(
                        owner_id,
                        f'📋 New join request for {chat.title} (via clone)\n'
                        f'User: {user.first_name} (@{user.username or "no_username"})\n'
                        f'ID: {user_id}',
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton('✅ Approve', callback_data=f'approve_one:{chat_id}:{user_id}'),
                                InlineKeyboardButton('❌ Decline', callback_data=f'decline_one:{chat_id}:{user_id}'),
                            ],
                        ]),
                    )
            except Exception as e:
                logger.warning(f'Clone {clone_id}: Could not notify owner: {e}')
            return

        if approve_mode == 'drip':
            return

        dm_sent = False
        if channel.get('welcome_dm_enabled', True):
            try:
                welcome_text = channel.get('welcome_message', 'Welcome to {channel_name}! 🎉')
                welcome_text = welcome_text.replace('{first_name}', user.first_name or 'there')
                welcome_text = welcome_text.replace('{last_name}', user.last_name or '')
                welcome_text = welcome_text.replace('{username}', f'@{user.username}' if user.username else 'there')
                welcome_text = welcome_text.replace('{user_id}', str(user_id))
                welcome_text = welcome_text.replace('{channel_name}', chat.title or '')
                await context.bot.send_message(user_id, welcome_text)
                dm_sent = True
            except Exception as e:
                logger.warning(f'Clone {clone_id}: DM failed to {user_id}: {e}')

        try:
            await join_request.approve()
        except Exception as e:
            logger.error(f'Clone {clone_id}: Failed to approve {user_id}: {e}')

        try:
            await db.update_join_request_after_approve(
                user_id=user_id,
                chat_id=chat_id,
                dm_sent=dm_sent,
                processed_by='clone',
            )
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error updating after approve: {e}')

    except Exception as e:
        logger.exception(f'CRITICAL: Error in clone join_request_handler: {e}')
        try:
            db = context.application.bot_data.get('db')
            if db:
                channel = await db.get_channel(update.chat_join_request.chat.id)
                if channel and channel.get('force_subscribe_enabled'):
                    logger.warning('Clone fallback approve skipped because force sub is enabled')
                    return
            await update.chat_join_request.approve()
        except Exception:
            pass


def apply_clone_force_sub_patches():
    if not hasattr(clone_manager, '_original_clone_callback_handler'):
        clone_manager._original_clone_callback_handler = clone_manager.clone_callback_handler

    clone_manager._handle_clone_force_sub_verify = _patched_clone_force_sub_verify
    clone_manager.clone_callback_handler = _patched_clone_callback_handler
    clone_manager.clone_join_request_handler = _patched_clone_join_request_handler
