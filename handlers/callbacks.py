import logging
import json
import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin_panel import show_dashboard

logger = logging.getLogger(__name__)


async def _show_feature_toggles(query, db):
    """Re-render the feature toggles menu without setting query.data."""
    import config as _cfg
    premium_status = '✅ ON' if _cfg.ENABLE_PREMIUM else '❌ OFF'
    clone_status = '✅ ON' if _cfg.ENABLE_CLONING else '❌ OFF'
    promo_status = '✅ ON' if _cfg.ENABLE_CROSS_PROMO else '❌ OFF'
    wm_raw = await db.get_platform_setting('global_watermark_enabled', 'false')
    wm_on = wm_raw.lower() == 'true' if isinstance(wm_raw, str) else bool(wm_raw)
    wm_status = '✅ ON' if wm_on else '❌ OFF'
    maint_raw = await db.get_platform_setting('MAINTENANCE_MODE', 'false')
    maint_on = maint_raw.lower() == 'true' if isinstance(maint_raw, str) else bool(maint_raw)
    maint_status = '🔴 ON' if maint_on else '✅ OFF'
    await query.edit_message_text(
        '⚙️ FEATURE TOGGLES\n\n'
        f'💎 Premium Gate: {premium_status}\n'
        f'🧬 Clone Bot Feature: {clone_status}\n'
        f'🔄 Cross Promotion: {promo_status}\n'
        f'🎨 Global Watermark: {wm_status}\n'
        f'🚧 Maintenance Mode: {maint_status}\n\n'
        'Toggle features on/off for the entire platform:\n'
        'ℹ️ Premium OFF = everyone uses bot freely!\n'
        '🚧 Maintenance ON = only superadmins can use the bot',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f'💎 Premium: {premium_status}', callback_data='sa_toggle_premium')],
            [InlineKeyboardButton(f'🧬 Clone Bot: {clone_status}', callback_data='sa_toggle_cloning')],
            [InlineKeyboardButton(f'🔄 Cross Promo: {promo_status}', callback_data='sa_toggle_cross_promo')],
            [InlineKeyboardButton(f'🎨 Watermark: {wm_status}', callback_data='sa_toggle_watermark')],
            [InlineKeyboardButton(f'🚧 Maintenance: {maint_status}', callback_data='sa_toggle_maintenance')],
            [InlineKeyboardButton('🔙 Back', callback_data='superadmin_panel')],
        ])
    )


async def _show_default_welcome_msg(update, context):
    """Re-show the default welcome message menu."""
    context.user_data['_reroute_data'] = 'default_welcome_msg'
    await button_callback(update, context)
    context.user_data.pop('_reroute_data', None)


async def _show_default_force_sub(update, context):
    """Re-show the default force sub menu."""
    context.user_data['_reroute_data'] = 'default_force_sub'
    await button_callback(update, context)
    context.user_data.pop('_reroute_data', None)


async def show_force_sub_settings(query, db, chat_id, origin='channel'):
    """Show force subscribe channel settings."""
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text('Channel not found.')
        return

    force_channels_raw = channel.get('force_subscribe_channels', '[]')
    if isinstance(force_channels_raw, str):
        try:
            force_channels = json.loads(force_channels_raw)
        except (ValueError, TypeError):
            force_channels = []
    elif isinstance(force_channels_raw, list):
        force_channels = force_channels_raw
    else:
        force_channels = []

    fsub_mode = channel.get('force_sub_mode', 'auto')
    fsub_timeout = channel.get('force_sub_timeout', 0)

    mode_labels = {'auto': 'Auto', 'manual': 'Manual', 'drip': 'Drip', 'all': 'All Modes'}
    timeout_label = f'{fsub_timeout}h' if fsub_timeout > 0 else 'Never'

    text = (f'\U0001f512 Force Subscribe Settings\n\n'
            f'Required channels ({len(force_channels)}):\n\n')
    buttons = []
    for ch in force_channels:
        title = ch.get('title', 'Unknown')
        text += f"\u2022 {title} ({ch.get('chat_id', '?')})\n"
        buttons.append([InlineKeyboardButton(
            f'\u274c Remove {title[:20]}',
            callback_data=f"remove_force_sub:{chat_id}:{ch.get('chat_id')}"
        )])

    if not force_channels:
        text += 'No required channels set.\n'

    text += (f'\n\u2501\u2501\u2501 Force Sub Mode \u2501\u2501\u2501\n'
             f'Current: {mode_labels.get(fsub_mode, fsub_mode)}\n\n'
             f'\u2022 Auto \u2014 Approve immediately after user joins all channels\n'
             f'\u2022 Manual \u2014 Send join links, admin approves manually\n'
             f'\u2022 Drip \u2014 After joining, queue for drip approval\n'
             f'\u2022 All \u2014 Apply force sub check to all approve modes\n')

    text += (f'\n\u23f0 Auto-Accept Timeout: {timeout_label}\n'
             f'(Accept even without joining after this time)\n')

    # Mode selection buttons
    mode_btns = []
    for m_val, m_label in [('auto', 'Auto'), ('manual', 'Manual'), ('drip', 'Drip'), ('all', 'All')]:
        icon = '\u2705 ' if fsub_mode == m_val else ''
        mode_btns.append(InlineKeyboardButton(
            f'{icon}{m_label}',
            callback_data=f'fsub_mode:{chat_id}:{m_val}'
        ))
    buttons.append(mode_btns)

    # Timeout buttons
    buttons.append([InlineKeyboardButton(
        f'\u23f0 Timeout: {timeout_label}',
        callback_data=f'fsub_timeout_menu:{chat_id}'
    )])

    buttons.append([InlineKeyboardButton('\u2795 Add Channel', callback_data=f'add_force_sub_ch:{chat_id}')])
    back_cb = 'default_force_sub' if origin == 'dashboard' else f'channel:{chat_id}'
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data=back_cb)])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            raise



async def show_welcome_settings(query, db, chat_id):
    """Show advanced welcome message settings (like force sub settings)."""
    user_id = query.from_user.id
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text('Channel not found.')
        return

    welcome_dm = channel.get('welcome_dm_enabled', True)
    welcome_msg = channel.get('welcome_message', '') or 'Welcome to {channel_name}! \U0001f389'
    media_type = channel.get('welcome_media_type', '')
    parse_mode = channel.get('welcome_parse_mode', 'HTML')

    # Get welcome channels (buttons)
    welcome_channels_raw = channel.get('welcome_buttons_json') or '[]'
    if isinstance(welcome_channels_raw, str):
        try:
            welcome_channels = json.loads(welcome_channels_raw)
        except (ValueError, TypeError):
            welcome_channels = []
    elif isinstance(welcome_channels_raw, list):
        welcome_channels = welcome_channels_raw
    else:
        welcome_channels = []

    status = '\U0001f7e2 Enabled' if welcome_dm else '\U0001f534 Disabled'

    text = (f'\U0001f4dd WELCOME MESSAGE SETTINGS\n\n'
            f'Status: {status}\n'
            f'Parse Mode: {parse_mode}\n')
    if media_type:
        text += f'Media: {media_type}\n'

    text += f'\n\u2501\u2501\u2501 Message Preview \u2501\u2501\u2501\n\n'

    # Show truncated preview
    preview = welcome_msg[:200]
    if len(welcome_msg) > 200:
        preview += '...'
    text += f'{preview}\n\n'

    text += f'\u2501\u2501\u2501 Channel Buttons ({len(welcome_channels)}) \u2501\u2501\u2501\n\n'

    buttons = []

    if welcome_channels:
        for i, ch in enumerate(welcome_channels, 1):
            title = ch.get('text', ch.get('title', 'Unknown'))
            text += f"{i}. {title} \u2705\n"
            buttons.append([InlineKeyboardButton(
                f'\u274c Remove {title[:20]}',
                callback_data=f"remove_welcome_ch:{chat_id}:{i-1}"
            )])
    else:
        text += 'No channel buttons configured.\n'
        text += '(Add channels to show as buttons in welcome DM)\n'

    text += (f'\n\u2501\u2501\u2501 Variables \u2501\u2501\u2501\n'
             f'{{first_name}}, {{username}}, {{channel_name}},\n'
             f'{{member_count}}, {{referral_link}}, {{coins}}, {{date}}\n')

    # Toggle button
    toggle_text = '\U0001f534 Disable' if welcome_dm else '\U0001f7e2 Enable'
    buttons.append([InlineKeyboardButton(toggle_text, callback_data=f'toggle_welcome_dm:{chat_id}')])

    # Edit & Preview buttons
    buttons.append([
        InlineKeyboardButton('\u270f\ufe0f Edit Message', callback_data=f'edit_welcome:{chat_id}'),
        InlineKeyboardButton('\U0001f440 Preview', callback_data=f'preview_welcome:{chat_id}'),
    ])

    # Add channel button - controlled by add_channel_btn_mode setting
    btn_mode = await db.get_platform_setting('add_channel_btn_mode', 'superadmin_only')
    show_add_btn = False
    if btn_mode == 'global':
        show_add_btn = True
    elif btn_mode == 'superadmin_only' and user_id in config.SUPERADMIN_IDS:
        show_add_btn = True
    if show_add_btn:
        buttons.append([InlineKeyboardButton('\u2795 Add Channel Button', callback_data=f'add_welcome_ch:{chat_id}')])

    # Media button
    buttons.append([InlineKeyboardButton('\U0001f4f7 Set Media', callback_data=f'set_welcome_media:{chat_id}')])

    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            raise


async def show_channel_settings(query, db, chat_id, user_id, context=None):
    """Show detailed settings for a specific channel."""
    channel = await db.get_channel(chat_id)
    if not channel or channel.get('owner_id') != user_id:
        await query.edit_message_text('Channel not found or access denied.')
        return

    title = channel.get('chat_title', 'Unknown')
    mode = channel.get('approve_mode', 'instant')
    auto = channel.get('auto_approve', True)
    welcome_dm = channel.get('welcome_dm_enabled', True)
    force_sub = channel.get('force_subscribe_enabled', False)
    # Get live pending count from Telegram API
    pending_db = 0
    try:
        if context:
            chat_info = await context.bot.get_chat(chat_id)
            pending_db = getattr(chat_info, 'pending_join_request_count', 0) or 0
        else:
            pending_db = await db.get_pending_count(chat_id)
    except Exception:
        pending_db = await db.get_pending_count(chat_id)
    pending = pending_db if pending_db is not None else channel.get('pending_requests', 0)
    support = channel.get('support_username', '')

    text = (f'\u2699\ufe0f Channel Settings: {title}\n\n'
            f'Mode: {mode}\n'
            f'Auto-approve: {"ON" if auto else "OFF"}\n'
            f'Welcome DM: {"ON" if welcome_dm else "OFF"}\n'
            f'Force Subscribe: {"ON" if force_sub else "OFF"}\n'
            f'Pending: {pending}\n')
    if support:
        text += f'Support: @{support}\n'

    buttons = []
    mode_labels = [('instant', 'Instant'), ('manual', 'Manual'), ('drip', 'Drip')]
    mode_btns = []
    for m_val, m_label in mode_labels:
        label = m_label + (' \u2705' if mode == m_val else '')
        mode_btns.append(InlineKeyboardButton(label, callback_data=f'set_mode:{chat_id}:{m_val}'))
    buttons.append(mode_btns)
    auto_icon = '\u2705' if auto else '\u274c'
    dm_icon = '\u2705' if welcome_dm else '\u274c'
    buttons.append([
        InlineKeyboardButton(f'{auto_icon} Auto-Approve', callback_data=f'toggle_auto_approve:{chat_id}'),
        InlineKeyboardButton(f'{dm_icon} Welcome DM', callback_data=f'toggle_welcome_dm:{chat_id}'),
    ])
    fsub_icon = '\u2705' if force_sub else '\u274c'
    buttons.append([
        InlineKeyboardButton(f'{fsub_icon} Force Sub', callback_data=f'toggle_force_sub:{chat_id}'),
        InlineKeyboardButton('\U0001f4dd Welcome Msg', callback_data=f'welcome_settings:{chat_id}'),
    ])
    if force_sub:
        buttons.append([InlineKeyboardButton('\u2699\ufe0f Force Sub Settings', callback_data=f'force_sub_settings:{chat_id}')])
    buttons.append([
        InlineKeyboardButton(f'\U0001f4cb Pending ({pending})', callback_data=f'pending_requests:{chat_id}'),
        InlineKeyboardButton('\U0001f504 Sync Pending', callback_data=f'sync_pending:{chat_id}'),
    ])
    if pending > 0:
        buttons.append([
            InlineKeyboardButton(f'\u2705 Approve All ({pending})', callback_data=f'batch_approve:{chat_id}'),
            InlineKeyboardButton('\u274c Decline All', callback_data=f'decline_all:{chat_id}'),
        ])
        if mode == 'drip':
            buttons.append([InlineKeyboardButton('\U0001f4a7 Drip Settings', callback_data=f'drip_settings:{chat_id}')])
    wm_row = []
    if user_id in config.SUPERADMIN_IDS:
        wm_row.append(InlineKeyboardButton('\U0001f3a8 Watermark', callback_data=f'watermark_settings:{chat_id}'))
    if config.ENABLE_CROSS_PROMO:
        wm_row.append(InlineKeyboardButton('\U0001f504 Cross Promo', callback_data=f'cross_promo_setup:{chat_id}'))
    if wm_row:
        buttons.append(wm_row)
    buttons.append([
        InlineKeyboardButton('\U0001f4ac Support Username', callback_data=f'edit_support_username:{chat_id}'),
        InlineKeyboardButton('\U0001f4ca Stats', callback_data=f'channel_stats:{chat_id}'),
    ])
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='my_channels')])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            raise


