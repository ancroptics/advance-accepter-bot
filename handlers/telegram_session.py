import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telethon.errors import PhoneCodeExpiredError, PhoneCodeInvalidError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from services import user_telethon
from services.session_crypto import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)

PHONE, CODE, PASSWORD = range(3)


async def _ensure_table(db):
    await db.pool.execute("""
        CREATE TABLE IF NOT EXISTS telegram_user_sessions (
            owner_id BIGINT PRIMARY KEY REFERENCES channel_owners(user_id) ON DELETE CASCADE,
            phone TEXT,
            session_encrypted TEXT,
            temp_session_encrypted TEXT,
            phone_code_hash TEXT,
            status TEXT DEFAULT 'pending',
            connected_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE telegram_user_sessions ADD COLUMN IF NOT EXISTS phone TEXT;
        ALTER TABLE telegram_user_sessions ADD COLUMN IF NOT EXISTS session_encrypted TEXT;
        ALTER TABLE telegram_user_sessions ADD COLUMN IF NOT EXISTS temp_session_encrypted TEXT;
        ALTER TABLE telegram_user_sessions ADD COLUMN IF NOT EXISTS phone_code_hash TEXT;
        ALTER TABLE telegram_user_sessions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
        ALTER TABLE telegram_user_sessions ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;
        ALTER TABLE telegram_user_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
    """)


async def _get_session(db, owner_id):
    await _ensure_table(db)
    return await db.pool.fetchrow(
        'SELECT * FROM telegram_user_sessions WHERE owner_id = $1',
        owner_id
    )


async def _save_login_state(db, owner_id, phone, temp_session_encrypted, phone_code_hash):
    await _ensure_table(db)
    return await db.pool.execute("""
        INSERT INTO telegram_user_sessions (
            owner_id, phone, temp_session_encrypted, phone_code_hash, status, updated_at
        )
        VALUES ($1, $2, $3, $4, 'pending_code', NOW())
        ON CONFLICT (owner_id) DO UPDATE SET
            phone = $2,
            temp_session_encrypted = $3,
            phone_code_hash = $4,
            status = 'pending_code',
            updated_at = NOW()
    """, owner_id, phone, temp_session_encrypted, phone_code_hash)


async def _save_password_state(db, owner_id, temp_session_encrypted):
    await _ensure_table(db)
    return await db.pool.execute("""
        UPDATE telegram_user_sessions
        SET temp_session_encrypted = $2,
            status = 'pending_password',
            updated_at = NOW()
        WHERE owner_id = $1
    """, owner_id, temp_session_encrypted)


async def _save_connected_session(db, owner_id, session_encrypted):
    await _ensure_table(db)
    return await db.pool.execute("""
        UPDATE telegram_user_sessions
        SET session_encrypted = $2,
            temp_session_encrypted = NULL,
            phone_code_hash = NULL,
            status = 'connected',
            connected_at = NOW(),
            updated_at = NOW()
        WHERE owner_id = $1
    """, owner_id, session_encrypted)


async def _delete_session(db, owner_id):
    await _ensure_table(db)
    return await db.pool.execute(
        'DELETE FROM telegram_user_sessions WHERE owner_id = $1',
        owner_id
    )


def _back_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Back', callback_data='telegram_session_menu')]])


def _code_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔁 Send New Code', callback_data='tg_session_resend_code')],
        [InlineKeyboardButton('🔙 Back', callback_data='telegram_session_menu')],
    ])


async def show_telegram_session_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    user_id = update.effective_user.id
    row = await _get_session(db, user_id)
    connected = bool(row and row.get('status') == 'connected' and row.get('session_encrypted'))
    channels = await db.get_owner_channels(user_id)

    status = 'Connected' if connected else 'Not connected'
    text = (
        '🔐 OLD JOIN REQUEST SYNC\n\n'
        f'Status: {status}\n\n'
        'This lets a channel owner connect their own Telegram user session so the bot can import '
        'old pending join requests that the Bot API cannot list.\n\n'
        'Only connect an account that is admin in the channels you manage here.'
    )

    buttons = [[InlineKeyboardButton('🔑 Connect / Reconnect', callback_data='tg_session_start')]]
    if connected:
        if channels:
            buttons.append([InlineKeyboardButton('🔄 Sync All My Channels', callback_data='tg_sync_all')])
            for ch in channels[:10]:
                title = ch.get('chat_title', 'Channel')[:28]
                buttons.append([InlineKeyboardButton(
                    f'🔄 {title}',
                    callback_data=f"tg_sync_channel:{ch['chat_id']}"
                )])
        buttons.append([InlineKeyboardButton('🗑 Disconnect Telegram Session', callback_data='tg_session_disconnect')])
    buttons.append([InlineKeyboardButton('🔙 Back', callback_data='dashboard')])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def start_telegram_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not user_telethon.configured():
        await query.edit_message_text(
            'Telethon API is not configured yet. Ask the platform owner to set TELETHON_API_ID and TELETHON_API_HASH.',
            reply_markup=_back_markup()
        )
        return ConversationHandler.END

    await query.edit_message_text(
        '🔑 CONNECT TELEGRAM SESSION\n\n'
        'Send the phone number for the Telegram account that is admin in your channels.\n\n'
        'Format: +15551234567\n\n'
        'Send /cancel to abort.',
        reply_markup=_back_markup()
    )
    return PHONE


