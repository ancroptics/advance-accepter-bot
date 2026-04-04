from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def dashboard_keyboard(channels=None, is_owner=False):
    buttons = []
    if channels:
        for ch in channels:
            buttons.append([InlineKeyboardButton(
                f"\u2699\ufe0f {ch.get('chat_title', 'Channel')[:25]}",
                callback_data=f"manage_channel:{ch['chat_id']}"
            )])
    if is_owner:
        buttons.extend([
            [
                InlineKeyboardButton('\U0001f4e2 Broadcast', callback_data='broadcast'),
                InlineKeyboardButton('\U0001f4ca Analytics', callback_data='analytics_overview'),
            ],
            [
                InlineKeyboardButton('\U0001f4dd Templates', callback_data='templates_menu'),
                InlineKeyboardButton('\U0001f916 Auto Poster', callback_data='auto_poster_menu'),
            ],
            [
                InlineKeyboardButton('\U0001f517 Referral', callback_data='referral_info'),
                InlineKeyboardButton('\U0001f504 Cross-Promo', callback_data='cross_promo_setup:0'),
            ],
            [
                InlineKeyboardButton('\U0001f9ec Clone Bot', callback_data='clone_bot_menu'),
                InlineKeyboardButton('\U0001f48e Premium', callback_data='premium_info'),
            ],
            [
                InlineKeyboardButton('\u2699\ufe0f Settings', callback_data='settings'),
                InlineKeyboardButton('\u2753 Help', callback_data='help'),
            ],
        ])
    return InlineKeyboardMarkup(buttons)


def channel_manage_keyboard(chat_id, channel=None):
    cid = chat_id
    auto = channel.get('auto_approve', True) if channel else True
    welcome = channel.get('welcome_dm_enabled', True) if channel else True
    pending = channel.get('pending_requests', 0) if channel else 0
    watermark = channel.get('watermark_enabled', True) if channel else True

    buttons = [
        [InlineKeyboardButton(
            f"{'\u274c Disable' if auto else '\u2705 Enable'} Auto-Approve",
            callback_data=f'toggle_auto_approve:{cid}'
        )],
        [
            InlineKeyboardButton('\U0001f552 Instant', callback_data=f'approve_mode:{cid}:instant'),
            InlineKeyboardButton('\U0001f4a7 Drip', callback_data=f'approve_mode:{cid}:drip'),
            InlineKeyboardButton('\u270b Manual', callback_data=f'approve_mode:{cid}:manual'),
        ],
        [InlineKeyboardButton(f'\U0001f4cb Pending: {pending:,}', callback_data=f'pending_requests:{cid}')],
        [InlineKeyboardButton('\U0001f4ac Edit Welcome Message', callback_data=f'edit_welcome:{cid}')],
        [InlineKeyboardButton('\U0001f30e Multi-Language', callback_data=f'language_setup:{cid}')],
        [InlineKeyboardButton('\U0001f441 Preview Welcome DM', callback_data=f'preview_welcome:{cid}')],
        [InlineKeyboardButton(
            f"{'\u274c' if welcome else '\u2705'} Toggle Welcome DM",
            callback_data=f'toggle_welcome_dm:{cid}'
        )],
        [InlineKeyboardButton('\U0001f512 Force Subscribe', callback_data=f'force_sub_setup:{cid}')],
        [InlineKeyboardButton('\U0001f504 Cross-Promotion', callback_data=f'cross_promo_setup:{cid}')],
        [InlineKeyboardButton(
            f"\U0001f3f7\ufe0f Watermark: {'ON' if watermark else 'OFF'}",
            callback_data=f'toggle_watermark:{cid}'
        )],
        [InlineKeyboardButton('\U0001f4ca Analytics', callback_data=f'analytics:{cid}')],
        [InlineKeyboardButton('\U0001f4e4 Export CSV', callback_data=f'export_csv:{cid}')],
        [InlineKeyboardButton('\U0001f519 Back to Dashboard', callback_data='dashboard')],
    ]
    return InlineKeyboardMarkup(buttons)


def back_button(callback_data='dashboard'):
    return InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data=callback_data)]])


def confirm_cancel_keyboard(confirm_data, cancel_data='dashboard'):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('\u2705 Confirm', callback_data=confirm_data),
         InlineKeyboardButton('\u274c Cancel', callback_data=cancel_data)]
    ])


def premium_upsell_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('\U0001f48e Premium - \u20b9199/mo', callback_data='upgrade_to:premium')],
        [InlineKeyboardButton('\U0001f4bc Business - \u20b9499/mo', callback_data='upgrade_to:business')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')],
    ])


def superadmin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('\U0001f4ca Full Analytics', callback_data='sa_analytics')],
        [InlineKeyboardButton('\U0001f465 Manage Owners', callback_data='sa_manage_owners')],
        [InlineKeyboardButton('\U0001f4e2 Manage Channels', callback_data='sa_manage_channels')],
        [InlineKeyboardButton('\U0001f9ec Manage Clones', callback_data='sa_manage_clones')],
        [InlineKeyboardButton('\U0001f4e2 Platform Broadcast', callback_data='sa_platform_broadcast')],
        [InlineKeyboardButton('\U0001f48e Manage Subs', callback_data='sa_manage_subs')],
        [InlineKeyboardButton('\U0001f527 System Health', callback_data='sa_system_health')],
    ])


def batch_approve_keyboard(chat_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton('\u2705 50', callback_data=f'batch_approve:{chat_id}:50'),
            InlineKeyboardButton('\u2705 100', callback_data=f'batch_approve:{chat_id}:100'),
        ],
        [
            InlineKeyboardButton('\u2705 500', callback_data=f'batch_approve:{chat_id}:500'),
            InlineKeyboardButton('\u2705 1000', callback_data=f'batch_approve:{chat_id}:1000'),
        ],
        [InlineKeyboardButton('\u2705 ALL \u26a0\ufe0f', callback_data=f'batch_approve:{chat_id}:all')],
        [InlineKeyboardButton('\U0001f550 Start Drip', callback_data=f'start_drip:{chat_id}')],
        [InlineKeyboardButton('\u274c Decline All', callback_data=f'decline_all:{chat_id}')],
        [InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')],
    ])