async def show_pending_requests(query, context, db, chat_id, user_id):
    """Show list of pending join requests for a channel."""
    channel = await db.get_channel(chat_id)
    if not channel or channel.get('owner_id') != user_id:
        await query.edit_message_text('Channel not found or access denied.')
        return

    # Try to get actual pending count from Telegram API
    telegram_pending = 0
    try:
        chat_info = await context.bot.get_chat(chat_id)
        telegram_pending = getattr(chat_info, 'pending_join_request_count', 0) or 0
    except Exception as e:
        logger.warning(f'Could not get Telegram pending count for {chat_id}: {e}')

    pending = await db.get_pending_requests(chat_id, limit=20)
    db_pending_count = await db.get_pending_count(chat_id)

    title = channel.get('chat_title', 'Unknown')
    pending_count = max(telegram_pending, db_pending_count)
    untracked = max(0, telegram_pending - db_pending_count)

    if telegram_pending == 0 and db_pending_count == 0:
        text = f'\U0001f4cb Pending Requests for {title}\n\nNo pending requests at the moment.'
        buttons = [
            [InlineKeyboardButton('\U0001f504 Refresh', callback_data=f'pending_requests:{chat_id}')],
            [InlineKeyboardButton('\U0001f519 Back', callback_data=f'channel:{chat_id}')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    text = f'\U0001f4cb Pending Requests for {title}\n\n'
    text += f'\U0001f4ca Telegram reports: {telegram_pending} pending\n'
    text += f'\U0001f4be Tracked in bot: {db_pending_count}\n'
    if untracked > 0:
        text += f'\u26a0\ufe0f Untracked (old): {untracked}\n'
        text += f'\n\U0001f4a1 {untracked} old request(s) were made before the bot was added.\n'
        text += 'To approve old requests: Telegram app \u2192 Channel \u2192 Join Requests\n'
        text += '\u2705 All new requests are tracked automatically!\n'
    text += f'\nTotal: {pending_count}\n\n'
    buttons = []
    for req in pending:
        name = req.get('first_name', 'Unknown')
        uname = f" (@{req.get('username')})" if req.get('username') else ""
        uid = req.get('user_id')
        text += f"\u2022 {name}{uname} (ID: {uid})\n"
        buttons.append([
            InlineKeyboardButton(f'\u2705 {name[:15]}', callback_data=f'approve_one:{chat_id}:{uid}'),
            InlineKeyboardButton(f'\u274c {name[:15]}', callback_data=f'decline_one:{chat_id}:{uid}'),
        ])

    if pending_count > 20:
        text += f'\n... and {pending_count - 20} more'

    if pending_count > 0:
        buttons.append([
            InlineKeyboardButton(f'\u2705 Approve All ({pending_count})', callback_data=f'batch_approve:{chat_id}'),
            InlineKeyboardButton('\u274c Decline All', callback_data=f'decline_all:{chat_id}'),
        ])
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data=f'channel:{chat_id}')])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query handler for all button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')

    if not db:
        await query.edit_message_text('Database not available. Try again later.')
        return

    try:
        if data == 'superadmin_panel':
            from handlers.admin_panel import superadmin_handler
            # superadmin_handler expects update.message, but we have callback_query
            # Rebuild the superadmin panel inline
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.edit_message_text('Access denied.')
                return
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
                [InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


        elif data == 'edit_support_overview':
            owner_username = query.from_user.username or 'Not set'
            support_username = config.SUPPORT_USERNAME or owner_username
            text = ('\U0001f4ac SUPPORT\n\n'
                    'For help and queries, contact the owner:\n\n'
                    f'\U0001f464 @{support_username}\n\n'
                    'This username is shown to users who need assistance.')
            buttons = [[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


        elif data == 'my_channels':
            await show_my_channels(query, db, user_id)

        elif data == 'admin_panel' or data == 'dashboard':
            await show_dashboard(update, context, edit=True)

        elif data == 'default_welcome_msg':
            # Advanced welcome message settings - one message, choose channels
            channels = await db.get_owner_channels(user_id)
            ch_count = len(channels) if channels else 0

            # Get current default welcome message
            default_msg = None
            default_media_type = None
            default_buttons_json = '[]'
            default_parse_mode = 'HTML'
            try:
                row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_default_welcome'
                )
                if row:
                    default_msg = row['value']
                media_row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_welcome_media_type'
                )
                if media_row:
                    default_media_type = media_row['value']
                btns_row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_welcome_buttons'
                )
                if btns_row:
                    default_buttons_json = btns_row['value']
                pm_row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_welcome_parse_mode'
                )
                if pm_row:
                    default_parse_mode = pm_row['value']
            except Exception:
                pass

            if not default_msg:
                if channels:
                    ch = await db.get_channel(channels[0]['chat_id'])
                    default_msg = ch.get('welcome_message', '') if ch else ''

            current = default_msg or 'Welcome to {channel_name}! \U0001f389'

            enabled_count = 0
            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                if full_ch and full_ch.get('welcome_dm_enabled'):
                    enabled_count += 1

            all_enabled = enabled_count == ch_count and ch_count > 0
            status = '\U0001f7e2 Enabled' if all_enabled else ('\U0001f7e1 Partial' if enabled_count > 0 else '\U0001f534 Disabled')

            try:
                welcome_btns = json.loads(default_buttons_json) if isinstance(default_buttons_json, str) else default_buttons_json
            except (ValueError, TypeError):
                welcome_btns = []
            if not isinstance(welcome_btns, list):
                welcome_btns = []

            text = (
                f'\U0001f4e9 WELCOME MESSAGE SETTINGS\n\n'
                f'Status: {status} ({enabled_count}/{ch_count} channels)\n'
                f'Parse Mode: {default_parse_mode}\n'
            )
            if default_media_type:
                text += f'Media: {default_media_type} \u2705\n'

            text += f'\n\u2501\u2501\u2501 Message Preview \u2501\u2501\u2501\n\n'
            preview = current[:300]
            if len(current) > 300:
                preview += '...'
            text += f'{preview}\n\n'

            if welcome_btns:
                text += f'\u2501\u2501\u2501 Channel Buttons ({len(welcome_btns)}) \u2501\u2501\u2501\n\n'
                for i, btn in enumerate(welcome_btns, 1):
                    title = btn.get('text', btn.get('title', 'Unknown'))
                    text += f'{i}. {title} \u2705\n'
                text += '\n'

            text += (
                '\u2501\u2501\u2501 Your Channels \u2501\u2501\u2501\n\n'
                'Toggle which channels display this welcome message:\n'
            )

            buttons = []
            toggle_all_text = '\U0001f534 Disable All' if all_enabled else '\U0001f7e2 Enable All'
            buttons.append([InlineKeyboardButton(toggle_all_text, callback_data='toggle_all_welcome')])

            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                dm_on = full_ch.get('welcome_dm_enabled', False) if full_ch else False
                icon = '\u2705' if dm_on else '\u274c'
                title = ch.get('chat_title', 'Unknown')[:25]
                buttons.append([
                    InlineKeyboardButton(f'{icon} {title}', callback_data=f'toggle_welcome_channel:{ch["chat_id"]}'),
                ])

            if not channels:
                text += '\nNo channels connected yet!\n'

            text += (
                '\n\u2501\u2501\u2501 Variables \u2501\u2501\u2501\n'
                '{first_name}, {username}, {channel_name},\n'
                '{member_count}, {referral_link}, {coins}, {date}\n'
            )

            buttons.append([
                InlineKeyboardButton('\u270f\ufe0f Edit Message', callback_data='edit_default_welcome'),
                InlineKeyboardButton('\U0001f440 Preview', callback_data='preview_default_welcome'),
            ])
            btn_mode = await db.get_platform_setting('add_channel_btn_mode', 'superadmin_only')
            show_add_btn = False
            if btn_mode == 'global':
                show_add_btn = True
            elif btn_mode == 'superadmin_only' and user_id in config.SUPERADMIN_IDS:
                show_add_btn = True
            if show_add_btn:
                buttons.append([
                    InlineKeyboardButton('\u2795 Add Channel Button', callback_data='add_default_welcome_btn'),
                ])
            if user_id in config.SUPERADMIN_IDS:
                mode_labels = {'superadmin_only': '🔒 Superadmin Only', 'global': '🌐 Global (All Users)'}
                current_label = mode_labels.get(btn_mode, btn_mode)
                buttons.append([
                    InlineKeyboardButton(f'📌 Channel Btn: {current_label}', callback_data='toggle_add_channel_btn_mode'),
                ])
            for i, btn in enumerate(welcome_btns):
                title = btn.get('text', btn.get('title', 'Unknown'))[:20]
                buttons.append([InlineKeyboardButton(f'\u274c Remove {title}', callback_data=f'remove_default_welcome_btn:{i}')])
            buttons.append([
                InlineKeyboardButton('\U0001f4f7 Set Media', callback_data='set_default_welcome_media'),
            ])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )


        elif data == 'toggle_all_welcome':
            channels = await db.get_owner_channels(user_id)
            enabled_count = 0
            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                if full_ch and full_ch.get('welcome_dm_enabled'):
                    enabled_count += 1
            all_enabled = enabled_count == len(channels) and len(channels) > 0
            new_state = not all_enabled
            for ch in (channels or []):
                await db.update_channel_setting(ch['chat_id'], 'welcome_dm_enabled', new_state)
                if new_state:
                    try:
                        row = await db.pool.fetchrow(
                            "SELECT value FROM platform_settings WHERE key = $1",
                            f'owner_{user_id}_default_welcome'
                        )
                        if row and row['value']:
                            await db.update_channel_setting(ch['chat_id'], 'welcome_message', row['value'])
                        btns_row = await db.pool.fetchrow(
                            "SELECT value FROM platform_settings WHERE key = $1",
                            f'owner_{user_id}_welcome_buttons'
                        )
                        if btns_row:
                            await db.update_channel_setting(ch['chat_id'], 'welcome_buttons_json', btns_row['value'])
                    except Exception:
                        pass
            await query.answer(f'Welcome DM {"enabled" if new_state else "disabled"} for all channels!')
            await _show_default_welcome_msg(update, context)

        elif data.startswith('toggle_welcome_channel:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current = channel.get('welcome_dm_enabled', False) if channel else False
            new_state = not current
            await db.update_channel_setting(chat_id, 'welcome_dm_enabled', new_state)
            if new_state:
                try:
                    row = await db.pool.fetchrow(
                        "SELECT value FROM platform_settings WHERE key = $1",
                        f'owner_{user_id}_default_welcome'
                    )
                    if row and row['value']:
                        await db.update_channel_setting(chat_id, 'welcome_message', row['value'])
                    btns_row = await db.pool.fetchrow(
                        "SELECT value FROM platform_settings WHERE key = $1",
                        f'owner_{user_id}_welcome_buttons'
                    )
                    if btns_row:
                        await db.update_channel_setting(chat_id, 'welcome_buttons_json', btns_row['value'])
                except Exception:
                    pass
            await query.answer(f'Welcome DM {"enabled" if new_state else "disabled"}!')
            await _show_default_welcome_msg(update, context)

        elif data == 'edit_default_welcome':
            default_msg = None
            try:
                row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_default_welcome'
                )
                if row:
                    default_msg = row['value']
            except Exception:
                pass
            current = default_msg or 'Not set'
            context.user_data['editing_default_welcome'] = True
            await query.edit_message_text(
                f'\U0001f4e9 EDIT WELCOME MESSAGE\n\n'
                f'\u2501\u2501\u2501 Current Message \u2501\u2501\u2501\n\n'
                f'{current}\n\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n'
                f'Send me the new welcome message.\n\n'
                f'Available variables:\n'
                f'{{first_name}} - User first name\n'
                f'{{username}} - Username\n'
                f'{{channel_name}} - Channel name\n'
                f'{{member_count}} - Member count\n'
                f'{{referral_link}} - Referral link\n'
                f'{{coins}} - User coins\n'
                f'{{date}} - Current date\n\n'
                f'Send /cancel to cancel.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('Cancel', callback_data='default_welcome_msg')]
                ])
            )

        elif data == 'preview_default_welcome':
            default_msg = None
            try:
                row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_default_welcome'
                )
                if row:
                    default_msg = row['value']
            except Exception:
                pass
            msg = default_msg or 'Welcome to {channel_name}! \U0001f389'
            preview = msg.replace('{first_name}', query.from_user.first_name or 'there')
            preview = preview.replace('{last_name}', query.from_user.last_name or '')
            preview = preview.replace('{username}', f'@{query.from_user.username}' if query.from_user.username else 'there')
            preview = preview.replace('{user_id}', str(query.from_user.id))
            preview = preview.replace('{channel_name}', 'My Channel')
            preview = preview.replace('{channel_username}', '@mychannel')
            preview = preview.replace('{member_count}', '1000')
            preview = preview.replace('{coins}', '0')
            from datetime import datetime
            preview = preview.replace('{date}', datetime.now().strftime('%Y-%m-%d'))
            preview = preview.replace('{referral_link}', f'https://t.me/bot?start=ref_{query.from_user.id}')
            try:
                btns_row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_welcome_buttons'
                )
                welcome_btns = json.loads(btns_row['value']) if btns_row else []
            except Exception:
                welcome_btns = []
            btn_rows = []
            for btn in welcome_btns:
                btn_rows.append([InlineKeyboardButton(btn.get('text', 'Link'), url=btn.get('url', 'https://t.me'))])
            btn_rows.append([InlineKeyboardButton('\U0001f519 Back', callback_data='default_welcome_msg')])
            text = f"\U0001f440 WELCOME MESSAGE PREVIEW\n\n{preview}\n\n(This is how the welcome DM will look)"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btn_rows))

        elif data.startswith('remove_default_welcome_btn:'):
            remove_idx = int(data.split(':')[1])
            try:
                btns_row = await db.pool.fetchrow(
                    "SELECT value FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_welcome_buttons'
                )
                welcome_btns = json.loads(btns_row['value']) if btns_row else []
            except Exception:
                welcome_btns = []
            if 0 <= remove_idx < len(welcome_btns):
                removed = welcome_btns.pop(remove_idx)
                await db.pool.execute(
                    "INSERT INTO platform_settings (key, value) VALUES ($1, $2) "
                    "ON CONFLICT (key) DO UPDATE SET value = $2",
                    f'owner_{user_id}_welcome_buttons', json.dumps(welcome_btns)
                )
                channels = await db.get_owner_channels(user_id)
                for ch in (channels or []):
                    full_ch = await db.get_channel(ch['chat_id'])
                    if full_ch and full_ch.get('welcome_dm_enabled'):
                        await db.update_channel_setting(ch['chat_id'], 'welcome_buttons_json', json.dumps(welcome_btns))
                await query.answer(f"Removed {removed.get('text', 'channel')}", show_alert=True)
            await _show_default_welcome_msg(update, context)

        elif data == 'set_default_welcome_media':
            context.user_data['awaiting_default_welcome_media'] = True
            await query.edit_message_text(
                '\U0001f4f7 SET WELCOME MEDIA\n\n'
                'Send me a photo, video, GIF, or document to attach to your welcome message.\n\n'
                'Or send "none" to remove current media.\n\n'
                'Send /cancel to cancel.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\u274c Remove Media', callback_data='remove_default_welcome_media')],
                    [InlineKeyboardButton('Cancel', callback_data='default_welcome_msg')]
                ])
            )

        elif data == 'remove_default_welcome_media':
            try:
                await db.pool.execute(
                    "DELETE FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_welcome_media_type'
                )
                await db.pool.execute(
                    "DELETE FROM platform_settings WHERE key = $1",
                    f'owner_{user_id}_welcome_media_file_id'
                )
                channels = await db.get_owner_channels(user_id)
                for ch in (channels or []):
                    full_ch = await db.get_channel(ch['chat_id'])
                    if full_ch and full_ch.get('welcome_dm_enabled'):
                        await db.update_channel_setting(ch['chat_id'], 'welcome_media_type', '')
                        await db.update_channel_setting(ch['chat_id'], 'welcome_media_file_id', '')
            except Exception:
                pass
            await query.answer('Media removed!', show_alert=True)
            await _show_default_welcome_msg(update, context)


        elif data == 'default_force_sub':
            # Show force sub settings that apply to all channels
            channels = await db.get_owner_channels(user_id)
            ch_count = len(channels) if channels else 0
            enabled_count = 0
            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                if full_ch and full_ch.get('force_subscribe_enabled'):
                    enabled_count += 1

            # Get dashboard-level default force sub channels
            default_fsub_raw = await db.get_platform_setting(f'owner_{user_id}_default_fsub_channels', '[]')
            try:
                default_fsub = json.loads(default_fsub_raw) if isinstance(default_fsub_raw, str) else (default_fsub_raw or [])
            except Exception:
                default_fsub = []

            all_enabled = enabled_count == ch_count and ch_count > 0
            status = '\U0001f7e2 Enabled' if all_enabled else ('\U0001f7e1 Partial' if enabled_count > 0 else '\U0001f534 Disabled')
            text = (
                f'\U0001f512 FORCE SUBSCRIBE (All Channels)\n\n'
                f'Status: {status} ({enabled_count}/{ch_count} channels)\n\n'
            )
            if default_fsub:
                text += '\U0001f4cb Default Required Channels (applied to all toggled-on):\n'
                for i, fc in enumerate(default_fsub[:10], 1):
                    title = fc.get('title', 'Unknown') if isinstance(fc, dict) else str(fc)
                    text += f'{i}. {title} \u2705\n'
                text += '\n'
            else:
                text += '\U0001f4cb Default Required Channels: None\n\n'
            text += (
                'Add channels here to apply them to ALL toggled-on channels.\n'
                'Use per-channel \u2699\ufe0f Settings to add channel-specific ones.'
            )
            toggle_text = '\U0001f534 Disable All' if all_enabled else '\U0001f7e2 Enable All'
            buttons = [
                [InlineKeyboardButton(toggle_text, callback_data='toggle_default_force_sub')],
                [InlineKeyboardButton('\u2795 Add Default Channel', callback_data='add_default_fsub_ch')],
            ]
            if default_fsub:
                buttons.append([InlineKeyboardButton('\U0001f5d1 Remove Default Channel', callback_data='remove_default_fsub_menu')])
            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                fs_on = full_ch.get('force_subscribe_enabled', False) if full_ch else False
                icon = '\u2705' if fs_on else '\u274c'
                title = ch.get('chat_title', 'Unknown')[:20]
                buttons.append([
                    InlineKeyboardButton(f'{icon} {title}', callback_data=f'toggle_force_sub:{ch["chat_id"]}'),
                    InlineKeyboardButton('\u2699\ufe0f Settings', callback_data=f'force_sub_settings:{ch["chat_id"]}:dashboard'),
                ])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data == 'toggle_default_force_sub':
            # Toggle force sub for ALL channels
            channels = await db.get_owner_channels(user_id)
            if not channels:
                await query.answer('No channels found!', show_alert=True)
                return
            all_enabled = True
            for ch in channels:
                full_ch = await db.get_channel(ch['chat_id'])
                if not full_ch or not full_ch.get('force_subscribe_enabled'):
                    all_enabled = False
                    break
            new_state = not all_enabled
            # Get default force sub channels
            default_fsub_raw = await db.get_platform_setting(f'owner_{user_id}_default_fsub_channels', '[]')
            try:
                default_fsub = json.loads(default_fsub_raw) if isinstance(default_fsub_raw, str) else (default_fsub_raw or [])
            except Exception:
                default_fsub = []
            for ch in channels:
                await db.update_channel_setting(ch['chat_id'], 'force_subscribe_enabled', new_state)
                # When enabling, sync default channels into each channel
                if new_state and default_fsub:
                    full_ch = await db.get_channel(ch['chat_id'])
                    existing_raw = full_ch.get('force_subscribe_channels') or [] if full_ch else []
                    if isinstance(existing_raw, str):
                        try:
                            existing = json.loads(existing_raw)
                        except Exception:
                            existing = []
                    else:
                        existing = existing_raw if isinstance(existing_raw, list) else []
                    existing_ids = {c.get('chat_id') for c in existing if isinstance(c, dict)}
                    merged = list(existing)
                    for dfc in default_fsub:
                        if isinstance(dfc, dict) and dfc.get('chat_id') not in existing_ids:
                            merged.append(dfc)
                    await db.update_channel_setting(ch['chat_id'], 'force_subscribe_channels', json.dumps(merged))
            state_text = 'enabled' if new_state else 'disabled'
            await query.answer(f'Force subscribe {state_text} for all {len(channels)} channels!', show_alert=True)
            await _show_default_force_sub(update, context)

        elif data == 'remove_default_fsub_menu':
            default_fsub_raw = await db.get_platform_setting(f'owner_{user_id}_default_fsub_channels', '[]')
            try:
                default_fsub = json.loads(default_fsub_raw) if isinstance(default_fsub_raw, str) else (default_fsub_raw or [])
            except Exception:
                default_fsub = []
            if not default_fsub:
                await query.answer('No default channels to remove!', show_alert=True)
                return
            buttons = []
            for fc in default_fsub:
                title = fc.get('title', 'Unknown') if isinstance(fc, dict) else str(fc)
                fc_id = fc.get('chat_id', 0) if isinstance(fc, dict) else 0
                buttons.append([InlineKeyboardButton(f'\u274c {title}', callback_data=f'remove_default_fsub:{fc_id}')])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='default_force_sub')])
            await query.edit_message_text(
                '\U0001f5d1 Remove Default Force Sub Channel\n\nSelect a channel to remove:',
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data.startswith('remove_default_fsub:'):
            remove_id = int(data.split(':')[1])
            default_fsub_raw = await db.get_platform_setting(f'owner_{user_id}_default_fsub_channels', '[]')
            try:
                default_fsub = json.loads(default_fsub_raw) if isinstance(default_fsub_raw, str) else (default_fsub_raw or [])
            except Exception:
                default_fsub = []
            removed_title = None
            new_list = []
            for fc in default_fsub:
                if isinstance(fc, dict) and fc.get('chat_id') == remove_id:
                    removed_title = fc.get('title', 'Unknown')
                else:
                    new_list.append(fc)
            await db.set_platform_setting(f'owner_{user_id}_default_fsub_channels', json.dumps(new_list))
            # Also remove from all channels that have force sub enabled
            channels = await db.get_owner_channels(user_id)
            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                if full_ch and full_ch.get('force_subscribe_enabled'):
                    ch_fsub_raw = full_ch.get('force_subscribe_channels') or []
                    if isinstance(ch_fsub_raw, str):
                        try:
                            ch_fsub = json.loads(ch_fsub_raw)
                        except Exception:
                            ch_fsub = []
                    else:
                        ch_fsub = ch_fsub_raw if isinstance(ch_fsub_raw, list) else []
                    filtered = [c for c in ch_fsub if not (isinstance(c, dict) and c.get('chat_id') == remove_id)]
                    if len(filtered) != len(ch_fsub):
                        await db.update_channel_setting(ch['chat_id'], 'force_subscribe_channels', json.dumps(filtered))
            await query.answer(f'Removed {removed_title or "channel"} from all channels!', show_alert=True)
            await _show_default_force_sub(update, context)

        elif data == 'close':
            await query.delete_message()

        elif data.startswith('channel:') or data.startswith('manage_channel:'):
            chat_id = int(data.split(':')[1])
            await show_channel_settings(query, db, chat_id, user_id, context)

        elif data.startswith('back_channels'):
            await show_my_channels(query, db, user_id)

        elif data.startswith('set_mode:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            mode = parts[2]
            channel = await db.get_channel(chat_id)
            current_mode = channel.get('approve_mode', 'instant') if channel else ''
            if current_mode == mode:
                await query.answer(f'Already set to {mode}', show_alert=False)
                return
            await db.update_channel_setting(chat_id, 'approve_mode', mode)
            await query.answer(f'Mode set to {mode}', show_alert=True)
            await show_channel_settings(query, db, chat_id, user_id, context)

        elif data.startswith('toggle_welcome_dm:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current = channel.get('welcome_dm_enabled', True)
            await db.update_channel_setting(chat_id, 'welcome_dm_enabled', not current)
            await show_welcome_settings(query, db, chat_id)

        elif data.startswith('toggle_auto_approve:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current = channel.get('auto_approve', True)
            await db.update_channel_setting(chat_id, 'auto_approve', not current)
            await show_channel_settings(query, db, chat_id, user_id, context)

        elif data.startswith('toggle_force_sub:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current = channel.get('force_subscribe_enabled', False)
            new_state = not current
            await db.update_channel_setting(chat_id, 'force_subscribe_enabled', new_state)
            # When enabling, sync default force sub channels into this channel
            if new_state:
                default_fsub_raw = await db.get_platform_setting(f'owner_{user_id}_default_fsub_channels', '[]')
                try:
                    default_fsub = json.loads(default_fsub_raw) if isinstance(default_fsub_raw, str) else (default_fsub_raw or [])
                except Exception:
                    default_fsub = []
                if default_fsub:
                    existing_raw = channel.get('force_subscribe_channels') or []
                    if isinstance(existing_raw, str):
                        try:
                            existing = json.loads(existing_raw)
                        except Exception:
                            existing = []
                    else:
                        existing = existing_raw if isinstance(existing_raw, list) else []
                    existing_ids = {c.get('chat_id') for c in existing if isinstance(c, dict)}
                    merged = list(existing)
                    for dfc in default_fsub:
                        if isinstance(dfc, dict) and dfc.get('chat_id') not in existing_ids:
                            merged.append(dfc)
                    await db.update_channel_setting(chat_id, 'force_subscribe_channels', json.dumps(merged))
            await show_channel_settings(query, db, chat_id, user_id, context)

        elif data.startswith('edit_welcome:'):
            chat_id = int(data.split(':')[1])
            context.user_data['editing_welcome_for'] = chat_id
            channel = await db.get_channel(chat_id)
            current_msg = channel.get('welcome_message', 'Welcome to {channel_name}! \U0001f389') if channel else 'Not set'
            await query.edit_message_text(
                '\U0001f4dd EDIT WELCOME MESSAGE\n\n'
                '\u2501\u2501\u2501 Current Message \u2501\u2501\u2501\n\n'
                f'{current_msg}\n\n'
                '\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n'
                'Send me the new welcome message.\n\n'
                'Available variables:\n'
                '{first_name} - User first name\n'
                '{last_name} - User last name\n'
                '{username} - Username\n'
                '{user_id} - User ID\n'
                '{channel_name} - Channel name\n'
                '{channel_username} - Channel @username\n'
                '{member_count} - Member count\n'
                '{coins} - User coins\n'
                '{referral_link} - Referral link\n'
                '{date} - Current date\n\n'
                'Send /cancel to cancel.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('Cancel', callback_data=f'channel:{chat_id}')]
                ])
            )

        elif data.startswith('edit_support_username:'):
            chat_id = int(data.split(':')[1])
            context.user_data['editing_support_username_for'] = chat_id
            await query.edit_message_text(
                'Send me the support username (without @).\n'
                'This will be shown to users who need help.\n\n'
                'Send /cancel to cancel.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('Cancel', callback_data=f'channel:{chat_id}')]
                ])
            )

        elif data.startswith('welcome_settings:'):
            chat_id = int(data.split(':')[1])
            await show_welcome_settings(query, db, chat_id)

        elif data.startswith('remove_welcome_ch:'):
            parts = data.split(':')
            parent_chat_id = int(parts[1])
            remove_idx = int(parts[2])
            channel = await db.get_channel(parent_chat_id)
            welcome_channels_raw = channel.get('welcome_buttons_json') or '[]'
            if isinstance(welcome_channels_raw, str):
                try:
                    welcome_channels = json.loads(welcome_channels_raw)
                except (ValueError, TypeError):
                    welcome_channels = []
            elif isinstance(welcome_channels_raw, list):
                welcome_channels = welcome_channels_raw
            else:
                welcome_channels = []
            if 0 <= remove_idx < len(welcome_channels):
                removed = welcome_channels.pop(remove_idx)
                await db.update_channel_setting(parent_chat_id, 'welcome_buttons_json', json.dumps(welcome_channels))
                await query.answer(f"Removed {removed.get('text', 'channel')}", show_alert=True)
            await show_welcome_settings(query, db, parent_chat_id)

        elif data.startswith('preview_welcome:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.edit_message_text('Channel not found.')
            else:
                welcome_msg = channel.get('welcome_message', '') or 'Welcome to {channel_name}! \U0001f389'
                preview = welcome_msg.replace('{first_name}', query.from_user.first_name or 'there')
                preview = preview.replace('{last_name}', query.from_user.last_name or '')
                preview = preview.replace('{username}', f'@{query.from_user.username}' if query.from_user.username else 'there')
                preview = preview.replace('{user_id}', str(query.from_user.id))
                preview = preview.replace('{channel_name}', channel.get('chat_title', 'Channel'))
                preview = preview.replace('{channel_username}', f'@{channel.get("chat_username", "")}')
                preview = preview.replace('{member_count}', str(channel.get('member_count', 0)))
                preview = preview.replace('{coins}', '0')
                from datetime import datetime
                preview = preview.replace('{date}', datetime.now().strftime('%Y-%m-%d'))
                preview = preview.replace('{referral_link}', f'https://t.me/bot?start=ref_{query.from_user.id}')
                # Build preview buttons
                welcome_channels_raw = channel.get('welcome_buttons_json') or '[]'
                if isinstance(welcome_channels_raw, str):
                    try:
                        welcome_btns = json.loads(welcome_channels_raw)
                    except (ValueError, TypeError):
                        welcome_btns = []
                elif isinstance(welcome_channels_raw, list):
                    welcome_btns = welcome_channels_raw
                else:
                    welcome_btns = []
                btn_rows = []
                for btn in welcome_btns:
                    btn_rows.append([InlineKeyboardButton(btn.get('text', 'Link'), url=btn.get('url', 'https://t.me'))])
                btn_rows.append([InlineKeyboardButton('\U0001f519 Back', callback_data=f'welcome_settings:{chat_id}')])
                text = f"\U0001f440 WELCOME MESSAGE PREVIEW\n\n{preview}\n\n(This is how the welcome DM will look)"
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btn_rows))

        elif data.startswith('force_sub_settings:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            origin = parts[2] if len(parts) > 2 else 'channel'
            await show_force_sub_settings(query, db, chat_id, origin=origin)

        elif data.startswith('fsub_mode:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            new_mode = parts[2]
            await db.update_channel_setting(chat_id, 'force_sub_mode', new_mode)
            mode_names = {'auto': 'Auto', 'manual': 'Manual', 'drip': 'Drip', 'all': 'All Modes'}
            await query.answer(f'Force sub mode: {mode_names.get(new_mode, new_mode)}', show_alert=True)
            await show_force_sub_settings(query, db, chat_id)

        elif data.startswith('fsub_timeout_menu:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current_timeout = channel.get('force_sub_timeout', 0) if channel else 0
            text = ('\u23f0 FORCE SUB TIMEOUT\n\n'
                    'Accept users automatically after this time,\n'
                    'even if they have NOT joined the required channels.\n\n'
                    'Choose timeout duration:')
            buttons = []
            for hours, label in [(0, 'Never'), (1, '1 hour'), (6, '6 hours'), (12, '12 hours'), (24, '24 hours'), (48, '48 hours')]:
                icon = '\u2705 ' if current_timeout == hours else ''
                buttons.append([InlineKeyboardButton(f'{icon}{label}', callback_data=f'set_fsub_timeout:{chat_id}:{hours}')])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data=f'force_sub_settings:{chat_id}')])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith('set_fsub_timeout:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            hours = int(parts[2])
            await db.update_channel_setting(chat_id, 'force_sub_timeout', hours)
            label = f'{hours} hours' if hours > 0 else 'Never'
            await query.answer(f'Force sub timeout: {label}', show_alert=True)
            await show_force_sub_settings(query, db, chat_id)

        elif data.startswith('remove_force_sub:'):
            parts = data.split(':')
            parent_chat_id = int(parts[1])
            remove_chat_id = int(parts[2])
            channel = await db.get_channel(parent_chat_id)
            force_channels_raw = channel.get('force_subscribe_channels', '[]')
            if isinstance(force_channels_raw, str):
                try:
                    force_channels = json.loads(force_channels_raw)
                except (ValueError, TypeError):
                    force_channels = []
            elif isinstance(force_channels_raw, list):
                force_channels = force_channels_raw
            else:
                force_channels = []
            force_channels = [ch for ch in force_channels if ch.get('chat_id') != remove_chat_id]
            await db.update_channel_setting(parent_chat_id, 'force_subscribe_channels', json.dumps(force_channels))
            await show_force_sub_settings(query, db, parent_chat_id)

        elif data.startswith('verify_force_sub:'):
            chat_id = int(data.split(':')[1])
            await handle_verify_force_sub(query, context, db, chat_id, user_id)

        elif data.startswith('sync_pending:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if not channel or channel.get('owner_id') != user_id:
                await query.answer('Access denied', show_alert=True)
                return
            await query.answer('Syncing pending requests...', show_alert=False)
            try:
                # Get real pending count from Telegram
                chat_info = await context.bot.get_chat(chat_id)
                telegram_pending = getattr(chat_info, 'pending_join_request_count', 0) or 0

                # Get our DB pending count
                db_pending = await db.get_pending_count(chat_id)

                # Update stored count with Telegram's real number
                await db.update_channel_setting(chat_id, 'pending_requests', telegram_pending)

                msg = (f'\u2705 Sync Complete!\n\n'
                       f'\U0001f4ca Telegram pending: {telegram_pending}\n'
                       f'\U0001f4be Tracked in DB: {db_pending}\n\n')

                if telegram_pending > db_pending:
                    diff = telegram_pending - db_pending
                    msg += (f'\u26a0\ufe0f {diff} old request(s) not tracked in bot.\n\n'
                            f'\U0001f4a1 These were made before the bot was added as admin.\n'
                            f'To approve them: Open Telegram \u2192 Channel \u2192 Recent Actions \u2192 Join Requests.\n\n'
                            f'\u2705 All new requests are now tracked and managed automatically!')
                elif telegram_pending == 0 and db_pending == 0:
                    msg += '\U0001f389 No pending requests!'
                elif telegram_pending == 0 and db_pending > 0:
                    msg += ('\U0001f504 Cleaning up stale DB records...\n'
                            'Some tracked requests may have been approved/declined externally.')
                    # Clean up stale DB records
                    try:
                        await db.cleanup_stale_pending(chat_id)
                    except Exception:
                        pass
                else:
                    msg += '\u2705 All pending requests are tracked!'

                if db_pending > 0:
                    msg += f'\n\n\U0001f4cb Use the buttons below to manage {db_pending} tracked request(s):'

                buttons = []
                if db_pending > 0:
                    buttons.append([
                        InlineKeyboardButton(f'\u2705 Approve All ({db_pending})', callback_data=f'batch_approve:{chat_id}'),
                        InlineKeyboardButton(f'\u274c Decline All ({db_pending})', callback_data=f'decline_all:{chat_id}'),
                    ])
                buttons.append([
                    InlineKeyboardButton('\U0001f504 Refresh', callback_data=f'sync_pending:{chat_id}'),
                    InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}'),
                ])

                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
            except Exception as e:
                logger.error(f'Error syncing pending: {e}')
                await query.answer(f'Sync failed: {str(e)[:100]}', show_alert=True)


        elif data.startswith('batch_approve:'):
            chat_id = int(data.split(':')[1])
            await handle_batch_approve(query, context, db, chat_id)

        elif data.startswith('drip_settings:'):
            chat_id = int(data.split(':')[1])
            await show_drip_settings(query, db, chat_id)

        elif data.startswith('start_drip:'):
            chat_id = int(data.split(':')[1])
            await handle_start_drip(query, context, db, chat_id)

        elif data.startswith('pending_requests:'):
            chat_id = int(data.split(':')[1])
            await show_pending_requests(query, context, db, chat_id, user_id)

        elif data.startswith('decline_all:'):
            chat_id = int(data.split(':')[1])
            await handle_decline_all(query, context, db, chat_id)

        elif data.startswith('approve_one:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            target_user_id = int(parts[2])
            await handle_approve_one(query, context, db, chat_id, target_user_id)

        elif data.startswith('decline_one:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            target_user_id = int(parts[2])
            await handle_decline_one(query, context, db, chat_id, target_user_id)

        elif data.startswith('set_drip_rate:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            rate = int(parts[2])
            await db.update_channel_setting(chat_id, 'drip_rate', rate)
            await query.answer(f'Drip rate set to {rate}/batch', show_alert=True)
            await show_drip_settings(query, db, chat_id)

        elif data.startswith('set_drip_interval:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            interval = int(parts[2])
            await db.update_channel_setting(chat_id, 'drip_interval', interval)
            await query.answer(f'Drip interval set to {interval}s', show_alert=True)
            await show_drip_settings(query, db, chat_id)

        elif data.startswith('my_clones'):
            await show_my_clones(query, db, user_id)

        elif data.startswith('clone_settings:'):
            clone_id = int(data.split(':')[1])
            await show_clone_settings(query, db, clone_id, user_id)

        elif data.startswith('activate_clone:'):
            clone_id = int(data.split(':')[1])
            await handle_activate_clone(query, context, db, clone_id)

        elif data.startswith('pause_clone:'):
            clone_id = int(data.split(':')[1])
            await handle_pause_clone(query, context, db, clone_id)

        elif data.startswith('delete_clone:'):
            clone_id = int(data.split(':')[1])
            await handle_delete_clone(query, context, db, clone_id, user_id)

        elif data.startswith('confirm_delete_clone:'):
            clone_id = int(data.split(':')[1])
            await handle_confirm_delete_clone(query, context, db, clone_id, user_id)

        elif data.startswith('channel_stats:'):
            chat_id = int(data.split(':')[1])
            await show_channel_stats(query, db, chat_id)

        elif data == 'sa_analytics':
            from handlers.admin_panel import sa_full_analytics
            await sa_full_analytics(update, context)

        elif data == 'sa_manage_owners':
            from handlers.admin_panel import sa_manage_owners
            await sa_manage_owners(update, context)

        elif data == 'sa_manage_channels':
            from handlers.admin_panel import sa_manage_channels
            await sa_manage_channels(update, context)

        elif data == 'sa_manage_clones':
            from handlers.admin_panel import sa_manage_clones
            await sa_manage_clones(update, context)

        elif data == 'sa_platform_broadcast':
            from handlers.admin_panel import sa_platform_broadcast
            await sa_platform_broadcast(update, context)

        elif data == 'sa_manage_subs':
            from handlers.admin_panel import sa_manage_subscriptions
            await sa_manage_subscriptions(update, context)

        elif data.startswith('sa_activate_user:'):
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            target_id = int(data.split(':')[1])
            target_owner = await db.get_owner(target_id)
            target_name = target_owner.get('first_name', 'Unknown') if target_owner else 'Unknown'
            current_tier = target_owner.get('tier', 'free') if target_owner else 'free'
            buttons = [
                [InlineKeyboardButton('\U0001f48e Premium (30d)', callback_data=f'sa_set_tier:{target_id}:premium:30'),
                 InlineKeyboardButton('\U0001f48e Premium (90d)', callback_data=f'sa_set_tier:{target_id}:premium:90')],
                [InlineKeyboardButton('\U0001f4bc Business (30d)', callback_data=f'sa_set_tier:{target_id}:business:30'),
                 InlineKeyboardButton('\U0001f4bc Business (90d)', callback_data=f'sa_set_tier:{target_id}:business:90')],
                [InlineKeyboardButton('\U0001f4bc Business (365d)', callback_data=f'sa_set_tier:{target_id}:business:365')],
            ]
            if current_tier != 'free':
                buttons.append([InlineKeyboardButton('\u274c Deactivate Premium', callback_data=f'sa_deactivate:{target_id}')])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='sa_manage_subs')])
            await query.edit_message_text(
                f'\U0001f48e Manage Premium for:\n\n'
                f'\U0001f464 {target_name} (ID: {target_id})\n'
                f'Current Plan: {current_tier.upper()}\n\n'
                f'Select a plan to activate:',
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data.startswith('sa_set_tier:'):
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            parts = data.split(':')
            target_id = int(parts[1])
            tier = parts[2]
            days = int(parts[3])
            await db.activate_premium(target_id, tier, days)
            await query.answer(f'Activated {tier} for {days} days!', show_alert=True)
            # Notify the user
            try:
                await context.bot.send_message(target_id, f'\U0001f389 Your plan has been upgraded to {tier.upper()} for {days} days!')
            except Exception:
                pass
            # Go back to manage subs
            from handlers.admin_panel import sa_manage_subscriptions
            await sa_manage_subscriptions(update, context)

        elif data.startswith('sa_deactivate:'):
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            target_id = int(data.split(':')[1])
            await db.deactivate_premium(target_id)
            await query.answer('Premium deactivated!', show_alert=True)
            try:
                await context.bot.send_message(target_id, '\u26a0\ufe0f Your premium plan has been deactivated. You are now on the FREE plan.')
            except Exception:
                pass
            from handlers.admin_panel import sa_manage_subscriptions
            await sa_manage_subscriptions(update, context)

        elif data == 'sa_system_health':
            from handlers.admin_panel import sa_system_health
            await sa_system_health(update, context)

        elif data == 'edit_support_username':
            from handlers.admin_panel import sa_edit_support_username
            await sa_edit_support_username(update, context)

        elif data == 'sa_feature_toggles':
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            import config as _cfg
            await _show_feature_toggles(query, db)

        elif data == 'sa_toggle_premium':
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            import config as _cfg
            _cfg.ENABLE_PREMIUM = not _cfg.ENABLE_PREMIUM
            await db.set_platform_setting('ENABLE_PREMIUM', str(_cfg.ENABLE_PREMIUM).lower())
            status = 'ENABLED' if _cfg.ENABLE_PREMIUM else 'DISABLED (everyone is free!)'
            await query.answer(f'Premium Gate {status}!', show_alert=True)
            # Re-show feature toggles inline
            await _show_feature_toggles(query, db)

        elif data == 'sa_toggle_cloning':
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            import config as _cfg
            _cfg.ENABLE_CLONING = not _cfg.ENABLE_CLONING
            await db.set_platform_setting('ENABLE_CLONING', str(_cfg.ENABLE_CLONING).lower())
            status = 'ENABLED' if _cfg.ENABLE_CLONING else 'DISABLED'
            await query.answer(f'Clone Bot feature {status}!', show_alert=True)
            # Re-show feature toggles inline
            await _show_feature_toggles(query, db)

        elif data == 'sa_toggle_cross_promo':
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            import config as _cfg
            _cfg.ENABLE_CROSS_PROMO = not _cfg.ENABLE_CROSS_PROMO
            await db.set_platform_setting('ENABLE_CROSS_PROMO', str(_cfg.ENABLE_CROSS_PROMO).lower())
            status = 'ENABLED' if _cfg.ENABLE_CROSS_PROMO else 'DISABLED'
            await query.answer(f'Cross Promotion {status}!', show_alert=True)
            # Re-show feature toggles inline
            await _show_feature_toggles(query, db)

        elif data == 'sa_toggle_maintenance':
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            maint_raw = await db.get_platform_setting('MAINTENANCE_MODE', 'false')
            maint_on = maint_raw.lower() == 'true' if isinstance(maint_raw, str) else bool(maint_raw)
            new_state = not maint_on
            await db.set_platform_setting('MAINTENANCE_MODE', str(new_state).lower())
            status = 'ENABLED - Only superadmins can use the bot!' if new_state else 'DISABLED - Bot is open to all users'
            await query.answer(f'Maintenance Mode {status}', show_alert=True)
            await _show_feature_toggles(query, db)

        elif data == 'sa_toggle_watermark':
            if user_id not in __import__('config').SUPERADMIN_IDS:
                await query.answer('Access denied', show_alert=True)
                return
            wm_raw = await db.get_platform_setting('global_watermark_enabled', 'false')
            wm_on = wm_raw.lower() == 'true' if isinstance(wm_raw, str) else bool(wm_raw)
            new_wm = not wm_on
            await db.set_platform_setting('global_watermark_enabled', 'true' if new_wm else 'false')
            status = 'ENABLED' if new_wm else 'DISABLED'
            await query.answer(f'Global Watermark {status}!', show_alert=True)
            # Re-show feature toggles inline
            await _show_feature_toggles(query, db)

        elif data == 'toggle_add_channel_btn_mode':
            if user_id not in config.SUPERADMIN_IDS:
                await query.answer('Superadmin only!', show_alert=True)
                return
            current = await db.get_platform_setting('add_channel_btn_mode', 'superadmin_only')
            # Cycle: superadmin_only -> global -> superadmin_only
            new_mode = 'global' if current == 'superadmin_only' else 'superadmin_only'
            await db.set_platform_setting('add_channel_btn_mode', new_mode)
            mode_labels = {'superadmin_only': '🔒 Superadmin Only', 'global': '🌐 Global (All Users)'}
            await query.answer(f'Channel Button: {mode_labels[new_mode]}', show_alert=True)
            context.user_data['_reroute_data'] = 'default_welcome_msg'
            await button_callback(update, context)
            return

        elif data == 'default_watermark':
            # Dashboard-level watermark settings for all channels
            channels = await db.get_owner_channels(user_id)
            ch_count = len(channels) if channels else 0
            enabled_count = 0
            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                if full_ch and full_ch.get('watermark_enabled'):
                    enabled_count += 1

            all_enabled = enabled_count == ch_count and ch_count > 0
            status = '\U0001f7e2 Enabled' if all_enabled else ('\U0001f7e1 Partial' if enabled_count > 0 else '\U0001f534 Disabled')

            # Get global watermark username
            global_wm_username = await db.get_platform_setting(f'owner_{user_id}_watermark_username', '')

            text = (
                f'\U0001f3a8 WATERMARK SETTINGS (All Channels)\n\n'
                f'Status: {status} ({enabled_count}/{ch_count} channels)\n'
            )
            if global_wm_username:
                text += f'Default Username: @{global_wm_username}\n'
            text += (
                '\nThe watermark appears at the bottom of:\n'
                '\u2022 Welcome DMs\n'
                '\u2022 Force subscribe messages\n\n'
                'Toggle per channel or enable/disable all:\n'
            )

            toggle_text = '\U0001f534 Disable All' if all_enabled else '\U0001f7e2 Enable All'
            buttons = [
                [InlineKeyboardButton(toggle_text, callback_data='toggle_all_watermark')],
            ]
            for ch in (channels or []):
                full_ch = await db.get_channel(ch['chat_id'])
                wm_on = full_ch.get('watermark_enabled', False) if full_ch else False
                icon = '\u2705' if wm_on else '\u274c'
                title = ch.get('chat_title', 'Unknown')[:20]
                buttons.append([
                    InlineKeyboardButton(f'{icon} {title}', callback_data=f'toggle_watermark_ch:{ch["chat_id"]}'),
                    InlineKeyboardButton('\u2699\ufe0f Settings', callback_data=f'watermark_settings:{ch["chat_id"]}'),
                ])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data == 'toggle_all_watermark':
            channels = await db.get_owner_channels(user_id)
            if not channels:
                await query.answer('No channels found!', show_alert=True)
                return
            all_enabled = True
            for ch in channels:
                full_ch = await db.get_channel(ch['chat_id'])
                if not full_ch or not full_ch.get('watermark_enabled'):
                    all_enabled = False
                    break
            new_state = not all_enabled
            for ch in channels:
                await db.update_channel_setting(ch['chat_id'], 'watermark_enabled', new_state)
            status = 'ENABLED' if new_state else 'DISABLED'
            await query.answer(f'Watermark {status} for all channels!', show_alert=True)
            context.user_data['_reroute_data'] = 'default_watermark'
            await button_callback(update, context)
            return

        elif data.startswith('toggle_watermark_ch:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.answer('Channel not found', show_alert=True)
                return
            current = channel.get('watermark_enabled', False)
            await db.update_channel_setting(chat_id, 'watermark_enabled', not current)
            status = 'ENABLED' if not current else 'DISABLED'
            await query.answer(f'Watermark {status}!', show_alert=True)
            context.user_data['_reroute_data'] = 'default_watermark'
            await button_callback(update, context)
            return

        elif data == 'sa_edit_upi':
            context.user_data['awaiting_upi_input'] = True
            await query.edit_message_text(
                'Send the new UPI ID:',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='dashboard')]])
            )


        # --- Dashboard menu buttons ---
        elif data == 'broadcast':
            # Show broadcast channel selection
            channels = await db.get_owner_channels(user_id)
            if not channels:
                await query.edit_message_text('No channels found. Add a channel first.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]))
                return
            buttons = []
            for ch in channels:
                buttons.append([InlineKeyboardButton(
                    ch.get('chat_title', 'Unknown'),
                    callback_data=f"broadcast_to:{ch['chat_id']}"
                )])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
            await query.edit_message_text('\U0001f4e2 Select channel to broadcast to:',
                reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith('broadcast_to:'):
            chat_id = int(data.split(':')[1])
            context.user_data['broadcast_channel'] = chat_id
            channel = await db.get_channel(chat_id)
            title = channel.get('chat_title', 'Unknown') if channel else 'Unknown'
            await query.edit_message_text(
                f'\U0001f4e2 Broadcast to: {title}\n\nSend me the message to broadcast.\nSend /cancel to cancel.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data=f'channel:{chat_id}')]]))

        elif data == 'analytics_overview':
            channels = await db.get_owner_channels(user_id)
            if not channels:
                await query.edit_message_text('No channels to show analytics for.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]))
                return
            buttons = []
            for ch in channels:
                buttons.append([InlineKeyboardButton(
                    f"\U0001f4ca {ch.get('chat_title', 'Unknown')}",
                    callback_data=f"channel_stats:{ch['chat_id']}"
                )])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
            await query.edit_message_text('\U0001f4ca Select channel for analytics:',
                reply_markup=InlineKeyboardMarkup(buttons))

        elif data == 'templates_menu':
            from handlers.template_mgmt import show_templates_menu
            await show_templates_menu(update, context)

        elif data == 'auto_poster_menu':
            await query.edit_message_text(
                '\U0001f916 Auto Poster\n\nSchedule automatic posts to your channels.\n\nComing soon!',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]))

        elif data == 'referral_info':
            end_user = await db.get_end_user(user_id)
            coins = end_user.get('coins', 0) if end_user else 0
            ref_count = end_user.get('referral_count', 0) if end_user else 0
            bot_username = (await context.bot.get_me()).username
            ref_link = f'https://t.me/{bot_username}?start=ref_{user_id}'
            # Calculate referral channel slots
            refs_per_slot = getattr(config, 'REFERRALS_PER_SLOT', 3)
            bonus_slots = ref_count // refs_per_slot
            refs_to_next = refs_per_slot - (ref_count % refs_per_slot)
            progress_bar = '\u2588' * (ref_count % refs_per_slot) + '\u2591' * refs_to_next
            await query.edit_message_text(
                f'\U0001f517 REFERRAL PROGRAM\n\n'
                f'Your referral link:\n{ref_link}\n\n'
                f'\U0001f4b0 Coins: {coins}\n'
                f'\U0001f465 Referrals: {ref_count}\n\n'
                f'\U0001f4e2 CHANNEL SLOTS UNLOCKED\n'
                f'\U0001f513 Bonus Slots: {bonus_slots}\n'
                f'\U0001f4ca Progress to next slot: {progress_bar} ({ref_count % refs_per_slot}/{refs_per_slot})\n'
                f'Refer {refs_to_next} more to unlock +1 channel slot!\n\n'
                f'\u2139\ufe0f Every {refs_per_slot} referrals = 1 extra force sub channel slot',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\U0001f3c6 Leaderboard', callback_data='referral_leaderboard')],
                    [InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]
                ]))

        elif data == 'referral_leaderboard':
            top = await db.get_top_referrers(limit=10)
            text = '\U0001f3c6 TOP REFERRERS\n\n'
            for i, r in enumerate(top or [], 1):
                text += f"{i}. @{r.get('username', 'N/A')} - {r.get('referral_count', 0)} referrals\n"
            if not top:
                text += 'No referrals yet.\n'
            await query.edit_message_text(text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='referral_info')]]))

        elif data.startswith('watermark_settings:'):
            chat_id = int(data.split(':')[1])
            if user_id not in config.SUPERADMIN_IDS:
                await query.answer('Only superadmin can edit watermark settings', show_alert=True)
                return
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.answer('Channel not found', show_alert=True)
                return
            wm_enabled = channel.get('watermark_enabled', False)
            wm_username = channel.get('watermark_username', '')
            status = '\U0001f7e2 Enabled' if wm_enabled else '\U0001f534 Disabled'
            text = (f'\U0001f3a8 WATERMARK SETTINGS\n\n'
                    f'Status: {status}\n'
                    f'Username: @{wm_username}\n\n' if wm_username else
                    f'\U0001f3a8 WATERMARK SETTINGS\n\n'
                    f'Status: {status}\n'
                    f'Username: Not set\n\n')
            text += ('The watermark appears at the bottom of:\n'
                     '\u2022 Welcome DMs\n'
                     '\u2022 Force subscribe messages\n\n'
                     'Format: \u2014\u2014\u2014\u2014\u2014\n@yourusername')
            toggle_text = '\U0001f534 Disable' if wm_enabled else '\U0001f7e2 Enable'
            wm_text = channel.get('watermark_text', '') or 'Not set'
            wm_location = channel.get('watermark_location', 'bottom') or 'bottom'
            text += (f'\n\nCustom Text: {wm_text}'
                     f'\nLocation: {wm_location.title()}')
            wm_buttons = [
                [InlineKeyboardButton(toggle_text, callback_data=f'toggle_watermark:{chat_id}')],
                [InlineKeyboardButton('\u270f\ufe0f Edit Username', callback_data=f'edit_watermark:{chat_id}')],
                [InlineKeyboardButton('\U0001f4dd Edit Text', callback_data=f'edit_wm_text:{chat_id}')],
                [InlineKeyboardButton('\U0001f4cd Edit Location', callback_data=f'edit_wm_location:{chat_id}')],
                [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(wm_buttons))

        elif data.startswith('toggle_watermark:'):
            chat_id = int(data.split(':')[1])
            if user_id not in config.SUPERADMIN_IDS:
                await query.answer('Only superadmin can edit watermark settings', show_alert=True)
                return
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.answer('Access denied', show_alert=True)
                return
            current = channel.get('watermark_enabled', False)
            await db.update_channel_setting(chat_id, 'watermark_enabled', not current)
            status = 'DISABLED' if current else 'ENABLED'
            await query.answer(f'Watermark {status}!', show_alert=True)
            # Refresh the watermark settings menu - re-fetch and show
            channel = await db.get_channel(chat_id)
            wm_enabled = channel.get('watermark_enabled', False)
            wm_username = channel.get('watermark_username', '')
            status_txt = '🟢 Enabled' if wm_enabled else '🔴 Disabled'
            if wm_username:
                text = (f'🎨 WATERMARK SETTINGS\n\n'
                        f'Status: {status_txt}\n'
                        f'Username: @{wm_username}\n\n')
            else:
                text = (f'🎨 WATERMARK SETTINGS\n\n'
                        f'Status: {status_txt}\n'
                        f'Username: Not set\n\n')
            text += ('The watermark appears at the bottom of:\n'
                     '• Welcome DMs\n'
                     '• Force subscribe messages\n\n'
                     'Format: —————\n@yourusername')
            toggle_text = '🔴 Disable' if wm_enabled else '🟢 Enable'
            wm_buttons = [
                [InlineKeyboardButton(toggle_text, callback_data=f'toggle_watermark:{chat_id}')],
                [InlineKeyboardButton('✏️ Edit Username', callback_data=f'edit_watermark:{chat_id}')],
                [InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(wm_buttons))

        elif data.startswith('edit_watermark:'):
            chat_id = int(data.split(':')[1])
            if user_id not in config.SUPERADMIN_IDS:
                await query.answer('Only superadmin can edit watermark settings', show_alert=True)
                return
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.answer('Access denied', show_alert=True)
                return
            context.user_data['editing_watermark_for'] = chat_id
            await query.edit_message_text(
                '\u270f\ufe0f Send the username for the watermark (without @):\n\n'
                'Example: mychannel\n\n'
                'Send /cancel to abort.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\u274c Cancel', callback_data=f'watermark_settings:{chat_id}')]
                ])
            )

        elif data.startswith('edit_wm_text:'):
            chat_id = int(data.split(':')[1])
            if user_id not in config.SUPERADMIN_IDS:
                await query.answer('Only superadmin can edit watermark settings', show_alert=True)
                return
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.answer('Access denied', show_alert=True)
                return
            context.user_data['editing_wm_text_for'] = chat_id
            await query.edit_message_text(
                '\U0001f4dd Send the custom watermark text:\n\n'
                'This text appears above the @username in the watermark.\n'
                'Example: Powered by, Managed by, Join us at\n\n'
                'Send /cancel to abort.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\u274c Cancel', callback_data=f'watermark_settings:{chat_id}')]
                ])
            )

        elif data.startswith('edit_wm_location:'):
            chat_id = int(data.split(':')[1])
            if user_id not in config.SUPERADMIN_IDS:
                await query.answer('Only superadmin can edit watermark settings', show_alert=True)
                return
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.answer('Access denied', show_alert=True)
                return
            current_loc = channel.get('watermark_location', 'bottom') or 'bottom'
            await query.edit_message_text(
                f'\U0001f4cd WATERMARK LOCATION\n\n'
                f'Current: {current_loc.title()}\n\n'
                'Choose where the watermark appears:',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\u2b07\ufe0f Bottom' + (' \u2705' if current_loc == 'bottom' else ''), callback_data=f'set_wm_loc:{chat_id}:bottom')],
                    [InlineKeyboardButton('\u2b06\ufe0f Top' + (' \u2705' if current_loc == 'top' else ''), callback_data=f'set_wm_loc:{chat_id}:top')],
                    [InlineKeyboardButton('\U0001f519 Back', callback_data=f'watermark_settings:{chat_id}')],
                ])
            )

        elif data.startswith('set_wm_loc:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            location = parts[2]
            channel = await db.get_channel(chat_id)
            if not channel or channel.get('owner_id') != user_id:
                await query.answer('Access denied', show_alert=True)
                return
            await db.update_channel_setting(chat_id, 'watermark_location', location)
            await query.answer(f'Watermark location set to {location}!', show_alert=True)
            # Re-show watermark settings
            channel = await db.get_channel(chat_id)
            wm_enabled = channel.get('watermark_enabled', False)
            wm_username = channel.get('watermark_username', '')
            status = '\U0001f7e2 Enabled' if wm_enabled else '\U0001f534 Disabled'
            text = (f'\U0001f3a8 WATERMARK SETTINGS\n\n'
                    f'Status: {status}\n')
            if wm_username:
                text += f'Username: @{wm_username}\n\n'
            else:
                text += f'Username: Not set\n\n'
            text += ('The watermark appears at the bottom of:\n'
                     '\u2022 Welcome DMs\n'
                     '\u2022 Force subscribe messages\n\n'
                     'Format: \u2014\u2014\u2014\u2014\u2014\n@yourusername')
            wm_text = channel.get('watermark_text', '') or 'Not set'
            wm_location = channel.get('watermark_location', 'bottom') or 'bottom'
            text += (f'\n\nCustom Text: {wm_text}'
                     f'\nLocation: {wm_location.title()}')
            toggle_text = '\U0001f534 Disable' if wm_enabled else '\U0001f7e2 Enable'
            wm_buttons = [
                [InlineKeyboardButton(toggle_text, callback_data=f'toggle_watermark:{chat_id}')],
                [InlineKeyboardButton('\u270f\ufe0f Edit Username', callback_data=f'edit_watermark:{chat_id}')],
                [InlineKeyboardButton('\U0001f4dd Edit Text', callback_data=f'edit_wm_text:{chat_id}')],
                [InlineKeyboardButton('\U0001f4cd Edit Location', callback_data=f'edit_wm_location:{chat_id}')],
                [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(wm_buttons))

        elif data.startswith('cross_promo_setup:'):
            from handlers.cross_promo import show_cross_promo_menu
            chat_id_str = data.split(':')[1]
            await show_cross_promo_menu(update, context, int(chat_id_str) if chat_id_str != '0' else 0)

        elif data.startswith('toggle_cross_promo:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if not channel or channel.get('owner_id') != user_id:
                await query.answer('Access denied', show_alert=True)
                return
            current = channel.get('cross_promo_enabled', False)
            await db.update_channel_setting(chat_id, 'cross_promo_enabled', not current)
            status = 'DISABLED' if current else 'ENABLED'
            await query.answer(f'Cross Promotion {status}!', show_alert=True)
            from handlers.cross_promo import show_cross_promo_menu
            await show_cross_promo_menu(update, context, chat_id)

        elif data.startswith('set_promo_cat:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            category = parts[2]
            channel = await db.get_channel(chat_id)
            if not channel or channel.get('owner_id') != user_id:
                await query.answer('Access denied', show_alert=True)
                return
            await db.update_channel_setting(chat_id, 'cross_promo_category', category)
            await query.answer(f'Category set to {category}!', show_alert=True)
            from handlers.cross_promo import show_cross_promo_menu
            await show_cross_promo_menu(update, context, chat_id)

        elif data == 'clone_bot_menu':
            clones = await db.get_owner_clones(user_id)
            text = '\U0001f9ec CLONE BOT\n\nCreate clones of this bot with your own token.\n\n'
            buttons = []
            if clones:
                text += f'You have {len(clones)} clone(s):\n\n'
                for cl in clones:
                    status_icon = '\u2705' if cl.get('is_active') else '\u274c'
                    buttons.append([InlineKeyboardButton(
                        f"{status_icon} @{cl.get('bot_username', '?')}",
                        callback_data=f"clone_settings:{cl['clone_id']}"
                    )])
            else:
                text += 'No clones yet.\n'
            buttons.append([InlineKeyboardButton('\u2795 Create Clone', callback_data='create_clone')])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data == 'create_clone':
            # Trigger clone conversation
            await query.edit_message_text(
                '\U0001f9ec CREATE CLONE BOT\n\n'
                'Send me the bot token from @BotFather.\n'
                'Use /clone command to start the process.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='clone_bot_menu')]]))

        elif data == 'premium_info':
            from handlers.premium import show_premium_info
            await show_premium_info(update, context)

        elif data == 'settings':
            owner = await db.get_owner(user_id)
            tier = owner.get('tier', 'free').upper() if owner else 'FREE'
            await query.edit_message_text(
                f'\u2699\ufe0f SETTINGS\n\n'
                f'\U0001f464 User ID: {user_id}\n'
                f'\U0001f4b3 Plan: {tier}\n\n'
                f'Channel-specific settings can be configured from My Channels.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('\U0001f30d Language', callback_data='language_settings')],
                    [InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]
                ]))

        elif data == 'language_settings':
            await query.edit_message_text(
                '\U0001f30d Language settings coming soon!',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='settings')]]))

        elif data == 'help':
            await query.edit_message_text(
                '\u2753 HELP\n\n'
                'Commands:\n'
                '/start - Start the bot\n'
                '/dashboard - Open dashboard\n'
                '/channels - List your channels\n'
                '/clone - Create a clone bot\n'
                '/help - Show this help\n\n'
                'To get started, add this bot as admin to your channel!',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')]]))


        else:
            logger.warning(f'Unknown callback data: {data}')

    except Exception as e:
        if 'message is not modified' in str(e).lower():
            logger.debug(f'Message not modified (same content): {data}')
            return
        logger.exception(f'Error in button_callback: {e}')
        try:
            await query.edit_message_text(f'An error occurred: {str(e)[:200]}')
        except Exception:
            pass


async def show_my_channels(query, db, user_id):
    """Show list of user's channels."""
    channels = await db.get_owner_channels(user_id)
    if not channels:
        await query.edit_message_text(
            'You have no channels yet.\n\n'
            'Add me as an admin to your channel, then use /addchannel to set it up.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f519 Back', callback_data='admin_panel')]
            ])
        )
        return

    buttons = []
    for ch in channels:
        title = ch.get('chat_title', 'Unknown')
        chat_id = ch.get('chat_id')
        pending = ch.get('pending_requests', 0)
        label = f'{title}'
        if pending:
            label += f' ({pending} pending)'
        buttons.append([InlineKeyboardButton(label, callback_data=f'channel:{chat_id}')])

    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='admin_panel')])
    await query.edit_message_text('\U0001f4fa Your Channels:', reply_markup=InlineKeyboardMarkup(buttons))