async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.application.bot_data.get('db')
    user_id = update.effective_user.id
    phone = (update.message.text or '').strip().replace(' ', '')
    if not re.fullmatch(r'\+\d{8,15}', phone):
        await update.message.reply_text('Send the phone number in international format, like +15551234567.')
        return PHONE

    await update.message.reply_text('Sending Telegram login code...')
    try:
        temp_session, code_hash = await user_telethon.send_login_code(phone)
        await _save_login_state(db, user_id, phone, encrypt_text(temp_session), code_hash)
    except Exception as e:
        logger.warning(f'Telegram login code send failed for owner {user_id}: {e}')
        await update.message.reply_text(
            f'Could not send login code: {str(e)[:120]}',
            reply_markup=_back_markup()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        'Telegram sent a login code. Send only the numeric code here.\n\n'
        'Send /cancel to abort.',
        reply_markup=_code_markup()
    )
    return CODE


async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.application.bot_data.get('db')
    user_id = update.effective_user.id
    code = re.sub(r'\D', '', update.message.text or '')
    try:
        await update.message.delete()
    except Exception:
        pass
    row = await _get_session(db, user_id)
    if not row or not row.get('temp_session_encrypted') or not row.get('phone_code_hash'):
        await update.message.reply_text('Login state expired. Start again from Old Request Sync.', reply_markup=_back_markup())
        return ConversationHandler.END

    try:
        result = await user_telethon.complete_login(
            decrypt_text(row['temp_session_encrypted']),
            row['phone'],
            row['phone_code_hash'],
            code,
        )
        if result.get('needs_password'):
            await _save_password_state(db, user_id, encrypt_text(result['temp_session']))
            await update.message.reply_text(
                'This Telegram account has 2FA enabled. Send the 2FA password.\n\n'
                'Send /cancel to abort.',
                reply_markup=_back_markup()
            )
            return PASSWORD
        await _save_connected_session(db, user_id, encrypt_text(result['session']))
    except PhoneCodeExpiredError:
        try:
            temp_session, code_hash = await user_telethon.send_login_code(row['phone'], force_sms=True)
            await _save_login_state(db, user_id, row['phone'], encrypt_text(temp_session), code_hash)
            await update.message.reply_text(
                'That Telegram login code expired. I sent a fresh code now.\n\n'
                'Send the newest numeric code only. Do not use the previous code.',
                reply_markup=_code_markup()
            )
            return CODE
        except Exception as resend_error:
            logger.warning(f'Telegram code resend failed for owner {user_id}: {resend_error}')
            await update.message.reply_text(
                f'Code expired and resend failed: {str(resend_error)[:120]}',
                reply_markup=_back_markup()
            )
            return ConversationHandler.END
    except PhoneCodeInvalidError:
        await update.message.reply_text(
            'That Telegram login code was invalid. Send the newest numeric code from Telegram.',
            reply_markup=_back_markup()
        )
        return CODE
    except Exception as e:
        logger.warning(f'Telegram code login failed for owner {user_id}: {e}')
        await update.message.reply_text(
            f'Login failed: {str(e)[:120]}',
            reply_markup=_back_markup()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        '✅ Telegram session connected. You can now sync old pending join requests.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Open Old Request Sync', callback_data='telegram_session_menu')]
        ])
    )
    return ConversationHandler.END


async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.application.bot_data.get('db')
    user_id = update.effective_user.id
    password = update.message.text or ''
    try:
        await update.message.delete()
    except Exception:
        pass
    row = await _get_session(db, user_id)
    if not row or not row.get('temp_session_encrypted'):
        await update.message.reply_text('Login state expired. Start again from Old Request Sync.', reply_markup=_back_markup())
        return ConversationHandler.END

    try:
        session = await user_telethon.complete_password(
            decrypt_text(row['temp_session_encrypted']),
            password,
        )
        await _save_connected_session(db, user_id, encrypt_text(session))
    except Exception as e:
        logger.warning(f'Telegram 2FA login failed for owner {user_id}: {e}')
        await update.message.reply_text(
            f'2FA login failed: {str(e)[:120]}',
            reply_markup=_back_markup()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        '✅ Telegram session connected. You can now sync old pending join requests.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Open Old Request Sync', callback_data='telegram_session_menu')]
        ])
    )
    return ConversationHandler.END


