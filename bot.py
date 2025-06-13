import os
import logging
import requests
import time
from datetime import datetime
import schedule
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telebot

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./logs/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Get token from environment variable
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')  # Channel username like '@yourchannel' or chat_id

# Initialize the bot
bot = telebot.TeleBot(TOKEN)

def setup_webdriver(max_retries=5, retry_delay=2):
    """Configure and return a remote Chrome WebDriver instance with retries"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=5400,2950")
    chrome_options.add_argument("--force-device-scale-factor=2")
    
    selenium_host = os.getenv('SELENIUM_HOST', 'localhost')
    selenium_port = os.getenv('SELENIUM_PORT', '4444')
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to Selenium at http://{selenium_host}:{selenium_port}/wd/hub (attempt {attempt+1}/{max_retries})")
            driver = webdriver.Remote(
                command_executor=f'http://{selenium_host}:{selenium_port}/wd/hub',
                options=chrome_options
            )
            logger.info("Successfully connected to Selenium")
            return driver
        except Exception as e:
            logger.warning(f"Failed to connect to Selenium: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Max retries exceeded. Could not connect to Selenium.")
                raise

def capture_coinglass_heatmap(time_period="24 hour"):
    """
    Capture the Coinglass Bitcoin liquidation heatmap
    
    Args:
        time_period (str): Time period to select (e.g., "24 hour", "1 month", "3 month")
    """
    driver = None
    try:
        logger.info(f"Starting capture of Coinglass heatmap with {time_period} timeframe")
        driver = setup_webdriver()
        
        # Navigate to Coinglass liquidation page
        driver.get("https://www.coinglass.com/pro/futures/LiquidationHeatMap")
        wait = WebDriverWait(driver, 20)

        # Inject CSS/JS to optimize screenshot
        driver.execute_script("""
            var style = document.createElement('style');
            style.innerHTML = `
                * {
                    transition: none !important;
                    animation: none !important;
                }
                .echarts-for-react {
                    width: 100% !important;
                    height: 100% !important;
                }
                canvas {
                    image-rendering: -webkit-optimize-contrast !important;
                    image-rendering: crisp-edges !important;
                }
            `;
            document.head.appendChild(style);
            window.devicePixelRatio = 2;
        """)
        
        # Select the desired time period
        time_dropdown = wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, "div.MuiSelect-root button.MuiSelect-button"
        )))
        if time_dropdown.text.strip() != time_period:
            time_dropdown.click()
            time.sleep(2)
            driver.execute_script(f"""
                var options = document.querySelectorAll('li[role="option"]');
                for (var i = 0; i < options.length; i++) {{
                    if (options[i].textContent.includes('{time_period}')) {{
                        options[i].click();
                        break;
                    }}
                }}
            """)
            time.sleep(3)
        else:
            logger.info(f"Dropdown already set to {time_period}")

        # Locate the chart container
        try:
            heatmap_container = wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, "div.echarts-for-react"
            )))
        except Exception:
            heatmap_container = wait.until(EC.presence_of_element_located((
                By.XPATH, "//div[contains(@class, 'echarts-for-react')]"
            )))
        time.sleep(3)

        # Compute screenshot bounds
        rect = driver.execute_script("""
            var r = arguments[0].getBoundingClientRect();
            return {left: r.left, top: r.top, width: r.width, height: r.height, scale: window.devicePixelRatio || 1};
        """, heatmap_container)
        clip = {
            'x': rect['left'],
            'y': rect['top'],
            'width': rect['width'],
            'height': rect['height'],
            'scale': 2
        }

        # Capture via Chrome DevTools Protocol
        result = driver.execute_cdp_cmd('Page.captureScreenshot', {
            'clip': clip,
            'captureBeyondViewport': True,
            'fromSurface': True
        })
        png = base64.b64decode(result['data'])
        image = Image.open(BytesIO(png))

        # Save file
        filename = f"btc_heatmap_24h_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
        image.save(filename, format='PNG', optimize=True, quality=100)
        logger.info(f"Heatmap saved as {filename}")
        return filename

    except Exception as err:
        logger.error(f"Error during heatmap capture: {err}")
        # Fallback: full-page screenshot
        if driver:
            fallback_name = f"fallback_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
            try:
                driver.save_screenshot(fallback_name)
                logger.info(f"Fallback full-page screenshot saved as {fallback_name}")
                return fallback_name
            except Exception as fb:
                logger.error(f"Fallback screenshot failed: {fb}")
        return None

    finally:
        if driver:
            driver.quit()

def get_bitcoin_price():
    """Fetch the current Bitcoin price from CoinGecko API"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            price = data.get('bitcoin', {}).get('usd')
            return f"${price:,.2f}" if price else None
        logger.warning(f"CoinGecko API returned {resp.status_code}")
    except Exception as e:
        logger.error(f"Error fetching BTC price: {e}")
    return None

def send_heatmap_24h():
    """Capture and send the 24‑hour heatmap"""
    try:
        logger.info("Running 24‑hour heatmap task")
        file_path = capture_coinglass_heatmap("24 hour")
        if not file_path:
            bot.send_message(CHANNEL_ID, "❌ 无法获取24小时比特币爆仓热力图。")
            return

        price = get_bitcoin_price()
        caption = f"📊 24‑Hour Bitcoin Liquidation Heatmap — {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
        if price:
            caption += f"\n💰 BTC Price: {price}"

        with open(file_path, 'rb') as photo:
            bot.send_photo(CHANNEL_ID, photo, caption=caption)
        os.remove(file_path)
        logger.info("Heatmap sent successfully")

    except Exception as e:
        logger.error(f"Error in send_heatmap_24h: {e}")
        try:
            bot.send_message(CHANNEL_ID, "⚠️ 发送24小时热力图时出错。")
        except Exception:
            pass

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "Bot 已启动！我将每四小时发送一次24小时比特币爆仓热力图。")

@bot.message_handler(commands=['heatmap'])
def handle_manual_heatmap(message):
    bot.reply_to(message, "正在获取最新的24小时比特币爆仓热力图…")
    try:
        file_path = capture_coinglass_heatmap("24 hour")
        if not file_path:
            bot.reply_to(message, "抱歉，目前无法获取热力图。")
            return
        price = get_bitcoin_price()
        caption = f"📊 Bitcoin Liquidation Heatmap — {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
        if price:
            caption += f"\n💰 BTC Price: {price}"
        with open(file_path, 'rb') as photo:
            bot.send_photo(message.chat.id, photo, caption=caption)
        os.remove(file_path)
    except Exception as e:
        logger.error(f"Manual heatmap error: {e}")
        bot.reply_to(message, "获取热力图时发生错误。")

def main():
    logger.info("Starting Coinglass Bitcoin Liquidation Heatmap bot")
    # 每隔 4 小时执行一次
    schedule.every(4).hours.do(send_heatmap_24h)
    # 启动时立即发送一次
    send_heatmap_24h()
    # 启动 Telegram Polling
    import threading
    threading.Thread(target=bot.polling, kwargs={"none_stop": True}).start()
    # 运行调度
    while True:
        schedule.run_pending()
        time.sleep(60)

def run_bot():
    """在后台线程中运行 Bot 逻辑"""
    main()

if __name__ == "__main__":
    from flask import Flask, jsonify
    app = Flask(__name__)

    @app.route("/", methods=["GET"])
    def root():
        return "OK", 200

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(status="ok"), 200

    # 启动 Bot 线程
    import threading
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()

    # 启动 HTTP 服务，监听 Koyeb 注入的 PORT
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
