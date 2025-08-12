# START OF FILE api/cron.py
import asyncio
import logging
from flask import Flask, request
from telegram import Bot

import database
from config import BOT_TOKEN
from handlers import login

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Cron Job Logic ---
async def run_account_check_job():
    """
    This recurring job checks for accounts that need attention.
    It is the serverless replacement for the old apscheduler job.
    """
    logger.info("Vercel Cron: Running periodic account checks...")
    bot = Bot(token=BOT_TOKEN)
    bot_data = database.get_all_settings()

    # --- NEW: Combined logic to handle all pending/stuck checks ---
    # This single query finds all accounts that are past their confirmation time.
    # It replaces the need for scheduling one-off jobs.
    accounts_to_check = database.fetch_all(
        "SELECT * FROM accounts WHERE status = 'pending_confirmation' AND reg_time <= datetime('now', '-10 minutes')"
    )
    
    reprocessing_accounts = database.get_accounts_for_reprocessing()

    tasks = []
    if accounts_to_check:
        logger.info(f"Vercel Cron: Found {len(accounts_to_check)} pending accounts to finalize.")
        for acc in accounts_to_check:
            # We don't have the original message ID here, which is fine.
            # The button will remain, but the user can click it to see the final status.
            tasks.append(login.schedule_initial_check(BOT_TOKEN, str(acc['user_id']), acc['user_id'], acc['phone_number'], acc['job_id'], None))
    
    if reprocessing_accounts:
        logger.info(f"Vercel Cron: Found {len(reprocessing_accounts)} accounts for 24h reprocessing.")
        tasks.extend([login.reprocess_account(bot, acc) for acc in reprocessing_accounts])

    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.info("Vercel Cron: No accounts needed attention.")

    logger.info("Vercel Cron: Finished periodic account checks.")


# --- Flask App for Cron ---
app = Flask(__name__)

@app.route('/cron', methods=['GET'])
def cron_handler():
    """Endpoint that Vercel calls on a schedule."""
    job_name = request.args.get('job')
    
    if job_name == 'account_check':
        asyncio.run(run_account_check_job())
        return 'OK: Account check job finished.', 200
    elif job_name == 'clear_topics':
        database.clear_old_topics()
        return 'OK: Topic cleanup finished.', 200
    
    return 'No job specified.', 400