async def cancel_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Telegram session login cancelled.', reply_markup=_back_markup())
    return ConversationHandler.END


async def resend_login_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer('Sending a fresh code...')
    db = context.application.bot_data.get('db')
    user_id = query.from_user.id
    row = await _get_session(db, user_id)
    if not row or not row.get('phone'):
        await query.edit_message_text('Login state expired. Start again from Old Request Sync.', reply_markup=_back_markup())
        return ConversationHandler.END

    try:
        temp_session, code_hash = await user_telethon.send_login_code(row['phone'], force_sms=True)
        await _save_login_state(db, user_id, row['phone'], encrypt_text(temp_session), code_hash)
        await query.edit_message_text(
            'I sent a fresh Telegram login code now.\n\n'
            'Send only the newest numeric code. Do not use older codes.',
            reply_markup=_code_markup()
        )
        return CODE
    except Exception as e:
        logger.warning(f'Telegram code resend failed for owner {user_id}: {e}')
        await query.edit_message_text(
            f'Could not send a fresh code: {str(e)[:120]}',
            reply_markup=_back_markup()
        )
        return ConversationHandler.END


async def disconnect_telegram_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db = context.application.bot_data.get('db')
    await _delete_session(db, query.from_user.id)
    await query.edit_message_text(
        '✅ Telegram session disconnected and removed.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Back', callback_data='telegram_session_menu')]])
    )


async def sync_old_requests(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    query = update.callback_query
    await query.answer()
    db = context.application.bot_data.get('db')
    user_id = query.from_user.id
    row = await _get_session(db, user_id)
    if not row or row.get('status') != 'connected' or not row.get('session_encrypted'):
        await query.edit_message_text('Connect your Telegram session first.', reply_markup=_back_markup())
        return

    channels = await db.get_owner_channels(user_id)
    if chat_id is not None:
        channels = [ch for ch in channels if ch['chat_id'] == chat_id]
    if not channels:
        await query.edit_message_text('No channels found to sync.', reply_markup=_back_markup())
        return

    await query.edit_message_text('Syncing old pending join requests...')
    session = decrypt_text(row['session_encrypted'])
    total_imported = 0
    lines = []
    for ch in channels:
        imported = 0
        try:
            requests = await user_telethon.get_pending_join_requests(session, ch['chat_id'])
            for req in requests:
                await db.save_join_request(
                    user_id=req['user_id'],
                    chat_id=ch['chat_id'],
                    username=req.get('username'),
                    first_name=req.get('first_name'),
                )
                await db.upsert_end_user(
                    user_id=req['user_id'],
                    username=req.get('username'),
                    first_name=req.get('first_name'),
                    last_name=req.get('last_name'),
                    source='old_request_sync',
                    source_channel=ch['chat_id'],
                )
                imported += 1
            pending = await db.get_pending_count(ch['chat_id'])
            await db.update_channel_setting(ch['chat_id'], 'pending_requests', pending)
            total_imported += imported
            lines.append(f"{ch.get('chat_title', 'Channel')}: {imported} imported")
        except Exception as e:
            logger.warning(f'Old request sync failed for {ch["chat_id"]}: {e}')
            lines.append(f"{ch.get('chat_title', 'Channel')}: failed ({str(e)[:60]})")

    text = '✅ Old request sync complete.\n\n' + '\n'.join(lines)
    text += f'\n\nTotal imported: {total_imported}'
    buttons = []
    if chat_id is not None:
        buttons.append([InlineKeyboardButton('✅ Approve Synced Requests', callback_data=f'batch_approve:{chat_id}:-1')])
    else:
        buttons.append([InlineKeyboardButton('✅ Approve All Synced Requests', callback_data='batch_all')])
    buttons.extend([
        [InlineKeyboardButton('📋 My Channels', callback_data='my_channels')],
        [InlineKeyboardButton('🔙 Old Request Sync', callback_data='telegram_session_menu')],
    ])
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def sync_old_requests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    chat_id = int(data.split(':')[1]) if data.startswith('tg_sync_channel:') else None
    await sync_old_requests(update, context, chat_id=chat_id)


telegram_session_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_telegram_login, pattern=r'^tg_session_start$')],
    states={
        PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
        CODE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code),
            CallbackQueryHandler(resend_login_code, pattern=r'^tg_session_resend_code$'),
        ],
        PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password)],
    },
    fallbacks=[CommandHandler('cancel', cancel_login)],
    per_message=False,
)
