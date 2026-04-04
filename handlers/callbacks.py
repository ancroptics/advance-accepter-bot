import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from database.models import DatabaseModels
import config

logger = logging.getLogger(__name__)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    db = context.application.bot_data.get('db')

    try:
        if data == 'dashboard':
            from handlers.admin_panel import show_dashboard
            await show_dashboard(update, context, edit=True)

        elif data == 'premium_info':
            from handlers.premium import show_premium_info
            await show_premium_info(update, context)

        elif data.startswith('upgrade_to:'):
            from handlers.premium import handle_upgrade
            await handle_upgrade(update, context)

        elif data.startswith('manage_channel:'):
            chat_id = int(data.split(':')[1])
            context.user_data['active_channel_id'] = chat_id
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.edit_message_text('Channel not found.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))
                return
            auto = '\u2705 ON' if channel.get('auto_approve') else '\u274c OFF'
            mode = channel.get('approve_mode', 'instant').title()
            text = (f'\u2699\ufe0f MANAGE: {channel["chat_title"]}\n\n'
                    f'Auto-Approve: {auto}\n'
                    f'Mode: {mode}\n'
                    f'Members: {channel.get("member_count", 0)}\n'
                    f'Pending: {channel.get("pending_requests", 0)}\n')
            buttons = [
                [InlineKeyboardButton('\u2705 Toggle Auto-Approve', callback_data=f'toggle_auto:{chat_id}')],
                [InlineKeyboardButton('\U0001f4dd Edit Welcome DM', callback_data=f'edit_welcome:{chat_id}')],
                [InlineKeyboardButton('\U0001f512 Force Subscribe', callback_data=f'force_sub_menu:{chat_id}')],
                [InlineKeyboardButton('\U0001f4ca Analytics', callback_data=f'analytics:{chat_id}')],
                [InlineKeyboardButton('\U0001f4e2 Broadcast', callback_data=f'broadcast_to:{chat_id}')],
                [InlineKeyboardButton('\U0001f519 Back', callback_data='dashboard')],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith('toggle_auto:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('auto_approve', True)
            await db.update_channel_setting(chat_id, 'auto_approve', new_val)
            status = '\u2705 ON' if new_val else '\u274c OFF'
            await query.edit_message_text(f'Auto-Approve is now {status}',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]]))

        elif data.startswith('edit_welcome:'):
            chat_id = int(data.split(':')[1])
            context.user_data['editing_welcome_for'] = chat_id
            channel = await db.get_channel(chat_id)
            current = channel.get('welcome_message', 'Welcome {name}!')
            await query.edit_message_text(
                f'\U0001f4dd EDIT WELCOME DM\n\n'
                f'Current message:\n{current}\n\n'
                f'Variables: {{name}}, {{username}}, {{channel}}, {{date}}\n\n'
                f'Send your new welcome message:',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data=f'manage_channel:{chat_id}')]]))

        elif data.startswith('force_sub_menu:'):
            chat_id = int(data.split(':')[1])
            from handlers.force_subscribe import show_force_sub_menu
            await show_force_sub_menu(update, context, chat_id)

        elif data.startswith('toggle_force_sub:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('force_subscribe_enabled', False)
            await db.update_channel_setting(chat_id, 'force_subscribe_enabled', new_val)
            from handlers.force_subscribe import show_force_sub_menu
            await show_force_sub_menu(update, context, chat_id)

        elif data.startswith('add_force_sub_ch:'):
            chat_id = int(data.split(':')[1])
            from handlers.force_subscribe import start_add_force_sub_channel, FORCE_SUB_INPUT
            return await start_add_force_sub_channel(update, context, chat_id)

        elif data.startswith('verify_force_sub:'):
            chat_id = int(data.split(':')[1])
            from handlers.force_subscribe import verify_force_subscribe
            await verify_force_subscribe(update, context, chat_id)

        elif data.startswith('analytics:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            text = (f'\U0001f4ca ANALYTICS: {channel["chat_title"]}\n\n'
                    f'Total Requests: {channel.get("total_requests_received", 0)}\n'
                    f'Approved: {channel.get("total_approved", 0)}\n'
                    f'Pending: {channel.get("pending_requests", 0)}\n'
                    f'Declined: {channel.get("total_declined", 0)}\n'
                    f'Today: {stats.get("today", 0)}\n'
                    f'This Week: {stats.get("this_week", 0)}\n')
            await query.edit_message_text(text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]]))

        elif data == 'analytics_overview':
            channels = await db.get_owner_channels(user_id)
            text = '\U0001f4ca ANALYTICS OVERVIEW\n\n'
            for ch in (channels or []):
                stats = await db.get_channel_analytics(ch['chat_id'])
                text += f"{ch['chat_title']}: {stats.get('total_requests', 0)} total, {stats.get('pending', 0)} pending\n"
            if not channels:
                text += 'No channels yet.\n'
            await query.edit_message_text(text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data.startswith('broadcast_to:'):
            chat_id = int(data.split(':')[1])
            context.user_data['broadcast_channel'] = chat_id
            await query.edit_message_text(
                '\U0001f4e2 BROADCAST\n\nSend the message you want to broadcast to all users who joined via this channel:',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data=f'manage_channel:{chat_id}')]]))

        elif data == 'broadcast':
            channels = await db.get_owner_channels(user_id)
            if not channels:
                await query.edit_message_text('No channels.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))
                return
            buttons = []
            for ch in channels:
                buttons.append([InlineKeyboardButton(ch['chat_title'], callback_data=f'broadcast_to:{ch["chat_id"]}')])
            buttons.append([InlineKeyboardButton('Back', callback_data='dashboard')])
            await query.edit_message_text('Select a channel to broadcast to:',
                reply_markup=InlineKeyboardMarkup(buttons))

        elif data == 'templates_menu':
            await query.edit_message_text('\U0001f4dd TEMPLATES\n\nComing soon! Templates will let you create reusable welcome messages.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data == 'auto_poster_menu':
            await query.edit_message_text('\U0001f916 AUTO POSTER\n\nComing soon! Schedule automatic posts to your channels.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data == 'referral_info':
            owner = await db.get_owner(user_id)
            ref_code = owner.get('referral_code', 'N/A') if owner else 'N/A'
            ref_count = owner.get('referral_count', 0) if owner else 0
            coins = owner.get('coins', 0) if owner else 0
            bot_username = config.BOT_USERNAME or (await context.bot.get_me()).username
            text = (f'\U0001f517 REFERRAL PROGRAM\n\n'
                    f'Your link: https://t.me/{bot_username}?start=ref_{ref_code}\n'
                    f'Referrals: {ref_count}\n'
                    f'Coins earned: {coins}\n\n'
                    f'Earn {config.DEFAULT_REFERRAL_COINS} coins per referral!')
            await query.edit_message_text(text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data.startswith('cross_promo_setup:'):
            await query.edit_message_text('\U0001f504 CROSS-PROMOTION\n\nComing soon!',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data == 'clone_bot_menu':
            owner = await db.get_owner(user_id)
            tier = owner.get('tier', 'free') if owner else 'free'
            is_superadmin = user_id in config.SUPERADMIN_IDS
            if tier == 'free' and not is_superadmin:
                await query.edit_message_text('\U0001f9ec CLONE BOT\n\nThis feature requires Premium.\nUpgrade to create your own branded bot!',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('\U0001f48e Upgrade', callback_data='premium_info')],
                        [InlineKeyboardButton('Back', callback_data='dashboard')]
                    ]))
            else:
                clones = await db.get_owner_clones(user_id)
                text = '\U0001f9ec CLONE BOT\n\nCreate your own branded version of this bot!\n\n'
                if clones:
                    for cl in clones:
                        text += f"@{cl.get('bot_username', '?')} - {'Active' if cl.get('is_active') else 'Inactive'}\n"
                text += '\nSend /clone <bot_token> to create a new clone.'
                await query.edit_message_text(text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data == 'help':
            from handlers.user_commands import help_handler
            await help_handler(update, context)

        elif data == 'settings':
            await query.edit_message_text('Use /dashboard to manage your channels.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

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

        elif data == 'sa_system_health':
            from handlers.admin_panel import sa_system_health
            await sa_system_health(update, context)

        elif data == 'edit_support_username':
            from handlers.admin_panel import sa_edit_support_username
            await sa_edit_support_username(update, context)

        elif data == 'superadmin_panel':
            from handlers.admin_panel import superadmin_handler
            await superadmin_handler(update, context)

        elif data == 'my_channels':
            from handlers.admin_panel import show_my_channels
            await show_my_channels(update, context)

        elif data == 'sa_edit_upi':
            context.user_data['awaiting_upi_input'] = True
            upi_id = getattr(config, 'UPI_ID', 'payment@upi')
            await query.edit_message_text(
                f'\U0001f4b3 EDIT UPI ID\n\n'
                f'Current UPI: {upi_id}\n\n'
                'Send the new UPI ID:',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Cancel', callback_data='superadmin_panel')]])
            )

        else:
            logger.warning(f'Unknown callback data: {data}')
            await query.edit_message_text('Unknown action.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

    except BadRequest as e:
        if 'Message is not modified' not in str(e):
            logger.exception(f'BadRequest in callback_router: {e}')
    except Exception as e:
        logger.exception(f'Error in callback_router: {e}')
        try:
            await query.edit_message_text(
                'An error occurred. Please try again.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back to Dashboard', callback_data='dashboard')]]))
        except Exception:
            pass