async def show_my_clones(query, db, user_id):
    """Show list of user's clone bots."""
    clones = await db.get_owner_clones(user_id)
    if not clones:
        await query.edit_message_text(
            'You have no clone bots yet.\n\n'
            'Use /clone to create a new clone bot.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f519 Back', callback_data='admin_panel')]
            ])
        )
        return

    buttons = []
    for clone in clones:
        label = f"@{clone.get('bot_username', 'unknown')}"
        status = clone.get('status', 'unknown')
        if status == 'active':
            label = f'\u2705 {label}'
        elif status == 'paused':
            label = f'\u23f8 {label}'
        else:
            label = f'\u274c {label}'
        buttons.append([InlineKeyboardButton(label, callback_data=f"clone_settings:{clone['clone_id']}")])

    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='admin_panel')])
    await query.edit_message_text('\U0001f916 Your Clone Bots:', reply_markup=InlineKeyboardMarkup(buttons))


async def show_clone_settings(query, db, clone_id, user_id):
    """Show settings for a specific clone."""
    clone = await db.get_clone(clone_id)
    if not clone or clone.get('owner_id') != user_id:
        await query.edit_message_text('Clone not found.')
        return

    is_active = clone.get('is_active', False)
    status = 'active' if is_active else 'inactive'
    username = clone.get('bot_username', 'unknown')
    error = clone.get('last_error', '')
    text = (f'\U0001f916 Clone: @{username}\n'
            f'Status: {"\u2705 Active" if is_active else "\u23f8 Inactive"}\n'
            f"Created: {clone.get('created_at', 'N/A')}\n")
    if error:
        text += f'Last Error: {error[:100]}\n'

    buttons = []
    if status == 'active':
        buttons.append([InlineKeyboardButton('\u23f8 Pause', callback_data=f'pause_clone:{clone_id}')])
    else:
        buttons.append([InlineKeyboardButton('\u25b6\ufe0f Activate', callback_data=f'activate_clone:{clone_id}')])
    buttons.append([InlineKeyboardButton('\U0001f5d1 Delete', callback_data=f'delete_clone:{clone_id}')])
    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='my_clones')])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_activate_clone(query, context, db, clone_id):
    clone = await db.get_clone(clone_id)
    if not clone:
        await query.answer('Clone not found', show_alert=True)
        return
    clone_mgr = context.application.bot_data.get('clone_manager')
    if clone_mgr:
        try:
            await clone_mgr.start_clone(clone_id, clone['bot_token'], clone['owner_id'])
            await db.update_clone_status(clone_id, is_active=True)
            await query.answer('Clone activated!', show_alert=True)
        except Exception as e:
            await query.answer(f'Failed: {str(e)[:100]}', show_alert=True)
    try:
        await show_clone_settings(query, db, clone_id, query.from_user.id)
    except Exception as e:
        if 'not modified' not in str(e).lower():
            raise


