import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.models import Database
from handlers.batch_approve import start_batch_approve, handle_batch_progress
from handlers.channel_settings import (
    handle_channel_settings,
    handle_toggle_auto_approve,
    handle_toggle_force_sub,
    handle_set_welcome,
    handle_set_decline_text,
    handle_remove_channel,
    handle_sync_pending,
    handle_pending_action,
    handle_set_schedule,
    handle_schedule_input
)

logger = logging.getLogger(__name__)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query handler that routes to specific handlers."""
    query = update.callback_query
    await query.answer()

    data = query.data
    db: Database = context.bot_data['db']

    logger.info(f"Callback received: {data} from user {query.from_user.id}")

    try:
        # Channel settings
        if data.startswith('settings:'):
            chat_id = int(data.split(':')[1])
            await handle_channel_settings(query, db, chat_id)

        # Auto approve toggle
        elif data.startswith('toggle_auto_approve:'):
            chat_id = int(data.split(':')[1])
            await handle_toggle_auto_approve(query, db, chat_id)

        # Force sub toggle
        elif data.startswith('toggle_force_sub:'):
            chat_id = int(data.split(':')[1])
            await handle_toggle_force_sub(query, db, chat_id)

        # Welcome message
        elif data.startswith('set_welcome:'):
            chat_id = int(data.split(':')[1])
            await handle_set_welcome(query, db, chat_id, context)

        # Decline text
        elif data.startswith('set_decline_text:'):
            chat_id = int(data.split(':')[1])
            await handle_set_decline_text(query, db, chat_id, context)

        # Remove channel
        elif data.startswith('remove_channel:'):
            chat_id = int(data.split(':')[1])
            await handle_remove_channel(query, db, chat_id)

        # Sync pending requests
        elif data.startswith('sync_pending:'):
            chat_id = int(data.split(':')[1])
            await handle_sync_pending(query, db, chat_id, context)

        # Pending actions (approve/decline all)
        elif data.startswith('pending_action:'):
            parts = data.split(':')
            action = parts[1]
            chat_id = int(parts[2])
            await handle_pending_action(query, db, chat_id, action, context)

        # Batch approve
        elif data.startswith('batch_approve:'):
            chat_id = int(data.split(':')[1])
            await start_batch_approve(query, db, chat_id, context)

        # Batch progress
        elif data.startswith('batch_progress:'):
            chat_id = int(data.split(':')[1])
            await handle_batch_progress(query, db, chat_id, context)

        # Schedule settings
        elif data.startswith('set_schedule:'):
            chat_id = int(data.split(':')[1])
            await handle_set_schedule(query, db, chat_id, context)

        # Schedule input
        elif data.startswith('schedule_input:'):
            parts = data.split(':')
            schedule_type = parts[1]
            chat_id = int(parts[2])
            await handle_schedule_input(query, db, chat_id, schedule_type, context)

        # Back to dashboard
        elif data == 'back_to_dashboard':
            from handlers.admin_panel import show_dashboard
            await show_dashboard(query, db)

        # Refresh channel list
        elif data == 'refresh_channels':
            from handlers.admin_panel import show_dashboard
            await show_dashboard(query, db)

        # Confirm remove
        elif data.startswith('confirm_remove:'):
            chat_id = int(data.split(':')[1])
            await db.remove_channel(chat_id)
            await query.edit_message_text(
                '\u2705 Channel removed successfully!',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton('\U0001f504 Back to Dashboard', callback_data='back_to_dashboard')
                ]])
            )

        # Cancel remove
        elif data.startswith('cancel_remove:'):
            chat_id = int(data.split(':')[1])
            await handle_channel_settings(query, db, chat_id)

        else:
            logger.warning(f"Unknown callback data: {data}")

    except Exception as e:
        logger.error(f"Error handling callback {data}: {e}", exc_info=True)
        try:
            await query.edit_message_text(
                f'\u274c An error occurred: {str(e)}',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton('\U0001f504 Back to Dashboard', callback_data='back_to_dashboard')
                ]])
            )
        except:
            pass


async def welcome_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle welcome message input from user."""
    if not context.user_data.get('awaiting_welcome'):
        return

    chat_id = context.user_data.get('welcome_chat_id')
    if not chat_id:
        return

    db: Database = context.bot_data['db']
    welcome_text = update.message.text

    await db.update_channel_settings(chat_id, welcome_message=welcome_text)

    # Clear state
    context.user_data.pop('awaiting_welcome', None)
    context.user_data.pop('welcome_chat_id', None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton('\U0001f519 Back to Settings', callback_data=f'settings:{chat_id}')]
    ])

    await update.message.reply_text(
        f'\u2705 Welcome message updated!\n\nPreview:\n{welcome_text}',
        reply_markup=keyboard
    )


async def decline_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle decline text input from user."""
    if not context.user_data.get('awaiting_decline_text'):
        return

    chat_id = context.user_data.get('decline_chat_id')
    if not chat_id:
        return

    db: Database = context.bot_data['db']
    decline_text = update.message.text

    await db.update_channel_settings(chat_id, decline_text=decline_text)

    # Clear state
    context.user_data.pop('awaiting_decline_text', None)
    context.user_data.pop('decline_chat_id', None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton('\U0001f519 Back to Settings', callback_data=f'settings:{chat_id}')]
    ])

    await update.message.reply_text(
        f'\u2705 Decline text updated!\n\nPreview:\n{decline_text}',
        reply_markup=keyboard
    )


async def schedule_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle schedule time input from user."""
    if not context.user_data.get('awaiting_schedule_time'):
        return

    chat_id = context.user_data.get('schedule_chat_id')
    schedule_type = context.user_data.get('schedule_type')
    if not chat_id or not schedule_type:
        return

    db: Database = context.bot_data['db']
    time_input = update.message.text.strip()

    try:
        # Parse time input (HH:MM format)
        parts = time_input.split(':')
        if len(parts) != 2:
            raise ValueError("Invalid time format")

        hour = int(parts[0])
        minute = int(parts[1])

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time range")

        schedule_time = f"{hour:02d}:{minute:02d}"

        # Update channel settings
        await db.update_channel_settings(
            chat_id,
            schedule_type=schedule_type,
            schedule_time=schedule_time,
            schedule_enabled=True
        )

        # Clear state
        context.user_data.pop('awaiting_schedule_time', None)
        context.user_data.pop('schedule_chat_id', None)
        context.user_data.pop('schedule_type', None)

        type_labels = {
            'daily': 'Daily',
            'hourly': 'Every hour',
            'twice_daily': 'Twice daily (00:00 & 12:00)',
            'weekly': 'Weekly'
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton('\U0001f519 Back to Settings', callback_data=f'settings:{chat_id}')]
        ])

        await update.message.reply_text(
            f'\u2705 Schedule updated!\n\n'
            f'Type: {type_labels.get(schedule_type, schedule_type)}\n'
            f'Time: {schedule_time} UTC\n'
            f'Status: Enabled',
            reply_markup=keyboard
        )

    except ValueError as e:
        await update.message.reply_text(
            '\u274c Invalid time format. Please send time in HH:MM format (e.g., 09:00, 14:30).\n'
            'Hours: 00-23, Minutes: 00-59'
        )
