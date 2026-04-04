import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.keyboards import (
    get_dashboard_keyboard,
    get_channel_manage_keyboard,
    get_channel_settings_keyboard,
)
from database.models import DatabaseModels

logger = logging.getLogger(__name__)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central callback query router."""
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
        await query.edit_message_text("Bot is still initializing. Please try again.")
        return

    try:
        # Dashboard
        if data == 'dashboard':
            from handlers.admin_panel import show_dashboard
            await show_dashboard(update, context, edit=True)

        # Channel management
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
            channel = await db.get_channel(chat_id)
            if channel and channel['owner_id'] == user_id:
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
                await query.answer("Watermark can only be disabled with Premium!", show_alert=True)

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
                    f"\u2705 Drip approve started!\n\n"
                    f"Rate: {channel['drip_rate']} users every {channel['drip_interval']} minutes\n"
                    f"Active hours: {channel['drip_active_start']}:00 - {channel['drip_active_end']}:00",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("\u2699\ufe0f Configure Drip", callback_data=f"configure_drip:{chat_id}")],
                        [InlineKeyboardButton("\U0001f519 Back", callback_data=f"manage_channel:{chat_id}")]
                    ])
                )

        elif data.startswith('decline_all:'):
            chat_id = int(data.split(':')[1])
            from handlers.batch_approve import decline_all_pending
            await decline_all_pending(update, context, chat_id)

        # Welcome DM
        elif data.startswith('edit_welcome:'):
            chat_id = int(data.split(':')[1])
            from handlers.welcome_dm import start_welcome_edit
            await start_welcome_edit(update, context, chat_id)

        elif data.startswith('preview_welcome:'):
            chat_id = int(data.split(':')[1])
            from handlers.welcome_dm import preview_welcome
            await preview_welcome(update, context, chat_id)

        # Force subscribe
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
            parts = data.split(':')
            chat_id = int(parts[1])
            from handlers.force_subscribe import verify_force_subscribe
            await verify_force_subscribe(update, context, chat_id)

        # Cross promo
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

        # Analytics
        elif data.startswith('analytics:'):
            chat_id = int(data.split(':')[1])
            from handlers.analytics_view import show_channel_analytics
            await show_channel_analytics(update, context, chat_id)

        elif data == 'analytics_overview':
            from handlers.analytics_view import show_analytics_overview
            await show_analytics_overview(update, context)

        # Premium
        elif data == 'premium_info':
            from handlers.premium import show_premium_info
            await show_premium_info(update, context)

        elif data.startswith('upgrade_to:'):
            tier = data.split(':')[1]
            from handlers.premium import show_upgrade_instructions
            await show_upgrade_instructions(update, context, tier)

        # Clone
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

        # Templates
        elif data == 'templates_menu':
            from handlers.template_mgmt import show_templates_menu
            await show_templates_menu(update, context)

        # Auto poster
        elif data == 'auto_poster_menu':
            from handlers.auto_poster import show_auto_poster_menu
            await show_auto_poster_menu(update, context)

        # Language
        elif data.startswith('language_setup:'):
            chat_id = int(data.split(':')[1])
            from handlers.language_mgmt import show_language_menu
            await show_language_menu(update, context, chat_id)

        # Superadmin actions
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

        # Referral
        elif data == 'referral_info':
            from handlers.user_commands import referral_handler
            await referral_handler(update, context)

        # Cross promo category selection
        elif data.startswith('set_promo_cat:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            category = parts[2]
            channel = await db.get_channel(chat_id)
            if channel and channel['owner_id'] == user_id:
                await db.update_channel_setting(chat_id, 'cross_promo_category', category)
                from handlers.cross_promo import show_cross_promo_menu
                await show_cross_promo_menu(update, context, chat_id)

        # Export CSV
        elif data.startswith('export_csv:'):
            chat_id = int(data.split(':')[1])
            from handlers.analytics_view import export_channel_csv
            await export_channel_csv(update, context, chat_id)

        # Refresh analytics
        elif data.startswith('refresh_analytics:'):
            chat_id = int(data.split(':')[1])
            from handlers.analytics_view import show_channel_analytics
            await show_channel_analytics(update, context, chat_id)

        # Help
        elif data == 'help':
            from handlers.user_commands import help_handler
            await help_handler(update, context)

        # Settings
        elif data == 'settings':
            await query.edit_message_text(
                "\u2699\ufe0f Settings\n\nUse /dashboard to manage your channels.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f519 Back", callback_data="dashboard")]
                ])
            )

        else:
            logger.info(f"Unhandled callback: {data}")

    except Exception as e:
        logger.exception(f"Error in callback_router for data='{data}': {e}")
        try:
            await query.edit_message_text(
                "\u26a0\ufe0f An error occurred. Please try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\U0001f519 Back to Dashboard", callback_data="dashboard")]
                ])
            )
        except Exception:
            pass
