# START OF FILE web_server.py
import threading
import logging
from flask import Flask
from bot import main as start_bot  # Import the main function from your bot.py

# --- Logging Setup ---
# Set up a basic logger for the web server part
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # Silence the default Flask startup messages
logger = logging.getLogger(__name__)

# --- Flask App ---
app = Flask(__name__)

@app.route('/')
def index():
    """A simple endpoint to respond to pings."""
    return "Bot is alive and running!"

def run_web_server():
    """Runs the Flask web server."""
    # Use 0.0.0.0 to be accessible within Render's network
    # Render provides the PORT environment variable
    import os
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# --- Main Execution ---
if __name__ == "__main__":
    # Run the bot in a separate thread
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.start()
    logger.info("[bold green]Telegram bot started in a background thread.[/bold green]")
    
    # Run the web server in the main thread
    logger.info("[bold blue]Starting keep-alive web server...[/bold blue]")
    run_web_server()