async def handle_pause_clone(query, context, db, clone_id):
    clone_mgr = context.application.bot_data.get('clone_manager')
    if clone_mgr:
        await clone_mgr.stop_clone(clone_id)
    await db.update_clone_status(clone_id, is_active=False)
    await query.answer('Clone paused', show_alert=True)
    await show_clone_settings(query, db, clone_id, query.from_user.id)


async def handle_delete_clone(query, context, db, clone_id, user_id):
    await query.edit_message_text(
        'Are you sure you want to delete this clone?',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('\u2705 Yes, Delete', callback_data=f'confirm_delete_clone:{clone_id}'),
             InlineKeyboardButton('\u274c Cancel', callback_data=f'clone_settings:{clone_id}')]
        ])
    )


async def handle_confirm_delete_clone(query, context, db, clone_id, user_id):
    clone_mgr = context.application.bot_data.get('clone_manager')
    if clone_mgr:
        await clone_mgr.stop_clone(clone_id)
    await db.delete_clone(clone_id)
    await query.answer('Clone deleted', show_alert=True)
    await show_my_clones(query, db, user_id)


async def handle_verify_force_sub(query, context, db, chat_id, user_id):
    """Verify user has joined all required force-sub channels."""
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text('Channel not found.')
        return

    force_channels_raw = channel.get('force_subscribe_channels', '[]')
    if isinstance(force_channels_raw, str):
        try:
            force_channels = json.loads(force_channels_raw)
        except (ValueError, TypeError):
            force_channels = []
    elif isinstance(force_channels_raw, list):
        force_channels = force_channels_raw
    else:
        force_channels = []

    not_joined = []
    for req_ch in force_channels:
        try:
            member = await context.bot.get_chat_member(req_ch['chat_id'], user_id)
            if member.status in ('left', 'kicked'):
                not_joined.append(req_ch)
        except Exception:
            not_joined.append(req_ch)

    if not_joined:
        text = 'You still need to join these channels:\n\n'
        buttons = []
        for ch in not_joined:
            text += f"\u2022 {ch.get('title', 'Channel')}\n"
            if ch.get('url'):
                buttons.append([InlineKeyboardButton(f"\U0001f4e2 Join {ch.get('title', '')}", url=ch['url'])])
        text += '\nPlease join all channels above, then click verify.'
        buttons.append([InlineKeyboardButton("\u2705 I've Joined \u2014 Verify Me", callback_data=f'verify_force_sub:{chat_id}')])
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            if 'not modified' in str(e).lower():
                await query.answer('You still need to join all required channels!', show_alert=True)
            else:
                raise
        return

    force_sub_mode = channel.get('force_sub_mode', 'auto')

    if force_sub_mode == 'manual':
        # Manual mode - mark as verified, admin will approve
        try:
            await db.update_join_request_force_sub(user_id, chat_id, False)
        except Exception as e:
            logger.error(f'Error updating force sub status: {e}')
        await query.edit_message_text(
            '\u2705 Channels verified! Your request is pending admin approval.\n'
            'You will be notified when approved.')
        return

    if force_sub_mode == 'drip':
        # Drip mode - mark verified, will be approved in next drip batch
        try:
            await db.update_join_request_force_sub(user_id, chat_id, False)
        except Exception as e:
            logger.error(f'Error updating force sub status: {e}')
        await query.edit_message_text(
            '\u2705 Channels verified! You are in the approval queue.\n'
            'You will be approved shortly.')
        return

    # Auto mode (or 'all') - approve immediately
    try:
        await context.bot.approve_chat_join_request(chat_id, user_id)
    except Exception as e:
        logger.error(f'Failed to approve after force sub: {e}')
        await query.edit_message_text('Verification passed but approval failed. Please contact support.')
        return

    try:
        await db.update_join_request_force_sub(user_id, chat_id, False)
        await db.update_join_request_after_approve(user_id=user_id, chat_id=chat_id, dm_sent=True, processed_by='force_sub')
    except Exception as e:
        logger.error(f'Error updating after force sub approve: {e}')

    welcome_text = channel.get('welcome_message', 'Welcome! \U0001f389')
    welcome_text = welcome_text.replace('{first_name}', query.from_user.first_name or 'there')
    welcome_text = welcome_text.replace('{channel_name}', channel.get('chat_title', ''))
    await query.edit_message_text(f'\u2705 Verified! You have been approved.\n\n{welcome_text}')


