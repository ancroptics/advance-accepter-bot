import asyncio
import json
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters
from telethon.errors import PhoneCodeExpiredError, PhoneCodeInvalidError

from services.session_crypto import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)


def _code_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔁 Send New Code / Try SMS', callback_data='tg_session_resend_code')],
        [InlineKeyboardButton('🔙 Back', callback_data='telegram_session_menu')],
    ])


def _code_sent_text(details=None, fresh=False):
    details = details or {}
    sent_type = (details.get('type') or '').lower()
    next_type = (details.get('next_type') or '').lower()
    timeout = details.get('timeout')
    prefix = 'I sent a fresh Telegram login code now.' if fresh else 'Telegram sent a login code.'

    if sent_type == 'app':
        destination = 'Check the official Telegram app or Telegram service notification on your logged-in devices.'
    elif sent_type == 'sms':
        destination = 'Check your SMS messages for the Telegram code.'
    elif sent_type == 'call':
        destination = 'Telegram should call the phone number with the code.'
    else:
        destination = 'Check Telegram first, then SMS if Telegram routes it there.'

    fallback = ''
    if next_type:
        wait = f' after about {timeout} seconds' if timeout else ''
        fallback = f'\n\nIf nothing arrives, tap "Send New Code / Try SMS"{wait}.'

    return (
        f'{prefix}\n\n'
        f'{destination}\n\n'
        'Send only the newest numeric code here. Do not use older codes.'
        f'{fallback}\n\n'
        'Send /cancel to abort.'
    )


def _delivery_details(sent):
    code_type = getattr(sent, 'type', None)
    next_type = getattr(sent, 'next_type', None)
    type_name = code_type.__class__.__name__.replace('SentCodeType', '') if code_type else 'Unknown'
    next_name = next_type.__class__.__name__.replace('CodeType', '') if next_type else ''
    timeout = getattr(sent, 'timeout', None) or getattr(code_type, 'timeout', None)
    return {'type': type_name.lower(), 'next_type': next_name.lower(), 'timeout': timeout}


async def _send_login_code_with_details(phone, force_sms=False):
    from services import user_telethon

    client = user_telethon._client()
    await client.connect()
    try:
        sent = await client.send_code_request(phone, force_sms=force_sms)
        await asyncio.sleep(1)
        return client.session.save(), sent.phone_code_hash, _delivery_details(sent)
    finally:
        await client.disconnect()


def _parse_force_channels(raw):
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = []
    elif isinstance(raw, list):
        parsed = raw
    else:
        parsed = []
    return parsed if isinstance(parsed, list) else []


async def _process_force_sub_join_request(context, db, user_id, force_chat_id):
    try:
        rows = await db.pool.fetch("""
            SELECT jr.chat_id,
                   mc.chat_title,
                   mc.force_subscribe_channels,
                   COALESCE(mc.force_sub_mode, 'auto') AS force_sub_mode
            FROM join_requests jr
            JOIN managed_channels mc ON mc.chat_id = jr.chat_id
            WHERE jr.user_id = $1
              AND jr.status = 'pending'
              AND COALESCE(jr.force_sub_required, FALSE) = TRUE
              AND mc.force_subscribe_enabled = TRUE
        """, user_id)
    except Exception as e:
        logger.warning(f'Could not load pending force-sub parents for {user_id}: {e}')
        return 0

    from handlers.force_subscribe import _force_sub_requirement_satisfied

    completed = 0
    for row in rows or []:
        row = dict(row)
        parent_chat_id = row['chat_id']
        force_channels = _parse_force_channels(row.get('force_subscribe_channels') or [])
        if not any(
            isinstance(ch, dict)
            and ch.get('chat_id') == force_chat_id
            and ch.get('invite_requires_approval')
            for ch in force_channels
        ):
            continue

        still_missing = False
        for req_ch in force_channels:
            if not await _force_sub_requirement_satisfied(context, db, req_ch, user_id):
                still_missing = True
                break
        if still_missing:
            continue

        mode = row.get('force_sub_mode', 'auto')
        try:
            await db.update_join_request_force_sub(user_id, parent_chat_id, False)
            await db.update_force_sub_completed(user_id, parent_chat_id)
            if mode == 'manual':
                await context.bot.send_message(
                    user_id,
                    f'✅ Verified for {row.get("chat_title", "the channel")}. Your request is pending admin approval.',
                )
            elif mode == 'drip':
                await context.bot.send_message(
                    user_id,
                    f'✅ Verified for {row.get("chat_title", "the channel")}. Your request is queued for drip approval.',
                )
            else:
                await context.bot.approve_chat_join_request(parent_chat_id, user_id)
                await db.update_join_request_status(user_id, parent_chat_id, 'approved', 'force_sub_request')
                await context.bot.send_message(
                    user_id,
                    f'✅ Verified! You have been approved to join {row.get("chat_title", "the channel")}.',
                )
            completed += 1
        except Exception as e:
            logger.warning(f'Could not auto-complete force-sub request for {user_id} in {parent_chat_id}: {e}')
    return completed


