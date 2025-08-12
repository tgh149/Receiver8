# START OF FILE config.py
import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        # --- Essential ---
        self.BOT_TOKEN = os.environ.get("BOT_TOKEN")
        if not self.BOT_TOKEN:
            raise ValueError("FATAL: BOT_TOKEN environment variable is not set.")

        # This is the single directory where all persistent data will be stored on Render.
        # It defaults to the current directory '.' for local testing.
        self.DATA_DIR = os.environ.get("RENDER_DISK_PATH", ".")
        
        # --- Optional but Recommended ---
        # The Telegram ID of the user who will be the first super-admin.
        # It's recommended to set this as an environment variable.
        self.INITIAL_ADMIN_ID = int(os.environ.get("INITIAL_ADMIN_ID", 0))

        # --- File Paths (now point to DATA_DIR) ---
        self.SCHEDULER_DB_FILE = os.path.join(self.DATA_DIR, "scheduler.sqlite")
        self.DB_FILE = os.path.join(self.DATA_DIR, "bot.db")
        self.SESSIONS_DIR = os.path.join(self.DATA_DIR, "sessions")

        # --- Session Forwarding Settings ---
        self.SESSION_LOG_CHANNEL_ID = int(os.environ.get("SESSION_LOG_CHANNEL_ID", 0))
        self.ENABLE_SESSION_FORWARDING = os.environ.get("ENABLE_SESSION_FORWARDING", "False").lower() in ("true", "1", "t")

        # Create directories if they don't exist
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.SESSIONS_DIR, exist_ok=True)

        if not self.INITIAL_ADMIN_ID:
            logger.warning("INITIAL_ADMIN_ID is not set. No admin will be created on first run.")
        if not self.SESSION_LOG_CHANNEL_ID and self.ENABLE_SESSION_FORWARDING:
            logger.warning("ENABLE_SESSION_FORWARDING is True, but SESSION_LOG_CHANNEL_ID is not set.")


# Use a cached function to avoid re-reading environment variables constantly.
@lru_cache()
def get_config() -> Config:
    """Returns a cached instance of the configuration settings."""
    return Config()