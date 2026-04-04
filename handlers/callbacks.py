import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.models import DatabaseModels

logger = logging.getLogger(__name__)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    user_id = query.from_user.id
    db: DatabaseModels = context.application.bot_data.get('db')
    if not db:
        await query.edit_message_text('Bot is still initializing. Please try again.')
        return

    try:
        if data == 'dashboard':
            from handlers.admin_panel import show_dashboard
            await show_dashboard(update, context, edit=True)
        elif data.startswith('manage_channel:'):
            chat_id = int(data.split(':')[1])
            from handlers.channel_settings import show_channel_settings
            await show_channel_settings(update, context, chat_id, edit=True)
        elif data.startswith('toggle_auto_approve:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if channel and channel['owner_id'] == user_id:
                new_val = not channel['auto_approve']
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
        elif data.startswith('toggle_welcome_dm:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if channel and channel['owner_id'] == user_id:
                new_val = not channel['welcome_dm_enabled']
                await db.update_channel_setting(chat_id, 'welcome_dm_enabled', new_val)
                from handlers.channel_settings import show_channel_settings
                await show_channel_settings(update, context, chat_id, edit=True)
        elif data.startswith('toggle_watermark:'):
            chat_id = int(data.split(':')[1])
            owner = await db.get_owner(user_id)
            if owner and owner['tier'] != 'free':
                channel = await db.get_channel(chat_id)
                if channel and channel['owner_id'] == user_id:
                    new_val = not channel['watermark_enabled']
                    await db.update_channel_setting(chat_id, 'watermark_enabled', new_val)
                    from handlers.channel_settings import show_channel_settings
                    await show_channel_settings(update, context, chat_id, edit=True)
            else:
                await query.answer('Watermark can only be disabled with Premium!', show_alert=True)
        elif data.startswith('pending_requests:'):
            chat_id = int(data.split(':')[1])
            from handlers.batch_approve import show_pending_menu
            await show_pending_menu(update, context, chat_id)
        elif data.startswith('batch_approve:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            count = int(parts[2]) if parts[2] != 'all' else -1
            from handlers.batch_approve import execute_batch_approve
            await execute_batch_approve(update, context, chat_id, count)
        elif data.startswith('start_drip:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if channel and channel['owner_id'] == user_id:
                await db.update_channel_setting(chat_id, 'approve_mode', 'drip')
                await query.edit_message_text(
                    f'Drip approve started!\nRate: {channel["drip_rate"]} every {channel["drip_interval"]}min',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]])
                )
        elif data.startswith('decline_all:'):
            chat_id = int(data.split(':')[1])
            from handlers.batch_approve import decline_all_pending
            await decline_all_pending(update, context, chat_id)
        elif data.startswith('edit_welcome:'):
            chat_id = int(data.split(':')[1])
            context.user_data['editing_welcome_for'] = chat_id
        elif data.startswith('preview_welcome:'):
            chat_id = int(data.split(':')[1])
            from handlers.welcome_dm import preview_welcome
            await preview_welcome(update, context, chat_id)
        elif data.startswith('force_sub_setup:'):
            chat_id = int(data.split(':')[1])
            from handlers.force_subscribe import show_force_sub_menu
            await show_force_sub_menu(update, context, chat_id)
        elif data.startswith('toggle_force_sub:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if channel and channel['owner_id'] == user_id:
                new_val = not channel['force_subscribe_enabled']
                await db.update_channel_setting(chat_id, 'force_subscribe_enabled', new_val)
                from handlers.force_subscribe import show_force_sub_menu
                await show_force_sub_menu(update, context, chat_id)
        elif data.startswith('verify_force_sub:'):
            chat_id = int(data.split(':')[1])
            from handlers.force_subscribe import verify_force_subscribe
            await verify_force_subscribe(update, context, chat_id)
        elif data.startswith('cross_promo_setup:'):
            chat_id = int(data.split(':')[1])
            from handlers.cross_promo import show_cross_promo_menu
            await show_cross_promo_menu(update, context, chat_id)
        elif data.startswith('toggle_cross_promo:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if channel and channel['owner_id'] == user_id:
                new_val = not channel['cross_promo_enabled']
                await db.update_channel_setting(chat_id, 'cross_promo_enabled', new_val)
                from handlers.cross_promo import show_cross_promo_menu
                await show_cross_promo_menu(update, context, chat_id)
        elif data.startswith('analytics:'):
            chat_id = int(data.split(':')[1])
            from handlers.analytics_view import show_channel_analytics
            await show_channel_analytics(update, context, chat_id)
        elif data == 'analytics_overview':
            from handlers.analytics_view import show_analytics_overview
            await show_analytics_overview(update, context)
        elif data == 'premium_info':
            from handlers.premium import show_premium_info
            await show_premium_info(update, context)
        elif data.startswith('upgrade_to:'):
            tier = data.split(':')[1]
            from handlers.premium import show_upgrade_instructions
            await show_upgrade_instructions(update, context, tier)
        elif data == 'clone_bot_menu':
            from handlers.clone_bot import show_clone_menu
            await show_clone_menu(update, context)
        elif data == 'clone_send_token':
            from handlers.clone_bot import prompt_clone_token
            await prompt_clone_token(update, context)
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
        elif data == 'templates_menu':
            from handlers.template_mgmt import show_templates_menu
            await show_templates_menu(update, context)
        elif data == 'auto_poster_menu':
            from handlers.auto_poster import show_auto_poster_menu
            await show_auto_poster_menu(update, context)
        elif data.startswith('language_setup:'):
            chat_id = int(data.split(':')[1])
            from handlers.language_mgmt import show_language_menu
            await show_language_menu(update, context, chat_id)
        elif data.startswith('set_promo_cat:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            category = parts[2]
            await db.update_channel_setting(chat_id, 'cross_promo_category', category)
            from handlers.cross_promo import show_cross_promo_menu
            await show_cross_promo_menu(update, context, chat_id)
        elif data.startswith('export_csv:'):
            chat_id = int(data.split(':')[1])
            from handlers.analytics_view import export_channel_csv
            await export_channel_csv(update, context, chat_id)
        elif data.startswith('refresh_analytics:'):
            chat_id = int(data.split(':')[1])
            from handlers.analytics_view import show_channel_analytics
            await show_channel_analytics(update, context, chat_id)
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
        elif data == 'sa_system_health':
            from handlers.admin_panel import sa_system_health
            await sa_system_health(update, context)
        elif data == 'sa_platform_broadcast':
            from handlers.admin_panel import sa_platform_broadcast
            await sa_platform_broadcast(update, context)
        elif data == 'sa_manage_subs':
            from handlers.admin_panel import sa_manage_subscriptions
            await sa_manage_subscriptions(update, context)
        elif data == 'referral_info':
            from handlers.user_commands import referral_handler
            await referral_handler(update, context)
        elif data.startswith('approve_one:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            target_user_id = int(parts[2])
            try:
                await context.bot.approve_chat_join_request(chat_id, target_user_id)
                await db.update_join_request_status(target_user_id, chat_id, 'approved', 'manual')
                pending_count = await db.get_pending_count(chat_id)
                await db.update_channel_setting(chat_id, 'pending_requests', pending_count)
                channel = await db.get_channel(chat_id)
                # Send welcome DM if enabled
                if channel and channel.get('welcome_dm_enabled'):
                    try:
                        welcome_text = channel.get('welcome_message', 'Welcome!')
                        welcome_text = welcome_text.replace('{channel_name}', channel.get('chat_title', ''))
                        await context.bot.send_message(target_user_id, welcome_text)
                    except Exception:
                        pass
                await query.edit_message_text(
                    f'\u2705 Approved user {target_user_id} for {channel["chat_title"] if channel else chat_id}',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]])
                )
            except Exception as e:
                await query.edit_message_text(f'\u274c Failed to approve: {str(e)[:100]}',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]]))
        elif data.startswith('decline_one:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            target_user_id = int(parts[2])
            try:
                await context.bot.decline_chat_join_request(chat_id, target_user_id)
                await db.update_join_request_status(target_user_id, chat_id, 'declined', 'manual')
                pending_count = await db.get_pending_count(chat_id)
                await db.update_channel_setting(chat_id, 'pending_requests', pending_count)
                channel = await db.get_channel(chat_id)
                await query.edit_message_text(
                    f'\u274c Declined user {target_user_id} for {channel["chat_title"] if channel else chat_id}',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]])
                )
            except Exception as e:
                await query.edit_message_text(f'\u274c Failed to decline: {str(e)[:100]}',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'manage_channel:{chat_id}')]]))
        elif data == 'edit_support_username':
            context.user_data['awaiting_support_username'] = True
            await query.edit_message_text(
                '\U0001f4ac Enter the support username (without @):\n\nType /cancel to cancel.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='dashboard')]])
            )
        else:
            logger.info(f'Unhandled callback: {data}')
    except Exception as e:
        logger.exception(f'Error in callback_router: {e}')
        try:
            await query.edit_message_text('An error occurred. Please try again.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back to Dashboard', callback_data='dashboard')]]))
        except Exception:
            pass
