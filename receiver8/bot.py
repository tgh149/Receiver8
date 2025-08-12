# START OF FILE bot.py
import logging
from logging.handlers import RotatingFileHandler
import asyncio
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Bot, BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from rich.logging import RichHandler

import database
# --- MODIFIED: Import from the new, cleaner config ---
from config import get_config
# --- MODIFIED: Import all handlers ---
from handlers import admin, start, commands, login, callbacks, proxy_chat
from handlers.admin import file_manager as admin_file_manager

# --- Logging Setup ---
# --- MODIFIED: Use DATA_DIR for logs ---
DATA_DIR = os.environ.get("RENDER_DISK_PATH", ".")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

log_level = logging.INFO
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
# Console Handler (Rich)
rich_handler = RichHandler(rich_tracebacks=True, markup=True, show_path=False, log_time_format="[%X]")
root_logger.addHandler(rich_handler)
# File Handler
file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler = RotatingFileHandler(os.path.join(LOGS_DIR, "bot_activity.log"), maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)
# Silence noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- NEW: Health Check Server for Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running.")

def run_health_check_server():
    """Runs a simple HTTP server in a separate thread for health checks."""
    # Render dynamically assigns a port, which is exposed via the PORT env var.
    # We'll use 10000 as a default for local testing.
    port = int(os.environ.get("PORT", 10000))
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    logger.info(f"Health check server starting on port {port}...")
    httpd.serve_forever()
# --- END NEW ---

async def recurring_account_check_job(bot_token: str):
    """This recurring job checks for accounts that need attention."""
    logger.info("Cron job: Running periodic account checks...")
    bot = Bot(token=bot_token)
    reprocessing_accounts = database.get_accounts_for_reprocessing()
    stuck_accounts = database.get_stuck_pending_accounts()

    if reprocessing_accounts:
        logger.info(f"Cron job: Found {len(reprocessing_accounts)} account(s) for 24h reprocessing.")
        tasks = [login.reprocess_account(bot, acc) for acc in reprocessing_accounts]
        await asyncio.gather(*tasks)

    if stuck_accounts:
        logger.info(f"Cron job: Found {len(stuck_accounts)} stuck account(s). Retrying initial check.")
        tasks = [
            login.schedule_initial_check(
                bot_token=bot_token,
                user_id_str=str(acc['user_id']),
                chat_id=acc['user_id'],
                phone_number=acc['phone_number'],
                job_id=acc['job_id'],
                prompt_message_id=None # No message to edit for cron jobs
            ) for acc in stuck_accounts
        ]
        await asyncio.gather(*tasks)

    if not reprocessing_accounts and not stuck_accounts:
        logger.info("Cron job: No accounts needed attention.")
    logger.info("Cron job: Finished periodic account checks.")


