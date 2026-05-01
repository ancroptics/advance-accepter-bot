import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from utils.decorators import superadmin_only

logger = logging.getLogger(__name__)

async def dashboard_handler(update, context):
    await show_dashboard(update, context, edit=False)

async def show_dashboard(update, context, edit=False):
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    if not db:
        text = 'Bot is still initializing...'
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return
    owner = await db.get_owner(user_id)
    if not owner:
        text = ('\U0001f44b Welcome!\n\nTo get started, add this bot as admin to your channel.\n'
                'The bot will automatically detect it and set up management.')
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return
    channels = await db.get_owner_channels(user_id)
    tier = owner.get('tier', 'free').upper()
    text = f'\U0001f4ca GROWTH ENGINE DASHBOARD\n\n\U0001f44b Hey {update.effective_user.first_name}!\n\U0001f3f7\ufe0f Plan: {tier}\n\n\u2501\u2501\u2501 YOUR CHANNELS \u2501\u2501\u2501\n\n'
    buttons = []
    if channels:
        for ch in channels:
            auto = '\u2705 Auto: ON' if ch.get('auto_approve') else '\u23f8\ufe0f Auto: OFF'
            text += (f"\U0001f4e2 {ch['chat_title']}\n"
                     f"   \U0001f465 {ch.get('member_count', 0)} | \U0001f4cb {ch.get('pending_requests', 0)} pending\n"
                     f"   {auto}\n\n")        
    else:
        text += 'No channels yet. Add the bot as admin to a channel!\n\n'
    buttons.extend([
        [InlineKeyboardButton('\U0001f4e2 My Channels', callback_data='my_channels')],
        [InlineKeyboardButton('\U0001f4e9 Welcome Message', callback_data='default_welcome_msg'),
         InlineKeyboardButton('\U0001f512 Force Sub', callback_data='default_force_sub')],
    ])
    if user_id in config.SUPERADMIN_IDS:
        buttons.append([InlineKeyboardButton('\U0001f4e2 Broadcast', callback_data='broadcast'),
                        InlineKeyboardButton('\U0001f4ca Analytics', callback_data='analytics_overview')])
    else:
        buttons.append([InlineKeyboardButton('\U0001f4ca Analytics', callback_data='analytics_overview')])
    buttons.append([InlineKeyboardButton('\U0001f4dd Templates', callback_data='templates_menu'),
                    InlineKeyboardButton('\U0001f916 Auto Poster', callback_data='auto_poster_menu')])
    if user_id in config.SUPERADMIN_IDS:
        buttons.append([InlineKeyboardButton('🎨 Watermark', callback_data='default_watermark')])
    row4 = []
    row4.append(InlineKeyboardButton('\U0001f517 Referral', callback_data='referral_info'))
    if config.ENABLE_CROSS_PROMO:
        row4.append(InlineKeyboardButton('\U0001f504 Cross-Promo', callback_data='cross_promo_setup:0'))
    buttons.append(row4)
    row5 = []
    if config.ENABLE_CLONING:
        row5.append(InlineKeyboardButton('\U0001f9ec Clone Bot', callback_data='clone_bot_menu'))
    if config.ENABLE_PREMIUM:
        row5.append(InlineKeyboardButton('\U0001f48e Premium', callback_data='premium_info'))
    if row5:
        buttons.append(row5)
    buttons.extend([
        [InlineKeyboardButton('\U0001f4ac Support', callback_data='edit_support_overview'),
         InlineKeyboardButton('\u2699\ufe0f Settings', callback_data='settings'),
         InlineKeyboardButton('\u2753 Help', callback_data='help')],
    ])
    if user_id in config.SUPERADMIN_IDS:
        buttons.append([InlineKeyboardButton('\U0001f451 Superadmin Panel', callback_data='superadmin_panel')])

    total_channels = await db.get_total_channel_count()
    text += f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\U0001f4ca Platform: {total_channels} channels using Growth Engine'
    kb = InlineKeyboardMarkup(buttons)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb)

async def channels_handler(update, context):
    await show_dashboard(update, context, edit=False)