async def handle_batch_approve(query, context, db, chat_id):
    """Approve all pending join requests for a channel."""
    pending = await db.get_pending_requests(chat_id)
    if not pending:
        await query.answer('No pending requests', show_alert=True)
        return

    approved = 0
    failed = 0
    for req in pending:
        try:
            await context.bot.approve_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_after_approve(
                user_id=req['user_id'], chat_id=chat_id,
                dm_sent=False, processed_by='batch_approve'
            )
            approved += 1
        except Exception as e:
            logger.warning(f"Batch approve failed for {req['user_id']}: {e}")
            failed += 1

    await query.answer(f'Approved: {approved}, Failed: {failed}', show_alert=True)
    try:
        await show_channel_settings(query, db, chat_id, query.from_user.id, context)
    except Exception:
        pass  # Message not modified is OK after batch operations


async def show_drip_settings(query, db, chat_id):
    """Show drip settings with quantity and interval options."""
    channel = await db.get_channel(chat_id)
    if not channel:
        await query.edit_message_text('Channel not found.')
        return

    drip_rate = channel.get('drip_rate', 5)
    drip_interval = channel.get('drip_interval', 60)
    pending_count = await db.get_pending_count(chat_id)

    # Format interval for display
    if drip_interval < 60:
        interval_display = f'{drip_interval}s'
    elif drip_interval < 3600:
        interval_display = f'{drip_interval // 60}m'
    else:
        interval_display = f'{drip_interval // 3600}h'

    text = (f'\U0001f4a7 DRIP SETTINGS\n\n'
            f'\U0001f4cb Pending requests: {pending_count}\n'
            f'\U0001f465 Batch size: {drip_rate} users\n'
            f'\u23f1 Interval: {interval_display}\n\n'
            f'\u2501\u2501\u2501 Batch Size \u2501\u2501\u2501\n'
            f'How many users to approve per batch:\n')

    buttons = []
    # Quantity row 1
    qty_row1 = []
    for q in [1, 5, 10]:
        icon = '\u2705 ' if drip_rate == q else ''
        qty_row1.append(InlineKeyboardButton(f'{icon}{q}', callback_data=f'set_drip_rate:{chat_id}:{q}'))
    buttons.append(qty_row1)
    # Quantity row 2
    qty_row2 = []
    for q in [25, 50, 100]:
        icon = '\u2705 ' if drip_rate == q else ''
        qty_row2.append(InlineKeyboardButton(f'{icon}{q}', callback_data=f'set_drip_rate:{chat_id}:{q}'))
    buttons.append(qty_row2)

    text += f'\n\u2501\u2501\u2501 Interval \u2501\u2501\u2501\n'
    text += f'Time between each batch:\n'

    # Interval row 1
    int_row1 = []
    for secs, label in [(30, '30s'), (60, '1m'), (300, '5m')]:
        icon = '\u2705 ' if drip_interval == secs else ''
        int_row1.append(InlineKeyboardButton(f'{icon}{label}', callback_data=f'set_drip_interval:{chat_id}:{secs}'))
    buttons.append(int_row1)
    # Interval row 2
    int_row2 = []
    for secs, label in [(900, '15m'), (1800, '30m'), (3600, '1h')]:
        icon = '\u2705 ' if drip_interval == secs else ''
        int_row2.append(InlineKeyboardButton(f'{icon}{label}', callback_data=f'set_drip_interval:{chat_id}:{secs}'))
    buttons.append(int_row2)

    if pending_count > 0:
        buttons.append([InlineKeyboardButton(
            f'\u25b6\ufe0f Start Drip Now ({pending_count} pending)',
            callback_data=f'start_drip:{chat_id}'
        )])

    buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data=f'channel:{chat_id}')])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            raise


