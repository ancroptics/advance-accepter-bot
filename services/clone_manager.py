import logging
import asyncio
import json
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ChatJoinRequestHandler, ChatMemberHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import config

logger = logging.getLogger(__name__)


class CloneManager:
    def __init__(self, application):
        self.application = application
        self.active_clones = {}
        self._polling_tasks = {}

    @property
    def db(self):
        return self.application.bot_data.get('db')

    async def startup_all_clones(self):
        """Start all active clones from database."""
        try:
            if not self.db:
                logger.warning('DB not available for clone startup')
                return
            clones = await self.db.get_active_clones()
            logger.info(f'Starting {len(clones)} bot clones')
            for clone in clones:
                try:
                    await self.start_clone(
                        clone['clone_id'],
                        clone['bot_token'],
                        clone['owner_id'],
                    )
                except Exception as e:
                    logger.error(f"Failed to start clone {clone['clone_id']}: {e}")
                    await self.db.update_clone_status(clone['clone_id'], error_msg=str(e))
        except Exception as e:
            logger.error(f'Error starting clones: {e}')

    async def start_clone(self, clone_id, token, owner_id):
        """Start a clone bot with polling for join requests."""
        if clone_id in self.active_clones:
            logger.info(f'Clone {clone_id} already running, skipping')
            return

        try:
            # Build a lightweight Application for the clone
            clone_app = Application.builder().token(token).build()

            # Share the same DB reference
            clone_app.bot_data['db'] = self.db
            clone_app.bot_data['owner_id'] = owner_id
            clone_app.bot_data['clone_id'] = clone_id
            clone_app.bot_data['parent_app'] = self.application

            # Register handlers for the clone
            clone_app.add_handler(CommandHandler('start', clone_start_handler))
            clone_app.add_handler(ChatJoinRequestHandler(clone_join_request_handler))
            clone_app.add_handler(CallbackQueryHandler(clone_callback_handler))
            clone_app.add_handler(MessageHandler(filters.ALL, clone_fallback_handler))

            await clone_app.initialize()
            await clone_app.start()
            await clone_app.updater.start_polling(
                allowed_updates=['message', 'callback_query', 'chat_join_request', 'my_chat_member'],
                drop_pending_updates=True,
            )

            bot_info = await clone_app.bot.get_me()
            self.active_clones[clone_id] = {
                'app': clone_app,
                'username': bot_info.username,
                'token': token,
                'owner_id': owner_id,
            }
            logger.info(f'Clone {clone_id} started as @{bot_info.username} (polling)')
        except Exception as e:
            logger.error(f'Clone {clone_id} start failed: {e}')
            raise

    async def stop_clone(self, clone_id):
        """Stop a running clone bot."""
        clone_data = self.active_clones.pop(clone_id, None)
        if clone_data and clone_data.get('app'):
            try:
                clone_app = clone_data['app']
                await clone_app.updater.stop()
                await clone_app.stop()
                await clone_app.shutdown()
                logger.info(f'Stopped clone {clone_id}')
            except Exception as e:
                logger.error(f'Error stopping clone {clone_id}: {e}')

    async def shutdown_all_clones(self):
        for clone_id in list(self.active_clones.keys()):
            await self.stop_clone(clone_id)