async def _recheck_parent_force_sub_requests(context, db, user_id, parent_chat_id):
    channel = await db.get_channel(parent_chat_id)
    if not channel or not channel.get('force_subscribe_enabled'):
        return
    force_channels = _parse_force_channels(channel.get('force_subscribe_channels') or [])
    for req_ch in force_channels:
        if isinstance(req_ch, dict) and req_ch.get('invite_requires_approval') and req_ch.get('chat_id'):
            await _process_force_sub_join_request(context, db, user_id, req_ch['chat_id'])


def _patch_join_request_handlers():
    import handlers as handlers_pkg
    import handlers.join_request as join_request_mod
    import services.clone_manager as clone_manager

    original_main = getattr(join_request_mod, '_original_join_request_handler_hotfix', None)
    if original_main is None:
        original_main = join_request_mod.join_request_handler
        join_request_mod._original_join_request_handler_hotfix = original_main

    async def wrapped_join_request_handler(update, context):
        join_request = update.chat_join_request
        db = context.application.bot_data.get('db')
        if db and join_request:
            user_id = join_request.from_user.id
            chat_id = join_request.chat.id
            try:
                from handlers.force_subscribe import record_force_sub_join_request

                await record_force_sub_join_request(db, user_id, chat_id)
                await _process_force_sub_join_request(context, db, user_id, chat_id)
            except Exception as e:
                logger.warning(f'Force-sub pre-check failed for {user_id} in {chat_id}: {e}')
        await original_main(update, context)
        if db and join_request:
            await _recheck_parent_force_sub_requests(
                context,
                db,
                join_request.from_user.id,
                join_request.chat.id,
            )

    join_request_mod.join_request_handler = wrapped_join_request_handler
    handlers_pkg.join_request_handler = wrapped_join_request_handler

    original_clone = getattr(clone_manager, '_original_clone_join_request_handler_hotfix', None)
    if original_clone is None:
        original_clone = clone_manager.clone_join_request_handler
        clone_manager._original_clone_join_request_handler_hotfix = original_clone

    async def wrapped_clone_join_request_handler(update, context):
        join_request = update.chat_join_request
        db = context.application.bot_data.get('db')
        if db and join_request:
            user_id = join_request.from_user.id
            chat_id = join_request.chat.id
            try:
                from handlers.force_subscribe import record_force_sub_join_request

                await record_force_sub_join_request(db, user_id, chat_id)
                await _process_force_sub_join_request(context, db, user_id, chat_id)
            except Exception as e:
                logger.warning(f'Clone force-sub pre-check failed for {user_id} in {chat_id}: {e}')
        await original_clone(update, context)
        if db and join_request:
            await _recheck_parent_force_sub_requests(
                context,
                db,
                join_request.from_user.id,
                join_request.chat.id,
            )

    clone_manager.clone_join_request_handler = wrapped_clone_join_request_handler