async def handle_start_drip(query, context, db, chat_id):
    """Start drip-approving pending requests."""
    channel = await db.get_channel(chat_id)
    drip_rate = channel.get('drip_rate', 5)

    pending = await db.get_pending_requests(chat_id, limit=drip_rate)
    if not pending:
        await query.answer('No pending requests to drip', show_alert=True)
        return

    approved = 0
    for req in pending:
        try:
            await context.bot.approve_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_after_approve(
                user_id=req['user_id'], chat_id=chat_id,
                dm_sent=False, processed_by='drip'
            )
            approved += 1
        except Exception as e:
            logger.warning(f"Drip approve failed for {req['user_id']}: {e}")

    remaining = await db.get_pending_count(chat_id)
    await query.answer(f'Drip: approved {approved}, {remaining} remaining', show_alert=True)
    try:
        await show_channel_settings(query, db, chat_id, query.from_user.id, context)
    except Exception:
        pass


async def handle_decline_all(query, context, db, chat_id):
    """Decline all pending join requests."""
    pending = await db.get_pending_requests(chat_id)
    if not pending:
        await query.answer('No pending requests', show_alert=True)
        return

    declined = 0
    for req in pending:
        try:
            await context.bot.decline_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_status(req['user_id'], chat_id, 'declined')
            declined += 1
        except Exception as e:
            logger.warning(f"Decline failed for {req['user_id']}: {e}")

    await query.answer(f'Declined: {declined}', show_alert=True)
    try:
        await show_channel_settings(query, db, chat_id, query.from_user.id, context)
    except Exception:
        pass


