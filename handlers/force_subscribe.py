import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

async def show_force_sub_menu(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    enabled = channel.get('force_subscribe_enabled', False)
    channels_raw = channel.get('force_subscribe_channels') or []
    if isinstance(channels_raw, str):
        try:
            channels = json.loads(channels_raw)
        except (ValueError, TypeError):
            channels = []
    else:
        channels = channels_raw if isinstance(channels_raw, list) else []
    timeout = 24
    status = '\U0001f7e2 Enabled' if enabled else '\U0001f534 Disabled'
    text = f'\U0001f512 FORCE SUBSCRIBE\n\nStatus: {status}\n\nRequired Channels:\n'
    if channels:
        for i, ch in enumerate(channels, 1):
            text += f"{i}. {ch.get('title', 'Unknown')} \u2705\n"
    else:
        text += 'None configured\n'
    text += f'\nTimeout: {timeout} hours\n(Auto-approve after timeout even if not joined)'
    toggle_text = '\U0001f534 Disable' if enabled else '\U0001f7e2 Enable'
    buttons = [
        [InlineKeyboardButton(toggle_text, callback_data=f'toggle_force_sub:{chat_id}')],
        [InlineKeyboardButton('\u2795 Add Channel', callback_data=f'add_force_sub_ch:{chat_id}')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def verify_force_subscribe(update, context, chat_id):
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return
    required_channels_raw = channel.get('force_subscribe_channels') or []
    if isinstance(required_channels_raw, str):
        try:
            required_channels = json.loads(required_channels_raw)
        except (ValueError, TypeError):
            required_channels = []
    else:
        required_channels = required_channels_raw if isinstance(required_channels_raw, list) else []
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
    if all_joined:
        try:
            await context.bot.approve_chat_join_request(chat_id, user_id)
            await db.update_join_request_status(user_id, chat_id, 'approved', 'force_sub')
            await db.update_force_sub_completed(user_id, chat_id)
            await query.edit_message_text(f'\u2705 Verified! You\'ve been approved to join {channel["chat_title"]}!')
        except Exception as e:
            logger.error(f'Error approving after force sub: {e}')
            await query.edit_message_text('\u2705 Verified! You should now have access.')
    else:
        text = '\u274c You haven\'t joined all channels yet. Please join:\n\n'
        buttons = []
        for ch in not_joined:
            text += f"\u2022 {ch.get('title', 'Channel')}\n"
            if ch.get('url'):
                buttons.append([InlineKeyboardButton(f"\U0001f4e2 Join {ch.get('title', '')}", url=ch['url'])])
        text += '\nPlease join all channels above, then click verify.'
        buttons.append([InlineKeyboardButton('\u2705 I\'ve Joined \u2014 Verify', callback_data=f'verify_force_sub:{chat_id}')])
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            if 'not modified' in str(e).lower():
                await query.answer('You still need to join all required channels!', show_alert=True)
            else:
                raise

force_subscribe_conv_handler = None

FORCE_SUB_INPUT = 100

async def handle_force_sub_channel_input(update, context):
    """Handle channel username/ID input for force subscribe setup."""
    text = update.message.text.strip()
    db = context.application.bot_data.get('db')
    chat_id = context.user_data.get('force_sub_target_channel')
    
    if not chat_id:
        await update.message.reply_text('\u274c Session expired. Please try again from channel settings.')
        return ConversationHandler.END
    
    try:
        if text.startswith('@'):
            channel_username = text
        elif text.startswith('-100'):
            channel_username = int(text)
        elif text.isdigit():
            channel_username = int('-100' + text)
        else:
            channel_username = '@' + text
        
        try:
            chat_info = await context.bot.get_chat(channel_username)
        except Exception:
            await update.message.reply_text(
                '\u274c Could not find that channel. Make sure:\n'
                '1. The channel/group exists\n'
                '2. The bot is a member of that channel\n'
                '3. You entered the correct username or ID\n\n'
                'Send the channel username (e.g. @mychannel) or /cancel'
            )
            return FORCE_SUB_INPUT

        # Verify bot is admin in the force sub channel (needed to check member status)
        try:
            bot_member = await context.bot.get_chat_member(chat_info.id, context.bot.id)
            if bot_member.status not in ('administrator', 'creator'):
                await update.message.reply_text(
                    f'\u26a0\ufe0f I need to be an admin in {chat_info.title} '
                    f'to verify if users have joined it.\n\n'
                    f'Please add me as admin to {chat_info.title} first, then try again.\n\n'
                    f'Send the channel username again after adding me, or /cancel'
                )
                return FORCE_SUB_INPUT
        except Exception:
            await update.message.reply_text(
                f'\u26a0\ufe0f I\'m not a member of {chat_info.title}.\n\n'
                f'Please add me as admin to that channel first so I can '
                f'verify user membership.\n\n'
                f'Send the channel username again after adding me, or /cancel'
            )
            return FORCE_SUB_INPUT
        
        channel = await db.get_channel(chat_id)
        current_channels_raw = channel.get('force_subscribe_channels') or []
        if isinstance(current_channels_raw, str):
            try:
                current_channels = json.loads(current_channels_raw)
            except (ValueError, TypeError):
                current_channels = []
        else:
            current_channels = current_channels_raw if isinstance(current_channels_raw, list) else []
        
        for ch in current_channels:
            if ch.get('chat_id') == chat_info.id:
                await update.message.reply_text(f'\u26a0\ufe0f {chat_info.title} is already in the force subscribe list!')
                return ConversationHandler.END
        
        new_entry = {
            'chat_id': chat_info.id,
            'title': chat_info.title,
            'username': chat_info.username or '',
            'url': f'https://t.me/{chat_info.username}' if chat_info.username else '',
        }
        
        # Check channel slot limit (base from tier + referral bonus)
        import config as _cfg
        user_id = update.effective_user.id
        owner = await db.get_owner(user_id)
        if _cfg.ENABLE_PREMIUM:
            from handlers.premium import get_tier_features
            tier = owner.get('tier', 'free') if owner else 'free'
            if user_id in _cfg.SUPERADMIN_IDS:
                tier = 'business'
            features = get_tier_features(tier)
            base_slots = features.get('max_channels', 1)
        else:
            base_slots = 999  # No limit when premium is off
        bonus_slots = await db.get_referral_bonus_slots(user_id)
        max_slots = base_slots + bonus_slots
        if len(current_channels) >= max_slots:
            refs_per_slot = getattr(_cfg, 'REFERRALS_PER_SLOT', 3)
            await update.message.reply_text(
                f'\u26a0\ufe0f You\'ve reached your force sub channel limit ({max_slots} slots).\n\n'
                f'\U0001f513 Base slots: {base_slots} (from your plan)\n'
                f'\U0001f517 Bonus slots: {bonus_slots} (from referrals)\n\n'
                f'Refer {refs_per_slot} people to unlock +1 slot!\n'
                f'Use /start to get your referral link.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\U0001f517 Referral Program', callback_data='referral_info')],
                    [InlineKeyboardButton('\U0001f519 Back', callback_data=f'force_sub_settings:{chat_id}')]
                ])
            )
            return ConversationHandler.END
        
        current_channels.append(new_entry)
        
        await db.update_channel_setting(chat_id, 'force_subscribe_channels', json.dumps(current_channels))
        
        if not channel.get('force_subscribe_enabled'):
            await db.update_channel_setting(chat_id, 'force_subscribe_enabled', True)
        
        await update.message.reply_text(
            f'\u2705 Added {chat_info.title} to force subscribe list!\n\n'
            f'Users will now need to join {chat_info.title} before their request is approved.\n\n'
            'Use /dashboard to manage settings.'
        )
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f'Error in force sub channel input: {e}')
        await update.message.reply_text(f'\u274c Error: {e}\nPlease try again or /cancel')
        return FORCE_SUB_INPUT

