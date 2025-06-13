import os
import logging
import requests
import time
from datetime import datetime
import schedule
from PIL import Image
from io import BytesIO
import telebot
import asyncio
from pyppeteer import launch
from pyppeteer.errors import TimeoutError as PyppeteerTimeoutError
from dotenv import load_dotenv
import threading
from flask import Flask, jsonify

# --- Configuration ---

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Load environment variables from .env file
load_dotenv()

# --- Environment Variables & Constants ---

# Telegram Bot Configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Bot Behavior Configuration
SCHEDULE_INTERVAL_HOURS = int(os.getenv('SCHEDULE_INTERVAL_HOURS', '4'))
DEFAULT_TIMEFRAME = os.getenv('DEFAULT_TIMEFRAME', '24 hour')
VALID_TIMEFRAMES = ["24 hour", "12 hour", "4 hour", "1 hour", "1 week", "1 month", "3 month"]
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper() # <-- SUGGESTION: Configurable log level

# Pyppeteer/Browser Configuration
VIEWPORT = {'width': 2700, 'height': 1475, 'deviceScaleFactor': 2}
PYPPETEER_LAUNCH_OPTIONS = {
    'executablePath': os.getenv('CHROME_BIN'), # For platforms like Heroku/Koyeb with buildpacks
    'args': ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    'headless': True
}

# --- Initialization ---

# Configure logging with the level from environment variables
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./logs/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if not TOKEN or not CHANNEL_ID:
    logger.error("FATAL: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set in .env file.")
    exit(1)

# Initialize Telegram bot
bot = telebot.TeleBot(TOKEN)

# --- Core Logic (No changes from previous version) ---

async def capture_coinglass_heatmap(time_period: str = "24 hour") -> str | None:
    """Captures the Coinglass liquidation heatmap using pyppeteer."""
    browser = None
    filename = None
    logger.info(f"Attempting to capture heatmap for timeframe: '{time_period}'")
    try:
        browser = await launch(PYPPETEER_LAUNCH_OPTIONS)
        page = await browser.newPage()
        await page.setViewport(VIEWPORT)
        
        logger.info("Navigating to Coinglass...")
        await page.goto('https://www.coinglass.com/pro/futures/LiquidationHeatMap', {'waitUntil': 'networkidle2', 'timeout': 60000})
        logger.info("Page loaded. Waiting for chart elements.")

        dropdown_selector = 'div.MuiSelect-root button.MuiSelect-button'
        await page.waitForSelector(dropdown_selector, {'visible': True, 'timeout': 30000})

        current_time_period = await page.evaluate(f"document.querySelector('{dropdown_selector}').textContent.trim()")
        if current_time_period != time_period:
            logger.info(f"Current timeframe is '{current_time_period}', changing to '{time_period}'.")
            await page.click(dropdown_selector)
            await asyncio.sleep(1)
            
            option_selector_js = f"""
                Array.from(document.querySelectorAll('li[role=option]'))
                     .find(el => el.textContent.includes('{time_period}'))
                     .click()
            """
            await page.evaluate(option_selector_js)
            logger.info("Timeframe changed. Waiting for chart to update...")
            await asyncio.sleep(5)
        else:
            logger.info(f"Timeframe already set to '{time_period}'.")

        chart_selector = 'div.echarts-for-react'
        await page.waitForSelector(chart_selector, {'visible': True, 'timeout': 20000})
        chart_element = await page.querySelector(chart_selector)
        
        if not chart_element:
            logger.error("Could not find the chart element after loading.")
            return None

        png_data = await chart_element.screenshot({'type': 'png'})
        
        filename = f"heatmap_{time_period.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        with open(filename, 'wb') as f:
            f.write(png_data)
        
        logger.info(f"Successfully captured and saved heatmap to {filename}")
        return filename

    except PyppeteerTimeoutError as e:
        logger.error(f"Timeout error during heatmap capture: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during heatmap capture: {e}", exc_info=True)
        return None
    finally:
        if browser:
            await browser.close()
            logger.info("Browser closed.")

def get_bitcoin_price() -> str | None:
    """Fetches the current Bitcoin price from CoinGecko."""
    try:
        url = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd'
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        price = data.get('bitcoin', {}).get('usd')
        return f"${price:,.2f}" if price else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching BTC price from CoinGecko: {e}")
    return None

