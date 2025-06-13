# bot.py (最终版 - API直连 + Matplotlib绘图)

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
import json
from io import BytesIO

# 绘图库
import numpy as np
import matplotlib
matplotlib.use('Agg') # 使用非交互式后端，在服务器上运行的必要设置
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter

# --- Configuration ---
os.makedirs("logs", exist_ok=True)
load_dotenv()

# --- Environment Variables & Constants ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
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

if not all([TOKEN, CHANNEL_ID]):
    logger.error("FATAL: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set.")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# --- Core Logic ---

def get_heatmap_raw_data(time_period: str = "24 hour") -> dict | None:
    """从 Coinglass 的真实 API 获取热力图的原始数据"""
    time_type_map = {
        "24 hour": "0", "1 month": "1", "3 month": "2",
        "12 hour": "3", "4 hour": "4", "1 hour": "5", "1 week": "6"
    }
    api_url = "https://api.coinglass.com/api/pro/v1/futures/getLiquidationMap"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    payload = {
        "symbol": "BTC",
        "timeType": time_type_map.get(time_period, "0"),
        "type": 0
    }
    try:
        logger.info(f"Fetching heatmap data from Coinglass API for timeframe: {time_period}")
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("success") and "data" in data:
            logger.info("Successfully fetched raw data.")
            return data["data"]
        else:
            logger.error(f"API returned success=false or no data. Response: {data}")
            return None
    except requests.RequestException as e:
        logger.error(f"Error fetching data from Coinglass API: {e}")
        return None

def plot_heatmap_image(raw_data: dict, time_period: str) -> bytes | None:
    """使用 Matplotlib 将原始数据绘制成热力图图片"""
    try:
        logger.info("Starting to plot heatmap image.")
        # 提取数据
        price_list = np.array(raw_data['priceList'])
        date_list = raw_data['dateList']
        long_list = np.array(raw_data['longRateList'])
        short_list = np.array(raw_data['shortRateList'])
        
        # Coinglass API 返回的是一维数组，需要重塑成二维矩阵
        # 矩阵的形状是 (价格点数, 时间点数)
        num_prices = len(price_list)
        num_times = len(date_list)
        
        # 将一维的清算率数据重塑为二维
        long_matrix = long_list.reshape(num_times, num_prices).T
        short_matrix = short_list.reshape(num_times, num_prices).T
        
        # 合并多头和空头数据用于绘图，这里我们简单相加
        heatmap_matrix = long_matrix + short_matrix
        
        # --- 开始绘图 ---
        # 创建一个模仿 Coinglass 的颜色映射
        colors = ['#000000', '#000080', '#0000FF', '#FFFF00', '#FFFFFF']
        cmap = LinearSegmentedColormap.from_list('coinglass_cmap', colors)

        # 创建图表和坐标轴
        fig, ax = plt.subplots(figsize=(15, 8), dpi=100)
        fig.set_facecolor('#131722') # 设置背景色
        ax.set_facecolor('#131722')

        # 绘制热力图
        im = ax.imshow(heatmap_matrix, aspect='auto', cmap=cmap, 
                       interpolation='nearest', origin='lower',
                       extent=[0, num_times, 0, num_prices])

        # --- 格式化坐标轴 ---
        # Y轴 (价格)
        ax.set_ylabel('Price (USD)', color='white', fontsize=12)
        price_ticks = np.linspace(0, num_prices - 1, 8, dtype=int)
        ax.set_yticks(price_ticks)
        ax.set_yticklabels([f'{int(price_list[i])}' for i in price_ticks], color='white')

        # X轴 (时间)
        ax.set_xlabel('Date', color='white', fontsize=12)
        time_ticks = np.linspace(0, num_times - 1, 6, dtype=int)
        ax.set_xticks(time_ticks)
        ax.set_xticklabels([datetime.fromtimestamp(date_list[i]/1000).strftime('%m-%d %H:%M') for i in time_ticks], color='white', rotation=20)

        # 设置标题
        ax.set_title(f'BTC Liquidation Heatmap ({time_period})', color='white', fontsize=16, pad=20)

        # 调整边框颜色
        for spine in ax.spines.values():
            spine.set_edgecolor('gray')

        # 添加颜色条 (图例)
        cbar = fig.colorbar(im, ax=ax, pad=0.02)
        cbar.set_label('Liquidation Amount', color='white')
        plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='white')

        # --- 保存到内存 ---
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig) # 关闭图表，释放内存
        
        logger.info("Successfully plotted heatmap image.")
        return buf.getvalue()

    except Exception as e:
        logger.error(f"Error plotting image: {e}", exc_info=True)
        return None

def process_and_send_heatmap(chat_id: str | int, time_period: str):
    """获取数据、绘图并发送的完整流程"""
    raw_data = get_heatmap_raw_data(time_period)
    if not raw_data:
        bot.send_message(chat_id, f'❌ Failed to fetch data for {time_period} heatmap.')
        return

    image_data = plot_heatmap_image(raw_data, time_period)
    if not image_data:
        bot.send_message(chat_id, f'❌ Failed to generate image for {time_period} heatmap.')
        return
    
    price = get_bitcoin_price()
    time_period_title = time_period.replace(" hour", "-Hour").replace(" week", "-Week").replace(" month", "-Month")
    caption = f"📊 {time_period_title} Bitcoin Liquidation Heatmap (Self-Generated)\n"
    caption += f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
    if price:
        caption += f"\n💰 BTC Price: {price}"
    
    bot.send_photo(chat_id, image_data, caption=caption)
    logger.info(f"Self-generated heatmap sent successfully to chat_id: {chat_id}")

def get_bitcoin_price() -> str | None:
    # (此函数保持不变)
    try:
        resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', timeout=10)
        resp.raise_for_status()
        data = resp.json()
        price = data.get('bitcoin', {}).get('usd')
        return f"${price:,.2f}" if price else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching BTC price: {e}")
        return None

# --- Scheduled & Bot Handler Functions (保持不变) ---
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
    bot.reply_to(message, f"Fetching and generating the latest {time_period} Bitcoin liquidation heatmap...")
    threading.Thread(target=process_and_send_heatmap, args=(message.chat.id, time_period)).start()

# --- Main Application Logic & Flask Server (保持不变) ---
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