@superadmin_only
async def superadmin_handler(update, context):
    db = context.application.bot_data.get('db')
    stats = await db.get_platform_stats()
    text = ('\U0001f451 SUPERADMIN PANEL\n\n'
            f'\U0001f465 Channel Owners: {stats.get("total_owners", 0)}\n'
            f'\U0001f4e2 Total Channels: {stats.get("total_channels", 0)}\n'
            f'\U0001f9ec Active Clones: {stats.get("active_clones", 0)}\n'
            f'\U0001f464 End Users: {stats.get("total_users", 0)}\n'
            f'\U0001f48e Premium: {stats.get("premium_owners", 0)}\n')
    buttons = [
        [InlineKeyboardButton('\U0001f4ca Full Analytics', callback_data='sa_analytics')],
        [InlineKeyboardButton('\U0001f465 Manage Owners', callback_data='sa_manage_owners')],
        [InlineKeyboardButton('\U0001f4e2 Manage Channels', callback_data='sa_manage_channels')],
        [InlineKeyboardButton('\U0001f9ec Manage Clones', callback_data='sa_manage_clones')],
        [InlineKeyboardButton('\U0001f4e2 Platform Broadcast', callback_data='sa_platform_broadcast')],
        [InlineKeyboardButton('\U0001f48e Manage Subs', callback_data='sa_manage_subs')],
        [InlineKeyboardButton('\U0001f527 System Health', callback_data='sa_system_health')],
        [InlineKeyboardButton('\U0001f4ac Edit Support Username', callback_data='edit_support_username')],
        [InlineKeyboardButton('\U0001f4b3 Edit UPI ID', callback_data='sa_edit_upi')],
        [InlineKeyboardButton('\u2699\ufe0f Feature Toggles', callback_data='sa_feature_toggles')],
        [InlineKeyboardButton('\U0001f3a8 Watermark Settings', callback_data='sa_watermark_settings')],
        [InlineKeyboardButton('\U0001f4e3 Main Channel Reminder', callback_data='sa_main_channel')],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def sa_full_analytics(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    stats = await db.get_platform_stats()
    await query.edit_message_text(f'Full analytics: {stats}',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='superadmin_panel')]]))

async def sa_manage_owners(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    owners = await db.get_all_owners()
    text = '\U0001f465 Channel Owners:\n\n'
    for o in (owners or []):
        text += f"ID: {o['user_id']} | @{o.get('username', 'N/A')} | {o.get('tier', 'free')}\n"
    await query.edit_message_text(text or 'No owners.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='superadmin_panel')]]))

async def sa_manage_channels(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channels = await db.get_all_channels(limit=20)
    text = '\U0001f4e2 All Channels:\n\n'
    for ch in (channels or []):
        text += f"{ch['chat_title']} | Owner: {ch['owner_id']} | Active: {ch.get('is_active')}\n"
    await query.edit_message_text(text or 'No channels.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='superadmin_panel')]]))

async def sa_manage_clones(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    clones = await db.get_all_clones()
    text = '\U0001f9ec All Clones:\n\n'
    for cl in (clones or []):
        text += f"@{cl.get('bot_username', '?')} | Owner: {cl['owner_id']} | Active: {cl.get('is_active')}\n"
    await query.edit_message_text(text or 'No clones.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='superadmin_panel')]]))

async def sa_system_health(update, context):
    query = update.callback_query
    import psutil, os
    text = f'\U0001f527 System Health\n\nMemory: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB'
    await query.edit_message_text(text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='superadmin_panel')]]))

async def sa_platform_broadcast(update, context):
    query = update.callback_query
    await query.edit_message_text('Platform broadcast: Use /broadcast_all <message>',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='superadmin_panel')]]))

