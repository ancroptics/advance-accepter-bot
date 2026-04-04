import logging
import asyncio
import json
from telegram import Bot, Update
from telegram.ext import Application, ChatJoinRequestHandler, ChatMemberHandler
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

            # Register join request handler for the clone
            clone_app.add_handler(ChatJoinRequestHandler(clone_join_request_handler))

            await clone_app.initialize()
            await clone_app.start()
            await clone_app.updater.start_polling(
                allowed_updates=['chat_join_request', 'my_chat_member'],
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
                    buttons.append([InlineKeyboardButton(
                        "\u2705 I've Joined \u2014 Verify Me",
                        callback_data=f'verify_force_sub:{chat_id}'
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