async def start_add_force_sub_channel(update, context, chat_id):
    """Start the conversation to add a force sub channel."""
    query = update.callback_query
    context.user_data['force_sub_target_channel'] = chat_id
    await query.edit_message_text(
        '\U0001f512 ADD FORCE SUBSCRIBE CHANNEL\n\n'
        'Send the channel username or ID that users must join:\n\n'
        'Examples:\n'
        '\u2022 @mychannel\n'
        '\u2022 -1001234567890\n\n'
        'Send /cancel to abort.'
    )
    return FORCE_SUB_INPUT


DEFAULT_FSUB_INPUT = 101

async def start_add_default_fsub_channel(update, context):
    """Start the conversation to add a default force sub channel for all channels."""
    query = update.callback_query
    context.user_data['adding_default_fsub'] = True
    await query.edit_message_text(
        '\U0001f512 ADD DEFAULT FORCE SUB CHANNEL\n\n'
        'This channel will be added to ALL your channels that have force sub enabled.\n\n'
        'Send the channel username or ID:\n\n'
        'Examples:\n'
        '\u2022 @mychannel\n'
        '\u2022 -1001234567890\n\n'
        'Send /cancel to abort.'
    )
    return DEFAULT_FSUB_INPUT

async def handle_default_fsub_channel_input(update, context):
    """Handle channel username/ID input for default force subscribe setup."""
    import json as _json
    text = update.message.text.strip()
    db = context.application.bot_data.get('db')
    user_id = update.effective_user.id

    try:
        if text.startswith('@'):
            channel_username = text
        elif text.startswith('-100'):
            channel_username = int(text)
        elif text.isdigit():
            channel_username = int('-100' + text)
        else:
            channel_username = '@' + text

        try:
            chat_info = await context.bot.get_chat(channel_username)
        except Exception:
            await update.message.reply_text(
                '\u274c Could not find that channel. Make sure:\n'
                '1. The channel/group exists\n'
                '2. The bot is a member of that channel\n'
                '3. You entered the correct username or ID\n\n'
                'Send the channel username (e.g. @mychannel) or /cancel'
            )
            return DEFAULT_FSUB_INPUT

        # Verify bot is admin in the force sub channel
        try:
            bot_member = await context.bot.get_chat_member(chat_info.id, context.bot.id)
            if bot_member.status not in ('administrator', 'creator'):
                await update.message.reply_text(
                    f'\u26a0\ufe0f I need to be an admin in {chat_info.title} '
                    f'to verify if users have joined it.\n\n'
                    f'Please add me as admin to {chat_info.title} first, then try again.\n\n'
                    f'Send the channel username again after adding me, or /cancel'
                )
                return DEFAULT_FSUB_INPUT
        except Exception:
            await update.message.reply_text(
                f'\u26a0\ufe0f I am not a member of {chat_info.title}.\n\n'
                f'Please add me as admin to that channel first.\n\n'
                f'Send the channel username again after adding me, or /cancel'
            )
            return DEFAULT_FSUB_INPUT

        # Get current default list
        default_fsub_raw = await db.get_platform_setting(f'owner_{user_id}_default_fsub_channels', '[]')
        try:
            default_fsub = _json.loads(default_fsub_raw) if isinstance(default_fsub_raw, str) else (default_fsub_raw or [])
        except Exception:
            default_fsub = []

        # Check for duplicates
        for ch in default_fsub:
            if isinstance(ch, dict) and ch.get('chat_id') == chat_info.id:
                await update.message.reply_text(f'\u26a0\ufe0f {chat_info.title} is already in the default force subscribe list!')
                return ConversationHandler.END

        new_entry = {
            'chat_id': chat_info.id,
            'title': chat_info.title,
            'username': chat_info.username or '',
            'url': f'https://t.me/{chat_info.username}' if chat_info.username else '',
        }
        default_fsub.append(new_entry)
        await db.set_platform_setting(f'owner_{user_id}_default_fsub_channels', _json.dumps(default_fsub))

        # Sync to all channels that have force sub enabled
        channels = await db.get_owner_channels(user_id)
        synced = 0
        for ch in (channels or []):
            full_ch = await db.get_channel(ch['chat_id'])
            if full_ch and full_ch.get('force_subscribe_enabled'):
                existing_raw = full_ch.get('force_subscribe_channels') or []
                if isinstance(existing_raw, str):
                    try:
                        existing = _json.loads(existing_raw)
                    except Exception:
                        existing = []
                else:
                    existing = existing_raw if isinstance(existing_raw, list) else []
                existing_ids = {c.get('chat_id') for c in existing if isinstance(c, dict)}
                if chat_info.id not in existing_ids:
                    existing.append(new_entry)
                    await db.update_channel_setting(ch['chat_id'], 'force_subscribe_channels', _json.dumps(existing))
                    synced += 1

        await update.message.reply_text(
            f'\u2705 Added {chat_info.title} as default force sub channel!\n\n'
            f'Synced to {synced} channel(s) with force sub enabled.\n\n'
            'Use /dashboard to manage settings.'
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f'Error in default force sub channel input: {e}')
        await update.message.reply_text(f'\u274c Error: {e}\nPlease try again or /cancel')
        return DEFAULT_FSUB_INPUT