async def sa_edit_support_username(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    current = ''
    try:
        current = (await db.get_platform_setting('support_username', '')) or ''
    except Exception:
        current = ''
    if not current:
        current = getattr(config, 'SUPPORT_USERNAME', '') or ''
    display_current = current or 'Not set'
    context.user_data['awaiting_support_username'] = True
    await query.edit_message_text(
        f'\U0001f4ac EDIT SUPPORT USERNAME\n\n'
        f'Current: @{display_current}\n\n'
        f'This is the ONLY support contact shown to all users on the dashboard.\n'
        f'Send the new support username (without @).\n'
        f'Type /cancel to cancel.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='superadmin_panel')]])
    )

async def sa_manage_subscriptions(update, context):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    owners = await db.get_all_owners()
    text = '\U0001f48e MANAGE PREMIUM\n\nTap on a user to activate/deactivate premium:\n\n'
    buttons = []
    for o in (owners or []):
        tier = o.get('tier', 'free')
        tier_icon = '\U0001f48e' if tier == 'premium' else '\U0001f4bc' if tier == 'business' else '\u26aa'
        name = o.get('first_name', '') or o.get('username', '') or str(o['user_id'])
        label = f'{tier_icon} {name} [{tier.upper()}]'
        buttons.append([InlineKeyboardButton(label, callback_data=f"sa_activate_user:{o['user_id']}")])
    if not owners:
        text += 'No owners found.\n'
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='superadmin_panel')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_my_channels(update, context):
    """Show all channels owned by this user."""
    query = update.callback_query
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')
    if not db:
        await query.edit_message_text('Bot is still initializing...')
        return
    channels = await db.get_owner_channels(user_id)
    if not channels:
        text = '\U0001f4e2 MY CHANNELS\n\nNo channels connected yet!\n\nAdd this bot as admin to your channel and it will be detected automatically.'
        buttons = [[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return
    text = '\U0001f4e2 MY CHANNELS\n\n'
    buttons = []
    for ch in channels:
        status = '\u2705' if ch.get('is_active', True) else '\u274c'
        auto = 'Auto-approve ON' if ch.get('auto_approve') else 'Manual'
        text += f"{status} {ch['chat_title']}\n"
        text += f"   ID: {ch['chat_id']}\n"
        text += f"   Members: {ch.get('member_count', 0)} | Pending: {ch.get('pending_requests', 0)}\n"
        text += f"   Mode: {auto}\n\n"
        buttons.append([InlineKeyboardButton(f"\u2699\ufe0f {ch['chat_title'][:25]}", callback_data=f"manage_channel:{ch['chat_id']}")])
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def sa_main_channel(update, context):
    """Superadmin: configure the main channel reminder link."""
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in config.SUPERADMIN_IDS:
        await query.answer('Access denied', show_alert=True)
        return
    db = context.application.bot_data.get('db')
    current = await db.get_platform_setting('main_channel_link', '') if db else ''
    context.user_data['awaiting_main_channel_link'] = True
    text = (
        '\U0001f4e3 MAIN CHANNEL REMINDER\n\n'
        f'Current: {current or "Not set"}\n\n'
        'Send the main channel link (e.g. https://t.me/YourChannel or @YourChannel).\n'
        'Every channel owner will be reminded to join it when they /start the bot '
        'and after completing dashboard steps.\n\n'
        'Send "off" or "clear" to disable the reminder.\n'
        'Type /cancel to cancel.'
    )
    buttons = [
        [InlineKeyboardButton('\u274c Clear / Disable', callback_data='sa_clear_main_channel')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data='superadmin_panel')],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def sa_clear_main_channel(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in config.SUPERADMIN_IDS:
        await query.answer('Access denied', show_alert=True)
        return
    db = context.application.bot_data.get('db')
    context.user_data.pop('awaiting_main_channel_link', None)
    if db:
        await db.set_platform_setting('main_channel_link', '')
        try:
            await db.set_platform_setting('main_channel_chat_id', '')
        except Exception:
            pass
    await query.edit_message_text(
        '\u2705 Main channel reminder disabled.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='superadmin_panel')]])
    )


async def _resolve_main_channel_chat_id(context, link):
    """Try to resolve the channel to a chat_id using bot.get_chat. Returns int or None.
    Requires the bot to be a member/admin of the channel for private channels."""
    try:
        ref = link.strip()
        if ref.startswith('http'):
            if 't.me/+' in ref or '/joinchat/' in ref:
                return None
            ref = ref.split('t.me/', 1)[-1].strip('/').split('?')[0].split('/')[0]
            ref = f'@{ref}' if ref and not ref.startswith('@') else ref
        elif not ref.startswith('@') and not ref.lstrip('-').isdigit():
            ref = f'@{ref}'
        if ref.lstrip('-').isdigit():
            chat = await context.bot.get_chat(int(ref))
        else:
            chat = await context.bot.get_chat(ref)
        return chat.id if chat else None
    except Exception as e:
        logger.debug(f'resolve_main_channel_chat_id failed: {e}')
        return None


async def send_main_channel_reminder(context, user_id):
    """Send the main-channel join reminder to a channel owner. Skips silently if:
    - user is superadmin
    - not configured
    - user is already a member of the main channel (requires bot to be admin in it)
    Never raises."""
    try:
        if user_id in config.SUPERADMIN_IDS:
            return
        db = context.application.bot_data.get('db')
        if not db:
            return
        owner = await db.get_owner(user_id)
        if not owner:
            return
        link = await db.get_platform_setting('main_channel_link', '')
        if not link:
            return
        link = link.strip()
        if not link:
            return
        url = link
        if link.startswith('@'):
            url = f'https://t.me/{link[1:]}'
        elif not link.startswith('http'):
            url = f'https://t.me/{link.lstrip("/")}'

        cached_id = await db.get_platform_setting('main_channel_chat_id', '')
        chat_id = None
        if cached_id:
            try:
                chat_id = int(cached_id)
            except Exception:
                chat_id = None
        if chat_id is None:
            chat_id = await _resolve_main_channel_chat_id(context, link)
            if chat_id is not None:
                try:
                    await db.set_platform_setting('main_channel_chat_id', str(chat_id))
                except Exception:
                    pass

        if chat_id is not None:
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                status = getattr(member, 'status', '')
                if hasattr(status, 'value'):
                    status = status.value
                status = str(status).lower()
                if status in ('member', 'administrator', 'creator', 'owner', 'restricted'):
                    return
            except Exception as e:
                logger.warning(f'main_channel membership check failed (is bot admin in the channel?): {e}')
                return

        kb = InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f4e3 Join Main Channel', url=url)]])
        await context.bot.send_message(
            user_id,
            '\U0001f4e3 Reminder: please join our main channel for updates & announcements!\n\n'
            '\u2139\ufe0f This message will stop appearing once you join the channel.',
            reply_markup=kb
        )
    except Exception as e:
        logger.debug(f'main_channel_reminder skipped: {e}')
