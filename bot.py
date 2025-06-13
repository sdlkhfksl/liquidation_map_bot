# bot.py (Corrected version for ScreenshotOne API)

import os
import logging
import requests
import time
from datetime import datetime
import schedule
import telebot
from dotenv import load_dotenv
import threading
from flask import Flask, jsonify

# --- Configuration ---
os.makedirs("logs", exist_ok=True)
load_dotenv()

# --- Environment Variables & Constants ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
SCREENSHOTONE_API_KEY = os.getenv('SCREENSHOTONE_API_KEY')

SCHEDULE_INTERVAL_HOURS = int(os.getenv('SCHEDULE_INTERVAL_HOURS', '4'))
DEFAULT_TIMEFRAME = os.getenv('DEFAULT_TIMEFRAME', '24 hour')
VALID_TIMEFRAMES = ["24 hour", "12 hour", "4 hour", "1 hour", "1 week", "1 month", "3 month"]
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# --- Initialization ---
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("./logs/bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

if not all([TOKEN, CHANNEL_ID, SCREENSHOTONE_API_KEY]):
    logger.error("FATAL: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, and SCREENSHOTONE_API_KEY must be set.")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# --- Core Logic (API Call Corrected) ---

def capture_coinglass_heatmap_api(time_period: str = "24 hour") -> bytes | None:
    """
    Captures the Coinglass heatmap using the ScreenshotOne API by targeting the canvas element.
    Returns the raw image data as bytes, or None on failure.
    """
    logger.info(f"Requesting screenshot from API for timeframe: '{time_period}'")
    
    js_script = f"""
    async () => {{
        const dropdown = document.querySelector('div.MuiSelect-root button.MuiSelect-button');
        if (dropdown && dropdown.textContent.trim() !== '{time_period}') {{
            dropdown.click();
            await new Promise(resolve => setTimeout(resolve, 500));
            const option = Array.from(document.querySelectorAll('li[role=option]')).find(el => el.textContent.includes('{time_period}'));
            if (option) {{
                option.click();
                await new Promise(resolve => setTimeout(resolve, 4000)); 
            }}
        }}
    }}()
    """
    
    canvas_selector = 'canvas[data-zr-dom-id^="zr_"]'
    
    params = {
        "access_key": SCREENSHOTONE_API_KEY,
        "url": "https://www.coinglass.com/pro/futures/LiquidationHeatMap",
        "selector": canvas_selector,
        "block_cookie_banners": "true",
        "block_ads": "true",
        
        # --- KEY FIX IS HERE ---
        "response_type": "by_format",      # CORRECTED: Changed from "image"
        "image_format": "png",             # ADDED: Specify the format when using "by_format"
        # --- END OF FIX ---
        
        "image_quality": "90",
        "viewport_width": "1920",
        "viewport_height": "1080",
        "wait_for_selector": canvas_selector,
        "scripts": js_script,
    }

    try:
        response = requests.get("https://api.screenshotone.com/take", params=params, timeout=90)
        response.raise_for_status()
        logger.info("Successfully received image from ScreenshotOne API.")
        return response.content
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling ScreenshotOne API: {e}")
        if e.response is not None:
            logger.error(f"API Response Status: {e.response.status_code}, Body: {e.response.text}")
        return None

# --- All other functions remain exactly the same ---

def get_bitcoin_price() -> str | None:
    try:
        resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', timeout=10)
        resp.raise_for_status()
        data = resp.json()
        price = data.get('bitcoin', {}).get('usd')
        return f"${price:,.2f}" if price else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching BTC price: {e}")
        return None

def process_and_send_heatmap(chat_id: str | int, time_period: str):
    try:
        image_data = capture_coinglass_heatmap_api(time_period)
        if not image_data:
            bot.send_message(chat_id, f'❌ Failed to capture the {time_period} Bitcoin liquidation heatmap.')
            return
        price = get_bitcoin_price()
        time_period_title = time_period.replace(" hour", "-Hour").replace(" week", "-Week").replace(" month", "-Month")
        caption = f"📊 {time_period_title} Bitcoin Liquidation Heatmap\n"
        caption += f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
        if price:
            caption += f"\n💰 BTC Price: {price}"
        bot.send_photo(chat_id, image_data, caption=caption)
        logger.info(f"Heatmap sent successfully to chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"Error in process_and_send_heatmap: {e}", exc_info=True)
        try:
            bot.send_message(chat_id, f'⚠️ An unexpected error occurred while processing the {time_period} heatmap.')
        except Exception as telegram_e:
            logger.error(f"Failed to send error message to Telegram: {telegram_e}")

def scheduled_heatmap_task():
    logger.info(f"Running scheduled task for {DEFAULT_TIMEFRAME} heatmap.")
    process_and_send_heatmap(CHANNEL_ID, DEFAULT_TIMEFRAME)

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, f"Bot started! I will send the {DEFAULT_TIMEFRAME} Bitcoin liquidation heatmap every {SCHEDULE_INTERVAL_HOURS} hours.")

@bot.message_handler(commands=['heatmap'])
def handle_manual_heatmap(message):
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

def run_bot_scheduler():
    logger.info(f"Starting Bot Scheduler. Interval: {SCHEDULE_INTERVAL_HOURS} hours.")
    schedule.every(SCHEDULE_INTERVAL_HOURS).hours.do(scheduled_heatmap_task)
    logger.info("Performing initial heatmap run on startup...")
    threading.Thread(target=scheduled_heatmap_task).start()
    logger.info("Starting Telegram bot polling...")
    threading.Thread(target=bot.polling, kwargs={"none_stop": True, "timeout": 30}, daemon=True).start()
    while True:
        schedule.run_pending()
        time.sleep(60)

app = Flask(__name__)
bot_thread = None

def start_background_tasks():
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        logger.info("Starting background tasks for the bot...")
        bot_thread = threading.Thread(target=run_bot_scheduler, daemon=True)
        bot_thread.start()

@app.route('/')
def root(): return 'Bot is running.'

@app.route('/health')
def health():
    if bot_thread and bot_thread.is_alive():
        return jsonify(status='ok'), 200
    else:
        logger.error("Health check failed: bot_scheduler thread is not alive.")
        return jsonify(status='error', reason='Background thread is not running'), 503

if __name__ == '__main__':
    logger.info("Starting application for local development...")
    start_background_tasks()
    port = int(os.getenv('PORT', '8080'))
    app.run(host='0.0.0.0', port=port)