async def post_init(application: Application):
    """Tasks to run after the bot is initialized but before it starts polling."""
    logger.info("[bold blue]Running post-initialization tasks...[/bold blue]")

    # --- MODIFIED: Use the config object ---
    config = get_config()

    database.init_db()
    logger.info("[green]Database schema checked/initialized.[/green]")

    # Persist forwarding settings from config into the database
    database.set_setting('session_log_channel_id', str(config.SESSION_LOG_CHANNEL_ID))
    database.set_setting('enable_session_forwarding', str(config.ENABLE_SESSION_FORWARDING))
    logger.info("[green]Session forwarding settings synced to database.[/green]")

    if config.INITIAL_ADMIN_ID:
        if database.add_admin(config.INITIAL_ADMIN_ID):
             logger.info(f"[green]Granted admin privileges to initial admin ID: {config.INITIAL_ADMIN_ID}[/green]")
             database.log_admin_action(config.INITIAL_ADMIN_ID, "SYSTEM_INIT", "Initial admin created.")
        else:
             logger.info(f"[green]Initial admin ID {config.INITIAL_ADMIN_ID} already exists.[/green]")

    application.bot_data.update(database.get_all_settings())
    application.bot_data['countries_config'] = database.get_countries_config()
    application.bot_data['scheduler_db_file'] = config.SCHEDULER_DB_FILE # Store for potential reset
    application.bot_data['initial_admin_id'] = config.INITIAL_ADMIN_ID # Store for potential reset
    logger.info("[green]Loaded dynamic settings and country configs into bot context.[/green]")

    if not database.get_all_api_credentials():
        default_api_id = application.bot_data.get('api_id', '25707049')
        default_api_hash = application.bot_data.get('api_hash', '676a65f1f7028e4d969c628c73fbfccc')
        database.add_api_credential(default_api_id, default_api_hash)
        logger.info(f"[green]Added default API credential to rotation pool.[/green]")

    user_commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("balance", "💼 Check your balance"),
        BotCommand("cap", "📋 View available countries & rates"),
        BotCommand("help", "🆘 Get help and info"),
        BotCommand("rules", "📜 Read the bot rules"),
        BotCommand("cancel", "❌ Cancel the current operation"),
    ]
    admin_commands = user_commands + [
        BotCommand("admin", "👑 Access Admin Panel"),
        BotCommand("zip", "⚡ Quick download (new/old sessions)")
    ]
    await application.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    logger.info("[green]Default user commands have been set.[/green]")

    admin_count = 0
    for admin_user in database.get_all_admins():
        try:
            await application.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_user['telegram_id']))
            admin_count += 1
        except Exception as e:
            logger.warning(f"Could not set commands for admin {admin_user['telegram_id']}: {e}")
    if admin_count > 0: logger.info(f"[green]Admin-specific commands have been set for {admin_count} admins.[/green]")

    jobstores = {'default': SQLAlchemyJobStore(url=f'sqlite:///{config.SCHEDULER_DB_FILE}')}
    scheduler = AsyncIOScheduler(timezone="UTC", jobstores=jobstores, job_defaults={'coalesce': True, 'misfire_grace_time': 300})
    application.bot_data["scheduler"] = scheduler
    scheduler.start()
    logger.info("[green]Persistent APScheduler started.[/green]")
    scheduler.add_job(recurring_account_check_job, 'interval', minutes=15, args=[config.BOT_TOKEN], id='account_check_job', replace_existing=True)
    logger.info("[green]Added recurring job for account maintenance.[/green]")
    scheduler.add_job(database.clear_old_topics, 'cron', hour=0, minute=5, id='clear_topics_job', replace_existing=True)
    logger.info("[green]Added daily job to clear old topic data.[/green]")


async def post_shutdown(application: Application):
    """Tasks to run on graceful shutdown."""
    scheduler = application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[yellow]APScheduler shut down.[/yellow]")

def main() -> None:
    """Start the bot."""
    logger.info("[bold cyan]Bot starting...[/bold cyan]")
    
    # --- NEW: Start the health check server ---
    health_check_thread = threading.Thread(target=run_health_check_server, daemon=True)
    health_check_thread.start()

    # --- MODIFIED: Use the config object ---
    config = get_config()
    
    application = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # --- Register Handlers ---
    # Group 0: Admin Handlers (Highest Priority)
    admin_handlers = admin.get_admin_handlers()
    # Add the /zip command handler to the admin group
    admin_handlers.append(CommandHandler("zip", admin_file_manager.zip_command_handler, filters=admin.admin_filter))

    application.add_handlers(admin_handlers, group=0)
    logger.info(f"[yellow]Registered {len(admin_handlers)} admin handlers in group 0.[/yellow]")

    # Group 1: Admin P2P Chat Handler
    support_admin_id_str = application.bot_data.get('support_id')
    if support_admin_id_str and support_admin_id_str.isdigit():
        support_admin_id = int(support_admin_id_str)
        admin_chat_handler = MessageHandler(
            filters.User(user_id=support_admin_id) & filters.REPLY & ~filters.COMMAND,
            proxy_chat.reply_to_user_by_reply
        )
        application.add_handler(admin_chat_handler, group=1)
        logger.info("[yellow]Registered admin P2P reply handler in group 1.[/yellow]")

    # Group 2: User-facing Handlers
    withdrawal_handler = callbacks.get_withdrawal_conv_handler()
    
    user_handlers = [
        CommandHandler("start", start.start),
        CommandHandler("balance", commands.balance_cmd),
        CommandHandler("cap", commands.cap_command),
        CommandHandler("help", commands.help_command),
        CommandHandler("rules", commands.rules_command),
        CommandHandler("cancel", commands.cancel_operation),
        CommandHandler("reply", proxy_chat.reply_to_user_by_command), # Manual admin reply
        withdrawal_handler, # Add the conversation handler here
        CallbackQueryHandler(callbacks.handle_callback_query),
        MessageHandler(filters.TEXT & ~filters.COMMAND, commands.on_text_message),
    ]
    application.add_handlers(user_handlers, group=2)
    logger.info(f"[yellow]Registered {len(user_handlers)} user handlers in group 2.[/yellow]")

    logger.info("[bold green]Bot is ready and polling for updates...[/bold green]")
    application.run_polling()

if __name__ == "__main__":
    main()