import functools
import logging
from telegram import Update
from telegram.ext import ContextTypes
from database.models import get_user, is_channel_owner
import config

logger = logging.getLogger(__name__)


def admin_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_IDS:
            await update.message.reply_text('⛔ This command is for admins only.')
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def owner_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        db = context.bot_data.get('db')
        if not db:
            await update.message.reply_text('❌ Database not available.')
            return
        user = await get_user(db, user_id)
        if not user or user.get('role') not in ('owner', 'admin'):
            await update.message.reply_text('⛔ This command is for channel owners only.')
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def registered_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        db = context.bot_data.get('db')
        if not db:
            await update.message.reply_text('❌ Database not available.')
            return
        user = await get_user(db, user_id)
        if not user:
            await update.message.reply_text(
                '👋 Please /start the bot first to register.'
            )
            return
        context.user_data['db_user'] = user
        return await func(update, context, *args, **kwargs)
    return wrapper


def channel_context(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        db = context.bot_data.get('db')
        channel_id = context.user_data.get('active_channel_id')
        if not channel_id:
            await update.message.reply_text(
                '⚠️ No channel selected. Use /channels to pick one.'
            )
            return
        if not await is_channel_owner(db, user_id, channel_id):
            await update.message.reply_text('⛔ You do not own this channel.')
            return
        context.user_data['channel_id'] = channel_id
        return await func(update, context, *args, **kwargs)
    return wrapper
