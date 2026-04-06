import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

logger = logging.getLogger(__name__)

TEMPLATE_NAME = 200
TEMPLATE_CONTENT = 201


async def show_templates_menu(update, context):
    """Show templates list with create/manage options."""
    query = update.callback_query
    db = context.application.bot_data.get('db')
    user_id = query.from_user.id

    try:
        templates = await db.get_templates(user_id)
    except Exception as e:
        logger.error(f"Error fetching templates: {e}")
        templates = []

    text = '📝 MESSAGE TEMPLATES\n\n'
    text += 'Templates let you save messages for quick reuse in broadcasts.\n\n'

    buttons = []
    if templates:
        text += f'You have {len(templates)} template(s):\n\n'
        for t in templates:
            name = t.get("name", "Untitled")
            preview = (t.get("content", "") or "")[:40]
            if len(t.get("content", "") or "") > 40:
                preview += "..."
            text += f'📄 {name}\n   {preview}\n\n'
            buttons.append([
                InlineKeyboardButton(f'📄 {name}', callback_data=f'view_template:{t["template_id"]}'),
                InlineKeyboardButton('🗑', callback_data=f'delete_template:{t["template_id"]}'),
            ])
    else:
        text += '📭 No templates yet.\n\nCreate your first template to get started!'

    buttons.append([InlineKeyboardButton('➕ Create Template', callback_data='create_template')])
    buttons.append([InlineKeyboardButton('🔙 Back to Dashboard', callback_data='dashboard')])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def view_template_handler(update, context):
    """View a single template with use/delete options."""
    query = update.callback_query
    db = context.application.bot_data.get('db')
    template_id = int(query.data.split(':')[1])

    template = await db.get_template(template_id)
    if not template:
        await query.answer('Template not found', show_alert=True)
        return

    text = f'📄 TEMPLATE: {template["name"]}\n\n'
    text += f'{template.get("content", "(empty)")}\n\n'
    text += f'Type: {template.get("content_type", "text").title()}'

    buttons = [
        [InlineKeyboardButton('🗑 Delete', callback_data=f'delete_template:{template_id}')],
        [InlineKeyboardButton('🔙 Back to Templates', callback_data='templates_menu')],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def delete_template_handler(update, context):
    """Delete a template."""
    query = update.callback_query
    db = context.application.bot_data.get('db')
    template_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    success = await db.delete_template(template_id, user_id)
    if success:
        await query.answer('✅ Template deleted!', show_alert=True)
    else:
        await query.answer('❌ Could not delete template', show_alert=True)

    # Refresh list
    await show_templates_menu(update, context)


async def start_create_template(update, context):
    """Start template creation flow."""
    query = update.callback_query
    await query.answer()
    context.user_data['creating_template'] = True

    await query.edit_message_text(
        '📝 CREATE NEW TEMPLATE\n\n'
        'Step 1/2: Send me a name for this template.\n\n'
        'Example: Welcome Message, Promo Offer, Update Notice\n\n'
        'Send /cancel to abort.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('❌ Cancel', callback_data='templates_menu')]
        ])
    )
    return TEMPLATE_NAME


async def handle_template_name(update, context):
    """Handle template name input."""
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text('Please send a valid name.')
        return TEMPLATE_NAME

    context.user_data['template_name'] = name
    await update.message.reply_text(
        f'📝 Template name: {name}\n\n'
        'Step 2/2: Now send the message content for this template.\n\n'
        'This can be any text message. You can use Telegram formatting.\n\n'
        'Send /cancel to abort.',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('❌ Cancel', callback_data='templates_menu')]
        ])
    )
    return TEMPLATE_CONTENT


async def handle_template_content(update, context):
    """Handle template content input."""
    content = update.message.text.strip()
    if not content:
        await update.message.reply_text('Please send some content.')
        return TEMPLATE_CONTENT

    db = context.application.bot_data.get('db')
    user_id = update.effective_user.id
    name = context.user_data.pop('template_name', 'Untitled')
    context.user_data.pop('creating_template', None)

    template_id = await db.create_template(user_id, name, content)
    if template_id:
        await update.message.reply_text(
            f'✅ Template "{name}" created!\n\n'
            f'Preview:\n{content[:200]}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📝 View Templates', callback_data='templates_menu')],
                [InlineKeyboardButton('📊 Dashboard', callback_data='dashboard')],
            ])
        )
    else:
        await update.message.reply_text(
            '❌ Failed to create template. Please try again.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📝 Templates', callback_data='templates_menu')],
            ])
        )
    return ConversationHandler.END


template_conv_handler = None  # Will be created in register_handlers