def _patch_telegram_login():
    from services import user_telethon
    import handlers.telegram_session as tg

    async def handle_phone(update, context):
        db = context.application.bot_data.get('db')
        user_id = update.effective_user.id
        phone = (update.message.text or '').strip().replace(' ', '')
        if not re.fullmatch(r'\+\d{8,15}', phone):
            await update.message.reply_text('Send the phone number in international format, like +15551234567.')
            return tg.PHONE

        await update.message.reply_text('Sending Telegram login code...')
        try:
            temp_session, code_hash, details = await _send_login_code_with_details(phone, force_sms=False)
            await tg._save_login_state(db, user_id, phone, encrypt_text(temp_session), code_hash)
        except Exception as e:
            logger.warning(f'Telegram login code send failed for owner {user_id}: {e}')
            await update.message.reply_text(
                f'Could not send login code: {str(e)[:120]}',
                reply_markup=tg._back_markup(),
            )
            return ConversationHandler.END

        await update.message.reply_text(_code_sent_text(details), reply_markup=_code_markup())
        return tg.CODE

    async def handle_code(update, context):
        db = context.application.bot_data.get('db')
        user_id = update.effective_user.id
        code = re.sub(r'\D', '', update.message.text or '')
        try:
            await update.message.delete()
        except Exception:
            pass
        row = await tg._get_session(db, user_id)
        if not row or not row.get('temp_session_encrypted') or not row.get('phone_code_hash'):
            await update.message.reply_text('Login state expired. Start again from Old Request Sync.', reply_markup=tg._back_markup())
            return ConversationHandler.END

        try:
            result = await user_telethon.complete_login(
                decrypt_text(row['temp_session_encrypted']),
                row['phone'],
                row['phone_code_hash'],
                code,
            )
            if result.get('needs_password'):
                await tg._save_password_state(db, user_id, encrypt_text(result['temp_session']))
                await update.message.reply_text(
                    'This Telegram account has 2FA enabled. Send the 2FA password.\n\nSend /cancel to abort.',
                    reply_markup=tg._back_markup(),
                )
                return tg.PASSWORD
            await tg._save_connected_session(db, user_id, encrypt_text(result['session']))
        except PhoneCodeExpiredError:
            try:
                temp_session, code_hash, details = await _send_login_code_with_details(row['phone'], force_sms=True)
                await tg._save_login_state(db, user_id, row['phone'], encrypt_text(temp_session), code_hash)
                await update.message.reply_text(
                    'That Telegram login code expired.\n\n' + _code_sent_text(details, fresh=True),
                    reply_markup=_code_markup(),
                )
                return tg.CODE
            except Exception as resend_error:
                logger.warning(f'Telegram code resend failed for owner {user_id}: {resend_error}')
                await update.message.reply_text(
                    f'Code expired and resend failed: {str(resend_error)[:120]}',
                    reply_markup=tg._back_markup(),
                )
                return ConversationHandler.END
        except PhoneCodeInvalidError:
            await update.message.reply_text(
                'That Telegram login code was invalid. Send the newest numeric code from Telegram.',
                reply_markup=tg._back_markup(),
            )
            return tg.CODE
        except Exception as e:
            logger.warning(f'Telegram code login failed for owner {user_id}: {e}')
            await update.message.reply_text(f'Login failed: {str(e)[:120]}', reply_markup=tg._back_markup())
            return ConversationHandler.END

        await update.message.reply_text(
            '✅ Telegram session connected. You can now sync old pending join requests.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('🔄 Open Old Request Sync', callback_data='telegram_session_menu')]
            ]),
        )
        return ConversationHandler.END

    async def resend_login_code(update, context):
        query = update.callback_query
        await query.answer('Sending a fresh code...')
        db = context.application.bot_data.get('db')
        user_id = query.from_user.id
        row = await tg._get_session(db, user_id)
        if not row or not row.get('phone'):
            await query.edit_message_text('Login state expired. Start again from Old Request Sync.', reply_markup=tg._back_markup())
            return ConversationHandler.END

        try:
            temp_session, code_hash, details = await _send_login_code_with_details(row['phone'], force_sms=True)
            await tg._save_login_state(db, user_id, row['phone'], encrypt_text(temp_session), code_hash)
            await query.edit_message_text(_code_sent_text(details, fresh=True), reply_markup=_code_markup())
            return tg.CODE
        except Exception as e:
            logger.warning(f'Telegram code resend failed for owner {user_id}: {e}')
            await query.edit_message_text(
                f'Could not send a fresh code: {str(e)[:120]}',
                reply_markup=tg._back_markup(),
            )
            return ConversationHandler.END

    tg.handle_phone = handle_phone
    tg.handle_code = handle_code
    tg.resend_login_code = resend_login_code
    tg._code_markup = _code_markup

    tg.telegram_session_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(tg.start_telegram_login, pattern=r'^tg_session_start$')],
        states={
            tg.PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            tg.CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code),
                CallbackQueryHandler(resend_login_code, pattern=r'^tg_session_resend_code$'),
            ],
            tg.PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, tg.handle_password)],
        },
        fallbacks=[CommandHandler('cancel', tg.cancel_login)],
        per_message=False,
    )


def apply_account_force_sub_hotfixes():
    import handlers.force_subscribe as force_subscribe

    force_subscribe.process_force_sub_join_request = _process_force_sub_join_request
    _patch_join_request_handlers()
    _patch_telegram_login()