async def clone_start_handler(update: Update, context):
    """Handle /start for clone bots - mirrors main bot dashboard."""
    try:
        bot_info = await context.bot.get_me()
        db = context.application.bot_data.get('db')
        owner_id = context.application.bot_data.get('owner_id')
        clone_id = context.application.bot_data.get('clone_id')
        user_id = update.effective_user.id

        # Check for force sub verification deep link: /start verify_CHATID
        if context.args and context.args[0].startswith('verify_'):
            try:
                chat_id = int(context.args[0][7:])
                await _handle_clone_force_sub_verify(update, context, chat_id)
                return
            except (ValueError, IndexError):
                pass

        # Check for referral deep link
        if context.args and context.args[0].startswith('ref_'):
            try:
                referrer_id = int(context.args[0][4:])
                if referrer_id != user_id and db:
                    await db.set_referrer(user_id, referrer_id)
                    await db.award_referral_coins(referrer_id, config.DEFAULT_REFERRAL_COINS)
            except Exception:
                pass

        if not db:
            await update.message.reply_text('Bot is initializing, please try again in a moment.')
            return

        # Check if user is the clone owner - show management dashboard
        if user_id == owner_id:
            channels = await db.get_owner_channels(owner_id)
            owner_data = await db.get_owner(owner_id)
            tier = owner_data.get('tier', 'free').upper() if owner_data else 'FREE'
            text = (f'\U0001f4ca CLONE BOT DASHBOARD\n\n'
                    f'\U0001f44b Hey {update.effective_user.first_name}!\n'
                    f'\U0001f916 Bot: @{bot_info.username}\n'
                    f'\U0001f3f7\ufe0f Plan: {tier}\n\n'
                    f'\u2501\u2501\u2501 YOUR CHANNELS \u2501\u2501\u2501\n\n')
            buttons = []
            if channels:
                for ch in channels:
                    auto = '\u2705 Auto: ON' if ch.get('auto_approve') else '\u23f8\ufe0f Auto: OFF'
                    text += (f"\U0001f4e2 {ch['chat_title']}\n"
                             f"   \U0001f465 {ch.get('member_count', 0)} | \U0001f4cb {ch.get('pending_requests', 0)} pending\n"
                             f"   {auto}\n\n")
                    buttons.append([InlineKeyboardButton(
                        f"\u2699\ufe0f {ch['chat_title'][:25]}",
                        callback_data=f"clone_manage_ch:{ch['chat_id']}"
                    )])
            else:
                text += 'No channels yet. Add this clone bot as admin to your channel!\n\n'
            buttons.append([InlineKeyboardButton('\U0001f4e2 Broadcast', callback_data='clone_broadcast')])
            buttons.append([InlineKeyboardButton('\U0001f4ca Analytics', callback_data='clone_analytics')])
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            # Regular user - show welcome and channel info
            channels = await db.get_owner_channels(owner_id)
            channel_names = ', '.join([ch.get('chat_title', '?') for ch in (channels or [])]) or 'various channels'
            text = (f'\U0001f44b Welcome!\n\n'
                    f'I\'m @{bot_info.username}, and I manage:\n'
                    f'\U0001f4e2 {channel_names}\n\n'
                    f'I handle join requests, welcome messages, and more!\n\n'
                    f'\u2705 Bot is active and running!')
            buttons = []
            for ch in (channels or []):
                if ch.get('chat_username'):
                    buttons.append([InlineKeyboardButton(
                        f"\U0001f4e2 Join {ch['chat_title'][:25]}",
                        url=f"https://t.me/{ch['chat_username']}"
                    )])
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
    except Exception as e:
        logger.error(f'Error in clone start handler: {e}')


