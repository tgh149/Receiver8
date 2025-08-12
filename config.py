# START OF FILE config.py

# Your bot's token from BotFather. This is the only mandatory value.
BOT_TOKEN = "7482708717:AAGBoyi1M5P2Xe9PQ5vM5ErSOmVLZU3ccnI"  # Replace with your bot's token

# The Telegram ID of the user who will be the first super-admin.
# The bot will automatically grant this user admin privileges on first run.
INITIAL_ADMIN_ID = 6158106622

# Filename for the persistent scheduler database
SCHEDULER_DB_FILE = "scheduler.sqlite"

# --- NEW SETTINGS FOR SESSION FORWARDING ---
# These lines were missing.

# (Optional) The ID of the Telegram group where session files should be sent.
# The group MUST have "Topics" enabled.
# To get this ID, forward a message from your group to a bot like @userinfobot
# It will be a negative number, e.g., -1001234567890
SESSION_LOG_CHANNEL_ID = -1002528192959 # <<-- IMPORTANT: REPLACE WITH YOUR REAL GROUP ID

# (Optional) Set to True to enable sending session files to the log group.
# Set to False to disable this feature.
ENABLE_SESSION_FORWARDING = True