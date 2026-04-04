import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin_panel import show_admin_panel, show_channel_settings
from handlers.force_subscribe import show_force_sub_settings

logger = logging.getLogger(__name__)


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
        # --- Navigation callbacks ---
        if data == 'my_channels':
            await show_my_channels(query, db, user_id)

        elif data == 'admin_panel':
            await show_admin_panel(update, context)

        elif data == 'close':
            await query.delete_message()

        elif data.startswith('channel:'):
            chat_id = int(data.split(':')[1])
            await show_channel_settings(query, db, chat_id, user_id)

        elif data.startswith('back_channels'):
            await show_my_channels(query, db, user_id)

        # --- Approve mode callbacks ---
        elif data.startswith('set_mode:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            mode = parts[2]
            await db.update_channel_setting(chat_id, 'approve_mode', mode)
            await query.answer(f'Mode set to {mode}', show_alert=True)
            await show_channel_settings(query, db, chat_id, user_id)

        # --- Toggle settings ---
        elif data.startswith('toggle_welcome_dm:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current = channel.get('welcome_dm_enabled', True)
            await db.update_channel_setting(chat_id, 'welcome_dm_enabled', not current)
            await show_channel_settings(query, db, chat_id, user_id)

        elif data.startswith('toggle_auto_approve:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current = channel.get('auto_approve', True)
            await db.update_channel_setting(chat_id, 'auto_approve', not current)
            await show_channel_settings(query, db, chat_id, user_id)

        elif data.startswith('toggle_force_sub:'):
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current = channel.get('force_subscribe_enabled', False)
            await db.update_channel_setting(chat_id, 'force_subscribe_enabled', not current)
            await show_channel_settings(query, db, chat_id, user_id)

        # --- Welcome message edit ---
        elif data.startswith('edit_welcome:'):
            chat_id = int(data.split(':')[1])
            context.user_data['editing_welcome_for'] = chat_id
            await query.edit_message_text(
                'Send me the new welcome message.\n\n'
                'Available variables:\n'
                '{first_name} - User first name\n'
                '{last_name} - User last name\n'
                '{username} - Username\n'
                '{user_id} - User ID\n'
                '{channel_name} - Channel name\n\n'
                'Send /cancel to cancel.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('Cancel', callback_data=f'channel:{chat_id}')]
                ])
            )

        # --- Support username edit ---
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

        # --- Force subscribe settings ---
        elif data.startswith('force_sub_settings:'):
            chat_id = int(data.split(':')[1])
            await show_force_sub_settings(query, db, chat_id)

        elif data.startswith('add_force_sub:'):
            from handlers.force_subscribe import start_add_force_sub_channel
            await start_add_force_sub_channel(update, context)

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

        # --- Verify force subscribe ---
        elif data.startswith('verify_force_sub:'):
            chat_id = int(data.split(':')[1])
            await handle_verify_force_sub(query, context, db, chat_id, user_id)

        # --- Batch actions ---
        elif data.startswith('batch_approve:'):
            chat_id = int(data.split(':')[1])
            await handle_batch_approve(query, context, db, chat_id)

        elif data.startswith('start_drip:'):
            chat_id = int(data.split(':')[1])
            await handle_start_drip(query, context, db, chat_id)

        elif data.startswith('decline_all:'):
            chat_id = int(data.split(':')[1])
            await handle_decline_all(query, context, db, chat_id)

        # --- Manual approve/decline single user ---
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

        # --- Drip settings ---
        elif data.startswith('set_drip_rate:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            rate = int(parts[2])
            await db.update_channel_setting(chat_id, 'drip_rate', rate)
            await query.answer(f'Drip rate set to {rate}/batch', show_alert=True)
            await show_channel_settings(query, db, chat_id, user_id)

        elif data.startswith('set_drip_interval:'):
            parts = data.split(':')
            chat_id = int(parts[1])
            interval = int(parts[2])
            await db.update_channel_setting(chat_id, 'drip_interval', interval)
            await query.answer(f'Drip interval set to {interval}s', show_alert=True)
            await show_channel_settings(query, db, chat_id, user_id)

        # --- Clone management callbacks ---
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

        # --- Stats ---
        elif data.startswith('channel_stats:'):
            chat_id = int(data.split(':')[1])
            await show_channel_stats(query, db, chat_id)

        else:
            logger.warning(f'Unknown callback data: {data}')

    except Exception as e:
        logger.exception(f'Error in button_callback: {e}')
        try:
            await query.edit_message_text(f'An error occurred: {str(e)[:200]}')
        except Exception:
            pass


async def show_my_channels(query, db, user_id):
    """Show list of user's channels."""
    channels = await db.get_user_channels(user_id)
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
    clones = await db.get_user_clones(user_id)
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

    status = clone.get('status', 'unknown')
    username = clone.get('bot_username', 'unknown')
    text = (f'\U0001f916 Clone: @{username}\n'
            f'Status: {status}\n'
            f"Created: {clone.get('created_at', 'N/A')}\n")

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
            await db.update_clone_status(clone_id, status='active')
            await query.answer('Clone activated!', show_alert=True)
        except Exception as e:
            await query.answer(f'Failed: {str(e)[:100]}', show_alert=True)
    await show_clone_settings(query, db, clone_id, query.from_user.id)


async def handle_pause_clone(query, context, db, clone_id):
    clone_mgr = context.application.bot_data.get('clone_manager')
    if clone_mgr:
        await clone_mgr.stop_clone(clone_id)
    await db.update_clone_status(clone_id, status='paused')
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
        buttons.append([InlineKeyboardButton("\u2705 I've Joined \u2014 Verify Me", callback_data=f'verify_force_sub:{chat_id}')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    # All joined - approve
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
    await show_channel_settings(query, db, chat_id, query.from_user.id)


async def handle_start_drip(query, context, db, chat_id):
    """Start drip-approving pending requests."""
    channel = await db.get_channel(chat_id)
    drip_rate = channel.get('drip_rate', 5)
    drip_interval = channel.get('drip_interval', 60)

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
    await show_channel_settings(query, db, chat_id, query.from_user.id)


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
    await show_channel_settings(query, db, chat_id, query.from_user.id)


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
    stats = await db.get_channel_stats(chat_id)
    if not stats:
        await query.answer('No stats available', show_alert=True)
        return

    text = (f'\U0001f4ca Channel Statistics:\n\n'
            f"Total requests: {stats.get('total_requests', 0)}\n"
            f"Approved: {stats.get('approved', 0)}\n"
            f"Declined: {stats.get('declined', 0)}\n"
            f"Pending: {stats.get('pending', 0)}\n"
            f"DMs sent: {stats.get('dms_sent', 0)}\n")

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

    # Check if editing welcome message
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

    # Check if editing support username
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