async def handle_approve_one(query, context, db, chat_id, target_user_id):
    """Approve a single join request."""
    try:
        await context.bot.approve_chat_join_request(chat_id, target_user_id)
        await db.update_join_request_after_approve(
            user_id=target_user_id, chat_id=chat_id,
            dm_sent=False, processed_by='manual_approve'
        )
        await query.edit_message_text(f'\u2705 Approved user {target_user_id}')
    except Exception as e:
        await query.edit_message_text(f'\u274c Failed to approve: {str(e)[:200]}')


async def handle_decline_one(query, context, db, chat_id, target_user_id):
    """Decline a single join request."""
    try:
        await context.bot.decline_chat_join_request(chat_id, target_user_id)
        await db.update_join_request_status(target_user_id, chat_id, 'declined')
        await query.edit_message_text(f'\u274c Declined user {target_user_id}')
    except Exception as e:
        await query.edit_message_text(f'Failed to decline: {str(e)[:200]}')


async def show_channel_stats(query, db, chat_id):
    """Show statistics for a channel."""
    channel = await db.get_channel(chat_id)
    pending_count = await db.get_pending_count(chat_id)
    user_count = await db.get_channel_user_count(chat_id)

    text = (f'\U0001f4ca Channel Statistics:\n\n'
            f"Channel: {channel.get('chat_title', 'Unknown') if channel else 'Unknown'}\n"
            f"Members: {channel.get('member_count', 0) if channel else 0}\n"
            f"Approved users: {user_count}\n"
            f"Pending: {pending_count}\n"
            f"Total approved: {channel.get('total_approved', 0) if channel else 0}\n"
            f"DMs sent: {channel.get('total_dms_sent', 0) if channel else 0}\n"
            f"DMs failed: {channel.get('total_dms_failed', 0) if channel else 0}\n")

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('\U0001f519 Back', callback_data=f'channel:{chat_id}')]
        ])
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for inline editing (welcome message, support username)."""
    db = context.application.bot_data.get('db')
    if not db:
        return

    user_id = update.effective_user.id

    # Handle default welcome message editing (applies to all channels)
    editing_default_welcome = context.user_data.get('editing_default_welcome')
    if editing_default_welcome:
        del context.user_data['editing_default_welcome']
        new_message = update.message.text
        # Save as owner default
        try:
            await db.pool.execute(
                "INSERT INTO platform_settings (key, value, updated_at) VALUES ($1, $2, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()",
                f'owner_{user_id}_default_welcome', new_message
            )
        except Exception as e:
            logger.error(f'Failed to save default welcome: {e}')
        # Apply to channels that have welcome DM enabled
        channels = await db.get_owner_channels(user_id)
        updated = 0
        for ch in (channels or []):
            full_ch = await db.get_channel(ch['chat_id'])
            if full_ch and full_ch.get('welcome_dm_enabled'):
                try:
                    await db.update_channel_setting(ch['chat_id'], 'welcome_message', new_message)
                    updated += 1
                except Exception:
                    pass
        await update.message.reply_text(
            f'\u2705 Welcome message updated and applied to {updated} enabled channel(s)!\n\n'
            f'Preview:\n{new_message}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f4e9 Welcome Settings', callback_data='default_welcome_msg')],
                [InlineKeyboardButton('\U0001f519 Back to Dashboard', callback_data='dashboard')]
            ])
        )
        return True

    editing_welcome = context.user_data.get('editing_welcome_for')
    if editing_welcome:
        chat_id = editing_welcome
        del context.user_data['editing_welcome_for']
        new_message = update.message.text
        await db.update_channel_setting(chat_id, 'welcome_message', new_message)
        await update.message.reply_text(
            f'\u2705 Welcome message updated!\n\nPreview:\n{new_message}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f519 Back to Channel', callback_data=f'channel:{chat_id}')]
            ])
        )
        return True

    editing_support = context.user_data.get('editing_support_username_for')
    if editing_support:
        chat_id = editing_support
        del context.user_data['editing_support_username_for']
        username = update.message.text.strip().lstrip('@')
        await db.update_channel_setting(chat_id, 'support_username', username)
        await update.message.reply_text(
            f'\u2705 Support username set to @{username}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('\U0001f519 Back to Channel', callback_data=f'channel:{chat_id}')]
            ])
        )
        return True

    return False


# Alias for __init__.py import
callback_router = button_callback
