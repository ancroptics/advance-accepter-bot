import functools
import logging
from telegram import Update
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)


def admin_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in config.SUPERADMIN_IDS:
            await update.effective_message.reply_text('\u26d4 This command is for admins only.')
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# Alias
superadmin_only = admin_only


def owner_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        # Superadmin bypass
        if user_id in config.SUPERADMIN_IDS:
            return await func(update, context, *args, **kwargs)
        db = context.application.bot_data.get('db')
        if not db:
            await update.effective_message.reply_text('\u274c Database not available.')
            return
        owner = await db.get_owner(user_id)
        if not owner:
            await update.effective_message.reply_text('\u26d4 This command is for channel owners only.')
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# Alias
channel_owner_only = owner_only


def registered_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        db = context.application.bot_data.get('db')
        if not db:
            await update.effective_message.reply_text('\u274c Database not available.')
            return
        owner = await db.get_owner(user_id)
        if not owner:
            await update.effective_message.reply_text('\U0001f44b Please /start the bot first to register.')
            return
        context.user_data['db_user'] = owner
        return await func(update, context, *args, **kwargs)
    return wrapper


def channel_context(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        db = context.application.bot_data.get('db')
        channel_id = context.user_data.get('active_channel_id')
        if not channel_id:
            await update.effective_message.reply_text('\u26a0\ufe0f No channel selected. Use /channels to pick one.')
            return
        channel = await db.get_channel(channel_id)
        # Superadmin bypass
        if user_id in config.SUPERADMIN_IDS:
            context.user_data['channel_id'] = channel_id
            return await func(update, context, *args, **kwargs)
        if not channel or channel['owner_id'] != user_id:
            await update.effective_message.reply_text('\u26d4 You do not own this channel.')
            return
        context.user_data['channel_id'] = channel_id
        return await func(update, context, *args, **kwargs)
    return wrapper


def premium_required(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        # Superadmin bypass - full access to all features
        if user_id in config.SUPERADMIN_IDS:
            return await func(update, context, *args, **kwargs)
        db = context.application.bot_data.get('db')
        if not db:
            await update.effective_message.reply_text('\u274c Database not available.')
            return
        owner = await db.get_owner(user_id)
        if not owner or owner.get('tier', 'free') == 'free':
            await update.effective_message.reply_text('\u2b50 This feature requires Premium. Use /dashboard to upgrade.')
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