def process_and_send_heatmap(chat_id: str | int, time_period: str):
    """A generic function to capture, format, and send a heatmap image."""
    filename = None
    try:
        filename = asyncio.run(capture_coinglass_heatmap(time_period))
        
        if not filename:
            bot.send_message(chat_id, f'❌ Failed to capture the {time_period} Bitcoin liquidation heatmap.')
            return

        price = get_bitcoin_price()
        time_period_title = time_period.replace(" hour", "-Hour").replace(" week", "-Week").replace(" month", "-Month")
        caption = f"📊 {time_period_title} Bitcoin Liquidation Heatmap\n"
        caption += f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
        if price:
            caption += f"\n💰 BTC Price: {price}"

        with open(filename, 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=caption)
        
        logger.info(f"Heatmap sent successfully to chat_id: {chat_id}")

    except Exception as e:
        logger.error(f"Error in process_and_send_heatmap: {e}", exc_info=True)
        try:
            bot.send_message(chat_id, f'⚠️ An unexpected error occurred while processing the {time_period} heatmap.')
        except Exception as telegram_e:
            logger.error(f"Failed to send error message to Telegram: {telegram_e}")
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)
            logger.info(f"Cleaned up temporary file: {filename}")

# --- Scheduled & Bot Handler Functions (No changes) ---

def scheduled_heatmap_task():
    """The function that gets called by the scheduler."""
    logger.info(f"Running scheduled task for {DEFAULT_TIMEFRAME} heatmap.")
    process_and_send_heatmap(CHANNEL_ID, DEFAULT_TIMEFRAME)

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, f"Bot started! I will send the {DEFAULT_TIMEFRAME} Bitcoin liquidation heatmap every {SCHEDULE_INTERVAL_HOURS} hours.")

@bot.message_handler(commands=['heatmap'])
def handle_manual_heatmap(message):
    """Handles manual requests like /heatmap or /heatmap 1 month"""
    args = message.text.split(maxsplit=2)
    time_period = DEFAULT_TIMEFRAME
    
    if len(args) > 1:
        requested_period = " ".join(args[1:])
        if requested_period in VALID_TIMEFRAMES:
            time_period = requested_period
        else:
            bot.reply_to(message, f"Invalid time frame. Please use one of: {', '.join(VALID_TIMEFRAMES)}")
            return

    bot.reply_to(message, f"Fetching the latest {time_period} Bitcoin liquidation heatmap...")
    threading.Thread(target=process_and_send_heatmap, args=(message.chat.id, time_period)).start()

# --- Main Application Logic ---

def run_bot_scheduler():
    """Main function to run the bot and scheduler."""
    logger.info(f"Starting Coinglass Heatmap Bot. Interval: {SCHEDULE_INTERVAL_HOURS} hours. Timeframe: {DEFAULT_TIMEFRAME}.")
    
    schedule.every(SCHEDULE_INTERVAL_HOURS).hours.do(scheduled_heatmap_task)
    
    logger.info("Performing initial heatmap run on startup...")
    threading.Thread(target=scheduled_heatmap_task).start()
    
    logger.info("Starting Telegram bot polling...")
    threading.Thread(target=bot.polling, kwargs={"none_stop": True, "timeout": 30}, daemon=True).start()
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# --- Flask Web Server & Application Entry Point ---

app = Flask(__name__)
bot_thread = None # Global handle to the bot thread

@app.route('/', methods=['GET'])
def root():
    return 'Bot is running.', 200

@app.route('/health', methods=['GET'])
def health():
    """
    Enhanced health check that verifies the core bot/scheduler thread is alive.
    """
    if bot_thread and bot_thread.is_alive():
        return jsonify(status='ok', threads={'bot_scheduler': 'alive'}), 200
    else:
        logger.error("Health check failed: bot_scheduler thread is not alive.")
        # Return 503 Service Unavailable, a standard code for a service being down
        return jsonify(status='error', threads={'bot_scheduler': 'dead'}), 503

if __name__ == '__main__':
    # Start the bot and scheduler logic in a background thread
    bot_thread = threading.Thread(target=run_bot_scheduler, daemon=True)
    bot_thread.start()
    
    # Use Flask's development server for local testing
    # For production, a WSGI server like Gunicorn will be used (see deployment instructions)
    port = int(os.getenv('PORT', '8080'))
    logger.info(f"Starting Flask dev server on port {port} for local testing.")
    app.run(host='0.0.0.0', port=port)
