# START OF FILE api/index.py
import asyncio
import logging
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import database
from config import BOT_TOKEN, INITIAL_ADMIN_ID, SESSION_LOG_CHANNEL_ID, ENABLE_SESSION_FORWARDING
from handlers import admin, start, commands, login, callbacks, proxy_chat
from handlers.admin import file_manager as admin_file_manager

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Initialize Application ---
application = ApplicationBuilder().token(BOT_TOKEN).build()

# --- One-time Setup Logic (replaces post_init) ---
def initial_setup():
    logger.info("Running one-time initial setup...")
    database.init_db()
    database.set_setting('session_log_channel_id', str(SESSION_LOG_CHANNEL_ID))
    database.set_setting('enable_session_forwarding', str(ENABLE_SESSION_FORWARDING))
    if INITIAL_ADMIN_ID:
        if database.add_admin(INITIAL_ADMIN_ID):
             logger.info(f"Granted admin privileges to initial admin ID: {INITIAL_ADMIN_ID}")
             database.log_admin_action(INITIAL_ADMIN_ID, "SYSTEM_INIT", "Initial admin created.")
    
    application.bot_data.update(database.get_all_settings())
    application.bot_data['countries_config'] = database.get_countries_config()
    
    if not database.get_all_api_credentials():
        default_api_id = application.bot_data.get('api_id', '25707049')
        default_api_hash = application.bot_data.get('api_hash', '676a65f1f7028e4d969c628c73fbfccc')
        database.add_api_credential(default_api_id, default_api_hash)
    logger.info("Initial setup complete.")

# Run setup once on startup
initial_setup()

# --- Register Handlers ---
admin_handlers = admin.get_admin_handlers()
admin_handlers.append(CommandHandler("zip", admin_file_manager.zip_command_handler, filters=admin.admin_filter))
application.add_handlers(admin_handlers, group=0)

support_admin_id_str = application.bot_data.get('support_id')
if support_admin_id_str and support_admin_id_str.isdigit():
    support_admin_id = int(support_admin_id_str)
    application.add_handler(MessageHandler(
        filters.User(user_id=support_admin_id) & filters.REPLY & ~filters.COMMAND,
        proxy_chat.reply_to_user_by_reply
    ), group=1)

withdrawal_handler = callbacks.get_withdrawal_conv_handler()
user_handlers = [
    CommandHandler("start", start.start),
    CommandHandler("balance", commands.balance_cmd),
    CommandHandler("cap", commands.cap_command),
    CommandHandler("help", commands.help_command),
    CommandHandler("rules", commands.rules_command),
    CommandHandler("cancel", commands.cancel_operation),
    CommandHandler("reply", proxy_chat.reply_to_user_by_command),
    withdrawal_handler,
    CallbackQueryHandler(callbacks.handle_callback_query),
    MessageHandler(filters.TEXT & ~filters.COMMAND, commands.on_text_message),
]
application.add_handlers(user_handlers, group=2)

# --- Flask App ---
app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook():
    """Endpoint to receive updates from Telegram."""
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, application.bot)
    asyncio.run(application.process_update(update))
    return 'OK', 200

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """One-time endpoint to set the webhook URL."""
    # VERCEL_URL is a system environment variable provided by Vercel
    webhook_url = f"https://{os.environ['VERCEL_URL']}"
    was_set = asyncio.run(application.bot.set_webhook(url=webhook_url))
    if was_set:
        return f"Webhook set to {webhook_url}"
    else:
        return "Webhook setup failed"