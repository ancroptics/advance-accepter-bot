import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# Drip speed presets: (quantity_per_batch, interval_minutes)
DRIP_PRESETS = {
    'slow': {'quantity': 10, 'interval': 60, 'label': '🐢 Slow (10 every 60min)'},
    'medium': {'quantity': 50, 'interval': 30, 'label': '⚡ Medium (50 every 30min)'},
    'fast': {'quantity': 200, 'interval': 15, 'label': '🚀 Fast (200 every 15min)'},
    'turbo': {'quantity': 500, 'interval': 10, 'label': '💨 Turbo (500 every 10min)'},
}


async def show_pending_menu(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return

    # Get REAL pending count from DB
    pending = await db.get_pending_count(chat_id)
    # Update cached column
    try:
        await db.update_channel_setting(chat_id, 'pending_requests', pending)
    except Exception:
        pass

    approve_mode = channel.get('approve_mode', 'instant')
    drip_speed = channel.get('drip_speed', 'medium')
    drip_quantity = channel.get('drip_quantity', DRIP_PRESETS.get(drip_speed, DRIP_PRESETS['medium'])['quantity'])
    drip_interval = channel.get('drip_interval', DRIP_PRESETS.get(drip_speed, DRIP_PRESETS['medium'])['interval'])

    text = (f'📋 PENDING REQUESTS\n'
            f'Channel: {channel["chat_title"]}\n'
            f'Pending: {pending:,}\n'
            f'Mode: {approve_mode.capitalize()}\n')

    if approve_mode == 'drip':
        text += f'\n💧 Drip: {drip_quantity} users every {drip_interval} min ({drip_speed})\n'

    text += '\n'

    buttons = [
        [InlineKeyboardButton('✅ Approve 50', callback_data=f'batch_approve:{chat_id}:50'),
         InlineKeyboardButton('✅ Approve 100', callback_data=f'batch_approve:{chat_id}:100')],
        [InlineKeyboardButton('✅ Approve 500', callback_data=f'batch_approve:{chat_id}:500'),
         InlineKeyboardButton('✅ Approve 1000', callback_data=f'batch_approve:{chat_id}:1000')],
        [InlineKeyboardButton('✅ Approve ALL ⚠️', callback_data=f'batch_approve:{chat_id}:all')],
        [InlineKeyboardButton('💧 Drip Settings', callback_data=f'drip_settings:{chat_id}')],
        [InlineKeyboardButton('❌ Decline All', callback_data=f'decline_all:{chat_id}')],
        [InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def show_drip_settings(update, context, chat_id):
    """Show drip configuration UI with speed and quantity options."""
    query = update.callback_query
    db = context.application.bot_data.get('db')
    channel = await db.get_channel(chat_id)
    if not channel:
        return

    pending = await db.get_pending_count(chat_id)
    current_speed = channel.get('drip_speed', 'medium')
    current_quantity = channel.get('drip_quantity', 50)
    current_interval = channel.get('drip_interval', 30)
    approve_mode = channel.get('approve_mode', 'instant')
    is_drip_active = approve_mode == 'drip'

    text = (
        f'💧 DRIP APPROVE SETTINGS\n'
        f'Channel: {channel["chat_title"]}\n'
        f'Pending: {pending:,}\n\n'
        f'Status: {"\ud83d\udfe2 ACTIVE" if is_drip_active else "\ud83d\udd34 INACTIVE"}\n'
        f'Speed: {current_speed.capitalize()}\n'
        f'Batch Size: {current_quantity}\n'
        f'Interval: every {current_interval} min\n\n'
        f'\u2501\u2501\u2501 Choose Speed \u2501\u2501\u2501\n'
    )

    buttons = []
    for key, preset in DRIP_PRESETS.items():
        marker = '\u25cf ' if key == current_speed else '\u25cb '
        buttons.append([InlineKeyboardButton(
            f'{marker}{preset["label"]}',
            callback_data=f'drip_speed:{chat_id}:{key}'
        )])

    buttons.append([InlineKeyboardButton('\u2501\u2501\u2501 Custom Quantity \u2501\u2501\u2501', callback_data='noop')])
    # Custom quantity row
    buttons.append([
        InlineKeyboardButton('10', callback_data=f'drip_qty:{chat_id}:10'),
        InlineKeyboardButton('25', callback_data=f'drip_qty:{chat_id}:25'),
        InlineKeyboardButton('50', callback_data=f'drip_qty:{chat_id}:50'),
        InlineKeyboardButton('100', callback_data=f'drip_qty:{chat_id}:100'),
    ])
    buttons.append([
        InlineKeyboardButton('200', callback_data=f'drip_qty:{chat_id}:200'),
        InlineKeyboardButton('500', callback_data=f'drip_qty:{chat_id}:500'),
        InlineKeyboardButton('1000', callback_data=f'drip_qty:{chat_id}:1000'),
    ])

    buttons.append([InlineKeyboardButton('\u2501\u2501\u2501 Interval \u2501\u2501\u2501', callback_data='noop')])
    buttons.append([
        InlineKeyboardButton('5min', callback_data=f'drip_int:{chat_id}:5'),
        InlineKeyboardButton('10min', callback_data=f'drip_int:{chat_id}:10'),
        InlineKeyboardButton('15min', callback_data=f'drip_int:{chat_id}:15'),
        InlineKeyboardButton('30min', callback_data=f'drip_int:{chat_id}:30'),
        InlineKeyboardButton('60min', callback_data=f'drip_int:{chat_id}:60'),
    ])

    # Start/Stop drip
    if is_drip_active:
        buttons.append([InlineKeyboardButton('⏹ Stop Drip', callback_data=f'approve_mode:{chat_id}:instant')])
    else:
        buttons.append([InlineKeyboardButton('▶️ Start Drip Now', callback_data=f'start_drip:{chat_id}')])

    buttons.append([InlineKeyboardButton('🔙 Back', callback_data=f'pending_requests:{chat_id}')])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_drip_speed(update, context, chat_id, speed):
    """Set drip speed preset and update quantity/interval accordingly."""
    db = context.application.bot_data.get('db')
    preset = DRIP_PRESETS.get(speed, DRIP_PRESETS['medium'])
    await db.update_channel_setting(chat_id, 'drip_speed', speed)
    await db.update_channel_setting(chat_id, 'drip_quantity', preset['quantity'])
    await db.update_channel_setting(chat_id, 'drip_interval', preset['interval'])
    await show_drip_settings(update, context, chat_id)


async def handle_drip_quantity(update, context, chat_id, quantity):
    """Set custom drip quantity."""
    db = context.application.bot_data.get('db')
    await db.update_channel_setting(chat_id, 'drip_quantity', quantity)
    await db.update_channel_setting(chat_id, 'drip_speed', 'custom')
    await show_drip_settings(update, context, chat_id)


async def handle_drip_interval(update, context, chat_id, interval):
    """Set custom drip interval."""
    db = context.application.bot_data.get('db')
    await db.update_channel_setting(chat_id, 'drip_interval', interval)
    await db.update_channel_setting(chat_id, 'drip_speed', 'custom')
    await show_drip_settings(update, context, chat_id)


async def start_drip_mode(update, context, chat_id):
    """Activate drip mode and start the scheduler job."""
    query = update.callback_query
    db = context.application.bot_data.get('db')

    # Set approve_mode to drip
    await db.update_channel_setting(chat_id, 'approve_mode', 'drip')

    # Schedule drip job
    scheduler = context.application.bot_data.get('scheduler')
    if scheduler:
        scheduler.schedule_drip(chat_id, context.application)

    channel = await db.get_channel(chat_id)
    pending = await db.get_pending_count(chat_id)
    drip_quantity = channel.get('drip_quantity', 50)
    drip_interval = channel.get('drip_interval', 30)

    await query.edit_message_text(
        f'💧 DRIP MODE ACTIVATED\n\n'
        f'Channel: {channel["chat_title"]}\n'
        f'Pending: {pending:,}\n'
        f'Approving {drip_quantity} users every {drip_interval} minutes\n\n'
        f'The bot will automatically approve pending requests in batches.\n'
        f'You can stop drip mode anytime from settings.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('💧 Drip Settings', callback_data=f'drip_settings:{chat_id}')],
            [InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')],
        ])
    )


async def execute_batch_approve(update, context, chat_id, count):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    if count == -1:
        pending = await db.get_pending_requests(chat_id, limit=99999)
    else:
        pending = await db.get_pending_requests(chat_id, limit=count)
    if not pending:
        await query.edit_message_text('No pending requests.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')]]))
        return
    total = len(pending)
    sent = 0
    failed = 0
    dm_sent = 0
    dm_failed = 0
    channel = await db.get_channel(chat_id)
    msg = await query.edit_message_text(f'⏳ Approving... 0/{total}')
    for i, req in enumerate(pending):
        try:
            # Try DM first
            if channel and channel.get('welcome_dm_enabled'):
                try:
                    welcome_text = channel.get('welcome_message', 'Welcome!')
                    welcome_text = welcome_text.replace('{first_name}', req.get('first_name', 'there'))
                    welcome_text = welcome_text.replace('{channel_name}', channel.get('chat_title', ''))
                    await context.bot.send_message(req['user_id'], welcome_text)
                    dm_sent += 1
                except Exception:
                    dm_failed += 1
            # Approve
            await context.bot.approve_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_status(req['user_id'], chat_id, 'approved', 'batch')
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f'Batch approve error: {e}')
        if (i + 1) % 25 == 0:
            try:
                await msg.edit_text(f'⏳ Approving... {i+1}/{total}\n✅ Sent: {sent} | ❌ Failed: {failed} | DMs: {dm_sent}')
            except Exception:
                pass
        await asyncio.sleep(0.5)

    # Update pending count
    new_pending = await db.get_pending_count(chat_id)
    await db.update_channel_setting(chat_id, 'pending_requests', new_pending)
    await db.update_channel_stats_after_batch(chat_id, sent, dm_sent, dm_failed)
    await msg.edit_text(
        f'✅ Batch Complete!\n\nApproved: {sent}\nFailed: {failed}\nDMs Sent: {dm_sent}\nDMs Failed: {dm_failed}\nRemaining Pending: {new_pending:,}',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')]])
    )


