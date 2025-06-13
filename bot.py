# --- START OF bot.py ---

import os
import logging
import time
from datetime import datetime
import schedule
import telebot
from dotenv import load_dotenv
import threading
from flask import Flask, jsonify
import requests
import base64
from io import BytesIO

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
# 创建 logs 文件夹，如果它不存在的话
os.makedirs("logs", exist_ok=True)
load_dotenv()

# --- Environment Variables & Constants ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
SCHEDULE_INTERVAL_HOURS = int(os.getenv('SCHEDULE_INTERVAL_HOURS', '24')) # 默认24小时
DEFAULT_TIMEFRAME = os.getenv('DEFAULT_TIMEFRAME', '1 month')
VALID_TIMEFRAMES = ["24 hour", "12 hour", "4 hour", "1 hour", "1 week", "1 month", "3 month"]
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# --- Initialization ---
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("./logs/bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

if not all([TOKEN, CHANNEL_ID]):
    logger.error("FATAL: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set in Koyeb environment variables.")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# --- Core Selenium Logic ---
def setup_webdriver():
    """配置并返回一个本地的 Chrome WebDriver 实例"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=2400,1600")
    chrome_options.add_argument("--force-device-scale-factor=1.5")
    
    logger.info("Setting up local Selenium WebDriver...")
    try:
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("Local WebDriver started successfully.")
        return driver
    except Exception as e:
        logger.error(f"Failed to start local WebDriver: {e}", exc_info=True)
        raise

def capture_coinglass_heatmap(time_period: str) -> bytes | None:
    """使用 Selenium 捕获 Coinglass 热图并返回图片的二进制数据"""
    driver = None
    try:
        logger.info(f"Starting capture for timeframe: {time_period}")
        driver = setup_webdriver()
        
        driver.get("https://www.coinglass.com/pro/futures/LiquidationHeatMap")
        wait = WebDriverWait(driver, 30)

        wait.until(EC.presence_of_element_located((By.ID, "root")))
        time.sleep(2)

        dropdown_selector = "div.cg-style-161sc7i > div.MuiSelect-root"
        time_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, dropdown_selector)))
        
        current_period = time_dropdown.text.strip()
        if current_period != time_period:
            time_dropdown.click()
            option_xpath = f"//li[@role='option' and text()='{time_period}']"
            option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
            option.click()
            logger.info(f"Selected '{time_period}' from dropdown.")
            time.sleep(4)
        else:
            logger.info("Correct time period already selected.")
            time.sleep(2)

        chart_element_selector = "div.echarts-for-react"
        heatmap_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, chart_element_selector)))
        
        result = driver.execute_cdp_cmd(
            'Page.captureScreenshot',
            {'clip': heatmap_container.rect, 'fromSurface': True}
        )
        png_data = base64.b64decode(result['data'])
        logger.info("Screenshot captured successfully.")
        return png_data

    except Exception as e:
        logger.error(f"An error occurred during heatmap capture: {e}", exc_info=True)
        if driver:
            driver.save_screenshot("debug_screenshot.png")
            logger.error("Saved full-page debug_screenshot.png")
        return None
    finally:
        if driver:
            driver.quit()
            logger.info("WebDriver has been closed.")

def get_bitcoin_price() -> str | None:
    """从 CoinGecko API 获取比特币价格"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = data.get('bitcoin', {}).get('usd')
        return f"${price:,.2f}" if price else None
    except requests.RequestException as e:
        logger.error(f"Error fetching Bitcoin price: {e}")
        return None

# --- Bot & Task Functions ---
def process_and_send_heatmap(chat_id: str | int, time_period: str):
    image_bytes = capture_coinglass_heatmap(time_period)
    
    if not image_bytes:
        bot.send_message(chat_id, f'❌ Failed to capture screenshot for {time_period} heatmap.')
        return
    
    price = get_bitcoin_price()
    time_period_title = time_period.replace(" hour", "H").replace(" week", "W").replace(" month", "M")
    caption = f"📊 BTC Liquidation Heatmap ({time_period_title})\n"
    caption += f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
    if price:
        caption += f"\n💰 BTC Price: {price}"
    
    bot.send_photo(chat_id, BytesIO(image_bytes), caption=caption)
    logger.info(f"Heatmap screenshot sent successfully to chat_id: {chat_id}")

def scheduled_heatmap_task():
    logger.info(f"Running scheduled task for {DEFAULT_TIMEFRAME} heatmap.")
    process_and_send_heatmap(CHANNEL_ID, DEFAULT_TIMEFRAME)

@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    bot.reply_to(message, f"Bot started. Use /heatmap [timeframe] to get a chart. e.g., `/heatmap 4 hour`.\nValid timeframes: {', '.join(VALID_TIMEFRAMES)}")

@bot.message_handler(commands=['heatmap'])
def handle_manual_heatmap(message):
    args = message.text.split(maxsplit=2)
    time_period = DEFAULT_TIMEFRAME
    if len(args) > 1:
        requested_period = " ".join(args[1:])
        if requested_period in VALID_TIMEFRAMES:
            time_period = requested_period
        else:
            bot.reply_to(message, f"Invalid time frame. Use one of: {', '.join(VALID_TIMEFRAMES)}")
            return
    bot.reply_to(message, f"Capturing the latest {time_period} Bitcoin liquidation heatmap, please wait...")
    threading.Thread(target=process_and_send_heatmap, args=(message.chat.id, time_period)).start()

# --- Main Application Logic & Flask Server ---
def run_bot_scheduler():
    logger.info(f"Starting Bot Scheduler. Interval: {SCHEDULE_INTERVAL_HOURS} hours.")
    schedule.every(SCHEDULE_INTERVAL_HOURS).hours.do(scheduled_heatmap_task)
    
    # 为了避免启动时发送两次，这里的启动任务可以视情况决定是否需要
    # logger.info("Performing initial heatmap run on startup...")
    # threading.Thread(target=scheduled_heatmap_task).start()

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

# Gunicorn hook, a reliable way to start background tasks in a web server environment.
def post_fork(server, worker):
    start_background_tasks()

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
    # 这个部分只在本地直接运行 python bot.py 时使用，Gunicorn部署时不会执行
    logger.info("Starting application for local development...")
    start_background_tasks()
    port = int(os.getenv('PORT', '8080'))
    app.run(host='0.0.0.0', port=port)

# --- END OF bot.py ---
