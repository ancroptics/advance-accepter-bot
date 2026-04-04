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
            from handlers.channel_settings import show_channel_settings
            await show_channel_settings(update, context, chat_id, edit=True)

        elif data.startswith('toggle_auto_approve:') or data.startswith('toggle_auto:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('auto_approve', True)
            await db.update_channel_setting(chat_id, 'auto_approve', new_val)
            from handlers.channel_settings import show_channel_settings
            await show_channel_settings(update, context, chat_id, edit=True)

        elif data.startswith('approve_mode:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            mode = parts[2]
            await db.update_channel_setting(chat_id, 'approve_mode', mode)
            from handlers.channel_settings import show_channel_settings
            await show_channel_settings(update, context, chat_id, edit=True)

        elif data.startswith('pending_requests:'):
            chat_id = int(data.split(':')[1])
            from handlers.batch_approve import show_pending_menu
            await show_pending_menu(update, context, chat_id)

        elif data.startswith('toggle_welcome_dm:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('welcome_dm_enabled', True)
            await db.update_channel_setting(chat_id, 'welcome_dm_enabled', new_val)
            from handlers.channel_settings import show_channel_settings
            await show_channel_settings(update, context, chat_id, edit=True)

        elif data.startswith('preview_welcome:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            welcome_msg = channel.get('welcome_message', 'Welcome {name}!')
            preview = welcome_msg.replace('{name}', query.from_user.first_name).replace('{username}', f'@{query.from_user.username or "user"}').replace('{channel}', channel.get('chat_title', 'Channel')).replace('{date}', '2026-04-04')
            await query.edit_message_text(
                f'\U0001f441 WELCOME DM PREVIEW\n\n{preview}',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]]))

        elif data.startswith('language_setup:'):
            chat_id = int(data.split(':')[1])
            from handlers.language_mgmt import show_language_menu
            await show_language_menu(update, context, chat_id)

        elif data.startswith('force_sub_setup:'):
            chat_id = int(data.split(':')[1])
            from handlers.force_subscribe import show_force_sub_menu
            await show_force_sub_menu(update, context, chat_id)

        elif data.startswith('toggle_watermark:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('watermark_enabled', False)
            await db.update_channel_setting(chat_id, 'watermark_enabled', new_val)
            from handlers.channel_settings import show_channel_settings
            await show_channel_settings(update, context, chat_id, edit=True)

        elif data.startswith('export_csv:'):
            chat_id = int(data.split(':')[1])
            await query.edit_message_text('\U0001f4e4 Export feature coming soon!',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Back', callback_data=f'manage_channel:{chat_id}')]]))

        elif data.startswith('edit_welcome:'):
            chat_id = int(data.split(':')[1])
            context.user_data['editing_welcome_for'] = chat_id
            channel = await db.get_channel(chat_id)
            current = channel.get('welcome_message', 'Welcome {name}!')
            await query.edit_message_text(
                f'\U0001f4dd EDIT WELCOME DM\n\n'
                f'Current message:\n{current}\n\n'
                f'Variables: {{name}}, {{username}}, {{channel}}, {{date}}\n\n'
                f'Send your new welcome message now:',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001f519 Cancel', callback_data=f'manage_channel:{chat_id}')]]))

        elif data.startswith('batch_approve:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            count_str = parts[2]
            count = -1 if count_str == 'all' else int(count_str)
            from handlers.batch_approve import execute_batch_approve
            await execute_batch_approve(update, context, chat_id, count)

        elif data.startswith('drip_settings:'):
            chat_id = int(data.split(':')[1])
            from handlers.batch_approve import show_drip_settings
            await show_drip_settings(update, context, chat_id)

        elif data.startswith('drip_speed:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            speed = parts[2]
            from handlers.batch_approve import handle_drip_speed
            await handle_drip_speed(update, context, chat_id, speed)

        elif data.startswith('drip_qty:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            qty = int(parts[2])
            from handlers.batch_approve import handle_drip_quantity
            await handle_drip_quantity(update, context, chat_id, qty)

        elif data.startswith('drip_int:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            interval = int(parts[2])
            from handlers.batch_approve import handle_drip_interval
            await handle_drip_interval(update, context, chat_id, interval)

        elif data.startswith('start_drip:'):
            chat_id = int(data.split(':')[1])
            from handlers.batch_approve import start_drip_mode
            await start_drip_mode(update, context, chat_id)

        elif data == 'noop':
            pass

        elif data.startswith('decline_all:'):
            chat_id = int(data.split(':')[1])
            from handlers.batch_approve import decline_all_pending
            await decline_all_pending(update, context, chat_id)

        elif data.startswith('verify_force_sub:'):
            chat_id = int(data.split(':')[1])
            from handlers.force_subscribe import verify_force_subscribe
            await verify_force_subscribe(update, context, chat_id)

        elif data.startswith('analytics:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            stats = await db.get_channel_analytics(chat_id)
            text = (f'\U0001f4ca ANALYTICS: {channel["chat_title"]}\n\n'
                    f'Total Requests: {stats.get("total_requests", 0)}\n'
                    f'Approved: {stats.get("approved", 0)}\n'
                    f'Pending: {stats.get("pending", 0)}\n'
                    f'Declined: {stats.get("declined", 0)}\n'
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
            from handlers.clone_bot import show_clone_menu
            await show_clone_menu(update, context)

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

        elif data.startswith('approve_one:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            target_user_id = int(parts[2])
            try:
                # Send welcome DM if enabled
                channel = await db.get_channel(chat_id)
                if channel and channel.get('welcome_dm_enabled', True):
                    try:
                        welcome_text = channel.get('welcome_message', 'Welcome!')
                        welcome_text = welcome_text.replace('{first_name}', query.from_user.first_name or 'there')
                        welcome_text = welcome_text.replace('{channel_name}', channel.get('chat_title', ''))
                        await context.bot.send_message(target_user_id, welcome_text)
                    except Exception as dm_e:
                        logger.warning(f'Could not send welcome DM on manual approve: {dm_e}')
                await context.bot.approve_chat_join_request(chat_id, target_user_id)
                await db.update_join_request_status(target_user_id, chat_id, 'approved', 'manual')
                await query.edit_message_text(
                    f'\u2705 Approved user {target_user_id} for {channel.get("chat_title", "channel") if channel else "channel"}')
            except Exception as e:
                logger.error(f'Error approving user: {e}')
                await query.edit_message_text(f'\u274c Failed to approve: {str(e)[:100]}',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data.startswith('decline_one:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            target_user_id = int(parts[2])
            try:
                await context.bot.decline_chat_join_request(chat_id, target_user_id)
                await db.update_join_request_status(target_user_id, chat_id, 'declined', 'manual')
                channel = await db.get_channel(chat_id)
                await query.edit_message_text(
                    f'\u274c Declined user {target_user_id} for {channel.get("chat_title", "channel") if channel else "channel"}')
            except Exception as e:
                logger.error(f'Error declining user: {e}')
                await query.edit_message_text(f'\u274c Failed to decline: {str(e)[:100]}',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='dashboard')]]))

        elif data.startswith('activate_clone:'):
            clone_id = int(data.split(':')[1])
            from handlers.clone_bot import activate_clone
            await activate_clone(update, context, clone_id)

        elif data.startswith('pause_clone:'):
            clone_id = int(data.split(':')[1])
            from handlers.clone_bot import pause_clone
            await pause_clone(update, context, clone_id)

        elif data.startswith('delete_clone:'):
            clone_id = int(data.split(':')[1])
            from handlers.clone_bot import delete_clone
            await delete_clone(update, context, clone_id)

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