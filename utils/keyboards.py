from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton('📢 My Channels', callback_data='channels'),
         InlineKeyboardButton('📊 Analytics', callback_data='analytics')],
        [InlineKeyboardButton('⚙️ Settings', callback_data='settings'),
         InlineKeyboardButton('💎 Premium', callback_data='premium')],
        [InlineKeyboardButton('📋 Help', callback_data='help'),
         InlineKeyboardButton('👥 Referral', callback_data='referral')],
    ]
    return InlineKeyboardMarkup(keyboard)


def channel_list_keyboard(channels):
    keyboard = []
    for ch in channels:
        name = ch.get('channel_name', 'Unknown')
        cid = ch.get('channel_id', '')
        keyboard.append([InlineKeyboardButton(f'📢 {name}', callback_data=f'ch_{cid}')])
    keyboard.append([InlineKeyboardButton('➕ Add Channel', callback_data='add_channel')])
    keyboard.append([InlineKeyboardButton('🔙 Back', callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)


def channel_settings_keyboard(channel_id):
    keyboard = [
        [InlineKeyboardButton('✅ Auto-Accept', callback_data=f'toggle_aa_{channel_id}'),
         InlineKeyboardButton('👋 Welcome Msg', callback_data=f'set_welcome_{channel_id}')],
        [InlineKeyboardButton('🔗 Captcha', callback_data=f'toggle_captcha_{channel_id}'),
         InlineKeyboardButton('⏰ Delay', callback_data=f'set_delay_{channel_id}')],
        [InlineKeyboardButton('📢 Cross-Promo', callback_data=f'cross_promo_{channel_id}'),
         InlineKeyboardButton('🖼 Watermark', callback_data=f'watermark_{channel_id}')],
        [InlineKeyboardButton('📊 Stats', callback_data=f'stats_{channel_id}'),
         InlineKeyboardButton('📤 Broadcast', callback_data=f'broadcast_{channel_id}')],
        [InlineKeyboardButton('📅 Schedule', callback_data=f'schedule_{channel_id}'),
         InlineKeyboardButton('🗑 Remove', callback_data=f'remove_ch_{channel_id}')],
        [InlineKeyboardButton('🔙 Back', callback_data='channels')],
    ]
    return InlineKeyboardMarkup(keyboard)


def premium_keyboard():
    keyboard = [
        [InlineKeyboardButton('🥉 Basic - $5/mo', callback_data='buy_basic'),
         InlineKeyboardButton('🥈 Pro - $15/mo', callback_data='buy_pro')],
        [InlineKeyboardButton('🥇 Enterprise - $50/mo', callback_data='buy_enterprise')],
        [InlineKeyboardButton('🔙 Back', callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_keyboard(action, target_id=''):
    keyboard = [
        [InlineKeyboardButton('✅ Confirm', callback_data=f'confirm_{action}_{target_id}'),
         InlineKeyboardButton('❌ Cancel', callback_data=f'cancel_{action}')],
    ]
    return InlineKeyboardMarkup(keyboard)


def analytics_keyboard(channel_id):
    keyboard = [
        [InlineKeyboardButton('📈 7 Days', callback_data=f'analytics_7_{channel_id}'),
         InlineKeyboardButton('📈 30 Days', callback_data=f'analytics_30_{channel_id}')],
        [InlineKeyboardButton('📥 Export CSV', callback_data=f'export_csv_{channel_id}')],
        [InlineKeyboardButton('🔙 Back', callback_data=f'ch_{channel_id}')],
    ]
    return InlineKeyboardMarkup(keyboard)


def settings_keyboard():
    keyboard = [
        [InlineKeyboardButton('🌐 Language', callback_data='set_language'),
         InlineKeyboardButton('🔔 Notifications', callback_data='set_notifications')],
        [InlineKeyboardButton('🤖 Bot Clones', callback_data='clones'),
         InlineKeyboardButton('🔑 API Key', callback_data='api_key')],
        [InlineKeyboardButton('🔙 Back', callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard(callback_data='main_menu'):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton('🔙 Back', callback_data=callback_data)]]
    )


def captcha_keyboard(correct_answer, options):
    keyboard = []
    row = []
    for opt in options:
        row.append(InlineKeyboardButton(str(opt), callback_data=f'captcha_{opt}'))
        if len(row) >= 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)