async def _handle_clone_force_sub_verify(update, context, chat_id):
    """Verify force subscribe for clone bot via deep link."""
    user_id = update.effective_user.id
    db = context.application.bot_data.get('db')
    if not db:
        await update.message.reply_text('Bot is initializing, try again.')
        return

    channel = await db.get_channel(chat_id)
    if not channel:
        await update.message.reply_text('Channel not found.')
        return

    required_channels_raw = channel.get('force_subscribe_channels') or []
    if isinstance(required_channels_raw, str):
        try:
            required_channels = json.loads(required_channels_raw)
        except (ValueError, TypeError):
            required_channels = []
    else:
        required_channels = required_channels_raw if isinstance(required_channels_raw, list) else []

    all_joined = True
    not_joined = []
    for req_ch in required_channels:
        try:
            member = await context.bot.get_chat_member(req_ch['chat_id'], user_id)
            if member.status in ('left', 'kicked'):
                all_joined = False
                not_joined.append(req_ch)
        except Exception:
            all_joined = False
            not_joined.append(req_ch)

    if all_joined:
        try:
            await context.bot.approve_chat_join_request(chat_id, user_id)
            await db.update_join_request_status(user_id, chat_id, 'approved', 'force_sub_clone')
            await update.message.reply_text(
                f'\u2705 Verified! You\'ve been approved to join {channel.get("chat_title", "the channel")}!'
            )
        except Exception as e:
            logger.error(f'Error approving after clone force sub verify: {e}')
            await update.message.reply_text('\u2705 Verified! You should now have access.')
    else:
        text = '\u274c You haven\'t joined all required channels yet:\n\n'
        buttons = []
        for ch in not_joined:
            text += f"\u2022 {ch.get('title', 'Channel')}\n"
            if ch.get('url'):
                buttons.append([InlineKeyboardButton(
                    f"\U0001f4e2 Join {ch.get('title', '')}",
                    url=ch['url']
                )])
        bot_info = await context.bot.get_me()
        buttons.append([InlineKeyboardButton(
            '\u2705 I\'ve Joined \u2014 Verify',
            url=f'https://t.me/{bot_info.username}?start=verify_{chat_id}'
        )])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def clone_callback_handler(update: Update, context):
    """Handle callback queries for clone bots - mirrors main bot functionality."""
    query = update.callback_query
    await query.answer()
    data = query.data
    db = context.application.bot_data.get('db')
    owner_id = context.application.bot_data.get('owner_id')
    user_id = query.from_user.id

    try:
        if data.startswith('verify_force_sub:'):
            chat_id = int(data.split(':')[1])
            bot_info = await context.bot.get_me()
            await query.edit_message_text(
                'Please click the button below to verify:',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton('\u2705 Verify', url=f'https://t.me/{bot_info.username}?start=verify_{chat_id}')
                ]])
            )

        elif data.startswith('clone_manage_ch:'):
            if user_id != owner_id:
                await query.answer('Access denied', show_alert=True)
                return
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            if not channel:
                await query.edit_message_text('Channel not found.')
                return
            title = channel.get('chat_title', 'Unknown')
            mode = channel.get('approve_mode', 'instant')
            auto = channel.get('auto_approve', True)
            welcome_dm = channel.get('welcome_dm_enabled', True)
            force_sub = channel.get('force_subscribe_enabled', False)
            pending = channel.get('pending_requests', 0)
            text = (f'\u2699\ufe0f {title}\n\n'
                    f'Mode: {mode}\n'
                    f'Auto-approve: {"ON" if auto else "OFF"}\n'
                    f'Welcome DM: {"ON" if welcome_dm else "OFF"}\n'
                    f'Force Subscribe: {"ON" if force_sub else "OFF"}\n'
                    f'Pending: {pending}\n')
            buttons = []
            mode_btns = []
            for m_val, m_label in [('instant', 'Instant'), ('manual', 'Manual'), ('drip', 'Drip')]:
                label = m_label + (' \u2705' if mode == m_val else '')
                mode_btns.append(InlineKeyboardButton(label, callback_data=f'clone_set_mode:{chat_id}:{m_val}'))
            buttons.append(mode_btns)
            auto_icon = '\u2705' if auto else '\u274c'
            dm_icon = '\u2705' if welcome_dm else '\u274c'
            buttons.append([
                InlineKeyboardButton(f'{auto_icon} Auto-Approve', callback_data=f'clone_toggle_auto:{chat_id}'),
                InlineKeyboardButton(f'{dm_icon} Welcome DM', callback_data=f'clone_toggle_dm:{chat_id}'),
            ])
            fsub_icon = '\u2705' if force_sub else '\u274c'
            buttons.append([
                InlineKeyboardButton(f'{fsub_icon} Force Sub', callback_data=f'clone_toggle_fsub:{chat_id}'),
                InlineKeyboardButton('\U0001f4dd Edit Welcome', callback_data=f'clone_edit_welcome:{chat_id}'),
            ])
            if pending > 0:
                buttons.append([InlineKeyboardButton(f'\u2705 Approve All ({pending})', callback_data=f'clone_batch_approve:{chat_id}')])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='clone_dashboard')])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data == 'clone_dashboard':
            if user_id != owner_id:
                await query.answer('Access denied', show_alert=True)
                return
            bot_info = await context.bot.get_me()
            channels = await db.get_owner_channels(owner_id)
            text = f'\U0001f4ca CLONE BOT DASHBOARD\n\n\U0001f916 @{bot_info.username}\n\n'
            buttons = []
            for ch in (channels or []):
                buttons.append([InlineKeyboardButton(
                    f"\u2699\ufe0f {ch['chat_title'][:25]}",
                    callback_data=f"clone_manage_ch:{ch['chat_id']}"
                )])
            if not channels:
                text += 'No channels yet.\n'
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith('clone_set_mode:'):
            if user_id != owner_id:
                return
            parts = data.split(':')
            chat_id, mode = int(parts[1]), parts[2]
            await db.update_channel_setting(chat_id, 'approve_mode', mode)
            await query.answer(f'Mode set to {mode}', show_alert=True)
            # Refresh channel view
            query.data = f'clone_manage_ch:{chat_id}'
            await clone_callback_handler(update, context)

        elif data.startswith('clone_toggle_auto:'):
            if user_id != owner_id:
                return
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('auto_approve', True)
            await db.update_channel_setting(chat_id, 'auto_approve', new_val)
            await query.answer(f'Auto-approve {"ON" if new_val else "OFF"}', show_alert=True)
            query.data = f'clone_manage_ch:{chat_id}'
            await clone_callback_handler(update, context)

        elif data.startswith('clone_toggle_dm:'):
            if user_id != owner_id:
                return
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('welcome_dm_enabled', True)
            await db.update_channel_setting(chat_id, 'welcome_dm_enabled', new_val)
            await query.answer(f'Welcome DM {"ON" if new_val else "OFF"}', show_alert=True)
            query.data = f'clone_manage_ch:{chat_id}'
            await clone_callback_handler(update, context)

        elif data.startswith('clone_toggle_fsub:'):
            if user_id != owner_id:
                return
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            new_val = not channel.get('force_subscribe_enabled', False)
            await db.update_channel_setting(chat_id, 'force_subscribe_enabled', new_val)
            await query.answer(f'Force Sub {"ON" if new_val else "OFF"}', show_alert=True)
            query.data = f'clone_manage_ch:{chat_id}'
            await clone_callback_handler(update, context)

        elif data.startswith('clone_edit_welcome:'):
            if user_id != owner_id:
                return
            chat_id = int(data.split(':')[1])
            channel = await db.get_channel(chat_id)
            current_msg = channel.get('welcome_message', 'Welcome to {channel_name}! \U0001f389') if channel else 'Not set'
            context.user_data['clone_editing_welcome_for'] = chat_id
            await query.edit_message_text(
                f'\U0001f4dd EDIT WELCOME MESSAGE\n\n'
                f'\u2501\u2501\u2501 Current Message \u2501\u2501\u2501\n\n'
                f'{current_msg}\n\n'
                f'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n'
                f'Send me the new welcome message.\n\n'
                f'Variables: {{first_name}}, {{last_name}}, {{username}}, {{channel_name}}, {{user_id}}',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('Cancel', callback_data=f'clone_manage_ch:{chat_id}')]
                ])
            )

        elif data.startswith('clone_batch_approve:'):
            if user_id != owner_id:
                return
            chat_id = int(data.split(':')[1])
            pending = await db.get_pending_requests(chat_id)
            approved = 0
            for req in (pending or []):
                try:
                    await context.bot.approve_chat_join_request(chat_id, req['user_id'])
                    await db.update_join_request_after_approve(
                        user_id=req['user_id'], chat_id=chat_id, dm_sent=False, processed_by='clone_batch')
                    approved += 1
                except Exception:
                    pass
            await query.answer(f'Approved {approved} requests!', show_alert=True)
            query.data = f'clone_manage_ch:{chat_id}'
            await clone_callback_handler(update, context)

        elif data == 'clone_broadcast':
            if user_id != owner_id:
                return
            channels = await db.get_owner_channels(owner_id)
            buttons = []
            for ch in (channels or []):
                buttons.append([InlineKeyboardButton(
                    ch['chat_title'][:30],
                    callback_data=f"clone_broadcast_to:{ch['chat_id']}"
                )])
            buttons.append([InlineKeyboardButton('\U0001f519 Back', callback_data='clone_dashboard')])
            await query.edit_message_text('Select channel to broadcast to:', reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith('clone_broadcast_to:'):
            if user_id != owner_id:
                return
            chat_id = int(data.split(':')[1])
            context.user_data['clone_broadcast_channel'] = chat_id
            await query.edit_message_text(
                'Send me the broadcast message:',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='clone_dashboard')]])
            )

        elif data == 'clone_analytics':
            if user_id != owner_id:
                return
            channels = await db.get_owner_channels(owner_id)
            text = '\U0001f4ca ANALYTICS\n\n'
            for ch in (channels or []):
                text += (f"\U0001f4e2 {ch['chat_title']}\n"
                         f"   Members: {ch.get('member_count', 0)} | Pending: {ch.get('pending_requests', 0)}\n\n")
            buttons = [[InlineKeyboardButton('\U0001f519 Back', callback_data='clone_dashboard')]]
            await query.edit_message_text(text or 'No data.', reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        logger.error(f'Error in clone callback handler: {e}')
        try:
            await query.edit_message_text(f'An error occurred: {str(e)[:200]}')
        except Exception:
            pass


async def clone_fallback_handler(update: Update, context):
    """Handle text inputs for clone bots (welcome edits, broadcasts)."""
    if not update.message or not update.message.text:
        return

    db = context.application.bot_data.get('db')
    owner_id = context.application.bot_data.get('owner_id')
    user_id = update.effective_user.id

    if user_id != owner_id or not db:
        return

    # Handle welcome message editing
    if context.user_data.get('clone_editing_welcome_for'):
        chat_id = context.user_data.pop('clone_editing_welcome_for')
        new_msg = update.message.text
        await db.update_channel_setting(chat_id, 'welcome_message', new_msg)
        await update.message.reply_text(
            f'\u2705 Welcome message updated!\n\nPreview:\n{new_msg}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data=f'clone_manage_ch:{chat_id}')]])
        )
        return

    # Handle broadcast
    if context.user_data.get('clone_broadcast_channel'):
        chat_id = context.user_data.pop('clone_broadcast_channel')
        message = update.message.text
        users = await db.get_channel_users(chat_id)
        sent = 0
        failed = 0
        for u in (users or []):
            try:
                await context.bot.send_message(u['user_id'], message)
                sent += 1
            except Exception:
                failed += 1
        await update.message.reply_text(
            f'\U0001f4e2 Broadcast complete!\n\nSent: {sent}\nFailed: {failed}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Back', callback_data='clone_dashboard')]])
        )
        return


