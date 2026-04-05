from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton('\ud83d\udce2 My Channels', callback_data='channels'),
         InlineKeyboardButton('\ud83d\udcca Analytics', callback_data='analytics')],
        [InlineKeyboardButton('\u2699\ufe0f Settings', callback_data='settings'),
         InlineKeyboardButton('\ud83d\udc8e Premium', callback_data='premium')],
        [InlineKeyboardButton('\ud83d\udccb Help', callback_data='help'),
         InlineKeyboardButton('\ud83d\udc65 Referral', callback_data='referral')],
    ]
    return InlineKeyboardMarkup(keyboard)


def channel_list_keyboard(channels):
    keyboard = []
    for ch in channels:
        name = ch.get('channel_name', 'Unknown')
        cid = ch.get('channel_id', '')
        keyboard.append([InlineKeyboardButton(f'\ud83d\udce2 {name}', callback_data=f'ch_{cid}')])
    keyboard.append([InlineKeyboardButton('\u2795 Add Channel', callback_data='add_channel')])
    keyboard.append([InlineKeyboardButton('\ud83d\udd19 Back', callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)


def channel_settings_keyboard(channel_id):
    keyboard = [
        [InlineKeyboardButton('\u2705 Auto-Accept', callback_data=f'toggle_aa_{channel_id}'),
         InlineKeyboardButton('\ud83d\udc4b Welcome Msg', callback_data=f'set_welcome_{channel_id}')],
        [InlineKeyboardButton('\ud83d\udd17 Captcha', callback_data=f'toggle_captcha_{channel_id}'),
         InlineKeyboardButton('\u23f0 Delay', callback_data=f'set_delay_{channel_id}')],
        [InlineKeyboardButton('\ud83d\udce2 Cross-Promo', callback_data=f'cross_promo_{channel_id}')],
        [InlineKeyboardButton('\ud83d\udcca Stats', callback_data=f'stats_{channel_id}'),
         InlineKeyboardButton('\ud83d\udce4 Broadcast', callback_data=f'broadcast_{channel_id}')],
        [InlineKeyboardButton('\ud83d\udcc5 Schedule', callback_data=f'schedule_{channel_id}'),
         InlineKeyboardButton('\ud83d\uddd1 Remove', callback_data=f'remove_ch_{channel_id}')],
        [InlineKeyboardButton('\ud83d\udd19 Back', callback_data='channels')],
    ]
    return InlineKeyboardMarkup(keyboard)


def premium_keyboard():
    keyboard = [
        [InlineKeyboardButton('\ud83e\udd49 Basic - $5/mo', callback_data='buy_basic'),
         InlineKeyboardButton('\ud83e\udd48 Pro - $15/mo', callback_data='buy_pro')],
        [InlineKeyboardButton('\ud83e\udd47 Enterprise - $50/mo', callback_data='buy_enterprise')],
        [InlineKeyboardButton('\ud83d\udd19 Back', callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_keyboard(action, target_id=''):
    keyboard = [
        [InlineKeyboardButton('\u2705 Confirm', callback_data=f'confirm_{action}_{target_id}'),
         InlineKeyboardButton('\u274c Cancel', callback_data=f'cancel_{action}')],
    ]
    return InlineKeyboardMarkup(keyboard)


def analytics_keyboard(channel_id):
    keyboard = [
        [InlineKeyboardButton('\ud83d\udcc8 7 Days', callback_data=f'analytics_7_{channel_id}'),
         InlineKeyboardButton('\ud83d\udcc8 30 Days', callback_data=f'analytics_30_{channel_id}')],
        [InlineKeyboardButton('\ud83d\udce5 Export CSV', callback_data=f'export_csv_{channel_id}')],
        [InlineKeyboardButton('\ud83d\udd19 Back', callback_data=f'ch_{channel_id}')],
    ]
    return InlineKeyboardMarkup(keyboard)


def settings_keyboard():
    keyboard = [
        [InlineKeyboardButton('\ud83c\udf10 Language', callback_data='set_language'),
         InlineKeyboardButton('\ud83d\udd14 Notifications', callback_data='set_notifications')],
        [InlineKeyboardButton('\ud83e\udd16 Bot Clones', callback_data='clones'),
         InlineKeyboardButton('\ud83d\udd11 API Key', callback_data='api_key')],
        [InlineKeyboardButton('\ud83d\udd19 Back', callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard(callback_data='main_menu'):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton('\ud83d\udd19 Back', callback_data=callback_data)]]
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