async def execute_drip_batch(application, chat_id):
    """Called by scheduler to approve a drip batch."""
    db = application.bot_data.get('db')
    if not db:
        return

    channel = await db.get_channel(chat_id)
    if not channel or channel.get('approve_mode') != 'drip':
        return

    quantity = channel.get('drip_quantity', 50)
    pending = await db.get_drip_batch(chat_id, quantity)
    if not pending:
        logger.info(f'Drip: No pending requests for {chat_id}')
        return

    sent = 0
    failed = 0
    dm_sent = 0
    dm_failed = 0
    bot = application.bot

    for req in pending:
        try:
            if channel.get('welcome_dm_enabled'):
                try:
                    welcome_text = channel.get('welcome_message', 'Welcome!')
                    welcome_text = welcome_text.replace('{first_name}', req.get('first_name', 'there'))
                    welcome_text = welcome_text.replace('{channel_name}', channel.get('chat_title', ''))
                    await bot.send_message(req['user_id'], welcome_text)
                    dm_sent += 1
                except Exception:
                    dm_failed += 1
            await bot.approve_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_status(req['user_id'], chat_id, 'approved', 'drip')
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f'Drip approve error for {req["user_id"]}: {e}')
        await asyncio.sleep(0.3)

    # Update stats
    new_pending = await db.get_pending_count(chat_id)
    await db.update_channel_setting(chat_id, 'pending_requests', new_pending)
    await db.update_channel_stats_after_batch(chat_id, sent, dm_sent, dm_failed)
    logger.info(f'Drip batch for {chat_id}: approved={sent}, failed={failed}, remaining={new_pending}')

    # Notify owner
    try:
        owner_id = channel.get('owner_id')
        if owner_id:
            await bot.send_message(
                owner_id,
                f'💧 Drip batch complete for {channel["chat_title"]}\n'
                f'Approved: {sent} | Failed: {failed}\n'
                f'Remaining: {new_pending:,}'
            )
    except Exception:
        pass


async def decline_all_pending(update, context, chat_id):
    query = update.callback_query
    db = context.application.bot_data.get('db')
    pending = await db.get_pending_requests(chat_id, limit=99999)
    count = 0
    for req in pending:
        try:
            await context.bot.decline_chat_join_request(chat_id, req['user_id'])
            await db.update_join_request_status(req['user_id'], chat_id, 'declined', 'batch')
            count += 1
        except Exception:
            pass
        await asyncio.sleep(0.3)
    # Update pending count
    new_pending = await db.get_pending_count(chat_id)
    await db.update_channel_setting(chat_id, 'pending_requests', new_pending)
    await query.edit_message_text(f'❌ Declined {count} requests.\nRemaining: {new_pending:,}',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🔙 Back', callback_data=f'manage_channel:{chat_id}')]]))

batch_approve_conv_handler = None