async def clone_join_request_handler(update: Update, context):
    """Handle join requests for clone bots - mirrors main bot logic."""
    try:
        join_request = update.chat_join_request
        user = join_request.from_user
        chat = join_request.chat
        chat_id = chat.id
        user_id = user.id

        db = context.application.bot_data.get('db')
        owner_id = context.application.bot_data.get('owner_id')
        clone_id = context.application.bot_data.get('clone_id')

        if not db:
            logger.error(f'Clone {clone_id}: DB not available')
            try:
                await join_request.approve()
            except Exception:
                pass
            return

        # Save join request
        try:
            await db.save_join_request(
                user_id=user_id,
                chat_id=chat_id,
                username=user.username,
                first_name=user.first_name,
                user_language=user.language_code,
            )
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error saving join request: {e}')

        # Save/update end user
        try:
            await db.upsert_end_user(
                user_id=user_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                source='clone_join_request',
                source_channel=chat_id,
            )
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error upserting end user: {e}')

        # Get channel settings
        channel = await db.get_channel(chat_id)

        # If channel not in DB, register it under the clone owner
        if not channel:
            try:
                await db.upsert_channel(
                    chat_id=chat_id,
                    owner_id=owner_id,
                    chat_title=chat.title,
                    chat_username=chat.username,
                )
                channel = await db.get_channel(chat_id)
            except Exception as e:
                logger.error(f'Clone {clone_id}: Error registering channel: {e}')

        if not channel:
            try:
                await join_request.approve()
            except Exception:
                pass
            return

        # Update pending count
        try:
            pending_count = await db.get_pending_count(chat_id)
            await db.update_channel_setting(chat_id, 'pending_requests', pending_count)
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error updating pending count: {e}')

        approve_mode = channel.get('approve_mode', 'instant')
        auto_approve = channel.get('auto_approve', True)

        if not auto_approve or approve_mode == 'manual':
            # Notify owner via the main bot
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                parent_app = context.application.bot_data.get('parent_app')
                if parent_app:
                    await parent_app.bot.send_message(
                        owner_id,
                        f'\U0001f4cb New join request for {chat.title} (via clone)\n'
                        f'User: {user.first_name} (@{user.username or "no_username"})\n'
                        f'ID: {user_id}',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton('\u2705 Approve', callback_data=f'approve_one:{chat_id}:{user_id}'),
                             InlineKeyboardButton('\u274c Decline', callback_data=f'decline_one:{chat_id}:{user_id}')]
                        ])
                    )
            except Exception as e:
                logger.warning(f'Clone {clone_id}: Could not notify owner: {e}')
            return

        if approve_mode == 'drip':
            return

        # Check force subscribe
        if channel.get('force_subscribe_enabled') and channel.get('force_subscribe_channels'):
            required_channels_raw = channel['force_subscribe_channels']
            if isinstance(required_channels_raw, str):
                try:
                    required_channels = json.loads(required_channels_raw)
                except (ValueError, TypeError):
                    required_channels = []
            elif isinstance(required_channels_raw, list):
                required_channels = required_channels_raw
            else:
                required_channels = []

            all_joined = True
            not_joined = []
            for req_ch in required_channels:
                try:
                    member = await context.bot.get_chat_member(req_ch['chat_id'], user_id)
                    if member.status in ('left', 'kicked'):
                        all_joined = False
                        not_joined.append(req_ch)
                except Exception:
                    all_joined = False
                    not_joined.append(req_ch)

            if not all_joined:
                try:
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    fsub_text = (f'\U0001f44b Welcome! To join {chat.title}, '
                            f'please join these channels first:\n\n')
                    buttons = []
                    for ch in not_joined:
                        fsub_text += f"\u2022 {ch.get('title', 'Channel')}\n"
                        if ch.get('url'):
                            buttons.append([InlineKeyboardButton(
                                f"\U0001f4e2 Join {ch.get('title', '')}",
                                url=ch['url']
                            )])
                    bot_info = await context.bot.get_me()
                    buttons.append([InlineKeyboardButton(
                        "\u2705 I've Joined \u2014 Verify Me",
                        url=f'https://t.me/{bot_info.username}?start=verify_{chat_id}'
                    )])
                    await context.bot.send_message(
                        user_id, fsub_text,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                    await db.update_join_request_force_sub(user_id, chat_id, True)
                except Exception as e:
                    logger.warning(f'Clone {clone_id}: Could not send force sub DM: {e}')
                    await join_request.approve()
                return

        # Auto-approve: send welcome DM then approve
        dm_sent = False
        if channel.get('welcome_dm_enabled', True):
            try:
                welcome_text = channel.get('welcome_message', 'Welcome to {channel_name}! \U0001f389')
                welcome_text = welcome_text.replace('{first_name}', user.first_name or 'there')
                welcome_text = welcome_text.replace('{last_name}', user.last_name or '')
                welcome_text = welcome_text.replace('{username}', f'@{user.username}' if user.username else 'there')
                welcome_text = welcome_text.replace('{user_id}', str(user_id))
                welcome_text = welcome_text.replace('{channel_name}', chat.title or '')
                await context.bot.send_message(user_id, welcome_text)
                dm_sent = True
            except Exception as e:
                logger.warning(f'Clone {clone_id}: DM failed to {user_id}: {e}')

        try:
            await join_request.approve()
        except Exception as e:
            logger.error(f'Clone {clone_id}: Failed to approve {user_id}: {e}')

        try:
            await db.update_join_request_after_approve(
                user_id=user_id,
                chat_id=chat_id,
                dm_sent=dm_sent,
                processed_by='clone',
            )
        except Exception as e:
            logger.error(f'Clone {clone_id}: Error updating after approve: {e}')

    except Exception as e:
        logger.exception(f'CRITICAL: Error in clone join_request_handler: {e}')
        try:
            await update.chat_join_request.approve()
        except Exception:
            pass
