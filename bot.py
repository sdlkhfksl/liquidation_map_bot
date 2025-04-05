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
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')  # Can be a channel username like '@yourchannel' or a chat_id

# Initialize the bot
bot = telebot.TeleBot(TOKEN)

def setup_webdriver():
    """Configure and return a headless Chrome WebDriver instance"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=5400,2950")
    chrome_options.add_argument("--force-device-scale-factor=2")
    return webdriver.Chrome(options=chrome_options)

def capture_coinglass_heatmap(time_period="1 month"):
    """
    Capture the Coinglass Bitcoin liquidation heatmap
    
    Args:
        time_period (str): Time period to select (e.g., "24 hour", "1 month", "3 month")
    """
    try:
        logger.info(f"Starting capture of Coinglass heatmap with {time_period} timeframe")
        driver = setup_webdriver()
        
        # Navigate to Coinglass liquidation page
        driver.get("https://www.coinglass.com/pro/futures/LiquidationHeatMap")
                # Wait for the page to load
        wait = WebDriverWait(driver, 20)
        # Optimize page for screenshot
        driver.execute_script("""
            // Disable animations
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
            
            // Set high DPI
            window.devicePixelRatio = 2;
        """)
        
        try:
            # Find and click the time period dropdown button
            time_dropdown = wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR, "div.MuiSelect-root button.MuiSelect-button"
            )))
            logger.info("Found time period dropdown")
            
            # Check if the dropdown already shows the desired time period
            if time_dropdown.text.strip() != time_period:
                # Click to open the dropdown
                time_dropdown.click()
                logger.info("Clicked dropdown to open it")
                
                # Wait for dropdown options to appear
                time.sleep(2)  # Increased delay to ensure dropdown is fully opened
                
                # Try multiple selector approaches
                logger.info("Trying with JavaScript")
                driver.execute_script(f"""
                    var options = document.querySelectorAll('li[role="option"]');
                    for(var i = 0; i < options.length; i++) {{
                        if(options[i].textContent.includes('{time_period}')) {{
                            options[i].click();
                            break;
                        }}
                    }}
                """)
                # Wait for the selection to take effect
                time.sleep(3)
            else:
                logger.info(f"Dropdown already shows {time_period}, no need to change")
            
            # Now find and capture the chart
            logger.info("Looking for chart container")
            # Try different selectors for the chart
            try:
                heatmap_container = wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, "div.echarts-for-react"
                )))
            except Exception:
                logger.info("First chart selector failed, trying alternative")
                heatmap_container = wait.until(EC.presence_of_element_located((
                    By.XPATH, "//div[contains(@class, 'echarts-for-react')]"
                )))
            
            logger.info("Found chart container, waiting for render")
            # Give extra time for the chart to fully render
            time.sleep(3)
            
            rect = driver.execute_script("""
                var rect = arguments[0].getBoundingClientRect();
                return {
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: rect.height,
                    scale: window.devicePixelRatio || 1
                };
            """, heatmap_container)
            
            # Set clip area for screenshot
            clip = {
                'x': rect['x'],
                'y': rect['y'],
                'width': rect['width'],
                'height': rect['height'],
                'scale': 2  # Force 2x scale
            }
            
            # Capture screenshot with CDP
            result = driver.execute_cdp_cmd('Page.captureScreenshot', {
                'clip': clip,
                'captureBeyondViewport': True,
                'fromSurface': True
            })
            
            # Convert base64 to image
            png_data = base64.b64decode(result['data'])
            
            # Convert to PIL Image for processing if needed
            image = Image.open(BytesIO(png_data))
            
            # Save temporarily
            temp_file = f"btc_liquidation_heatmap_{datetime.now().strftime('%Y%m%d')}_{time_period.replace(' ', '_')}.png"
            image.save(temp_file, format='PNG', optimize=True, quality=100)
            
            logger.info(f"Heatmap captured and saved as {temp_file}")
            return temp_file
            
        except Exception as inner_e:
            logger.error(f"Error during chart capture process: {inner_e}")
            
            # Fallback: take screenshot of entire page
            logger.info("Attempting fallback: capturing entire page")
            driver.save_screenshot(f"fallback_screenshot_{datetime.now().strftime('%Y%m%d')}.png")
            
            # Try to continue with whatever is on screen
            try:
                # Find any chart element that might be present
                elements = driver.find_elements(By.CSS_SELECTOR, "div[class*='chart'], canvas, div[class*='echarts']")
                if elements:
                    logger.info(f"Found {len(elements)} potential chart elements, capturing first one")
                    png_data = elements[0].screenshot_as_png
                    image = Image.open(BytesIO(png_data))
                    temp_file = f"fallback_chart_{datetime.now().strftime('%Y%m%d')}.png"
                    image.save(temp_file, format='PNG', optimize=True, quality=100)
                    return temp_file
            except Exception as fallback_e:
                logger.error(f"Fallback capture also failed: {fallback_e}")
            
            raise inner_e
            
    except Exception as e:
        logger.error(f"Error capturing heatmap: {e}")
        if 'driver' in locals():
            driver.quit()
        return None
    finally:
        if 'driver' in locals():
            driver.quit()

def get_bitcoin_price():
    """Fetch the current Bitcoin price from CoinGecko API"""
    try:
        # CoinGecko API is free and doesn't require authentication for basic usage
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            price = data.get('bitcoin', {}).get('usd')
            if price:
                return f"${price:,.2f}"  # Format with commas and 2 decimal places
        
        logger.warning(f"Failed to get Bitcoin price: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error fetching Bitcoin price: {e}")
        return None
    
def send_Monthly_heatmap():
    """Capture and send the Monthly heatmap"""
    try:
        logger.info("Starting Monthly heatmap task")
        
        # Capture the heatmap
        heatmap_file = capture_coinglass_heatmap()
        
        if not heatmap_file:
            logger.error("Failed to capture heatmap")
            bot.send_message(CHANNEL_ID, "Failed to capture today's Bitcoin liquidation heatmap.")
            return
        
        # Get current Bitcoin price
        btc_price = get_bitcoin_price()
        price_text = f"BTC Price: {btc_price}" if btc_price else ""
        
        # Send the image with caption including Bitcoin price
        with open(heatmap_file, 'rb') as photo:
            caption = f"📊 Monthly Bitcoin Liquidation Heatmap - {datetime.now().strftime('%Y-%m-%d')}\n"
            if price_text:
                caption += f"💰 {price_text}\n"
            
            bot.send_photo(CHANNEL_ID, photo, caption=caption)
            
        # Clean up the file
        os.remove(heatmap_file)
        logger.info("Monthly heatmap sent successfully")
        
    except Exception as e:
        logger.error(f"Error in send_Monthly_heatmap: {e}")
        try:
            bot.send_message(CHANNEL_ID, "Error sending today's Bitcoin liquidation heatmap. Will try again tomorrow.")
        except:
            logger.error("Could not send error message to channel")
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "Bot started! I will send Monthly Bitcoin liquidation heatmaps from Coinglass.")

@bot.message_handler(commands=['heatmap'])
def handle_manual_heatmap(message):
    """Handle manual requests for the heatmap"""
    bot.reply_to(message, "Fetching the latest Bitcoin liquidation heatmap...")
    try:
        heatmap_file = capture_coinglass_heatmap()
        
        if not heatmap_file:
            bot.reply_to(message, "Sorry, I couldn't fetch the heatmap at this time.")
            return
        
        # Get current Bitcoin price
        btc_price = get_bitcoin_price()
        price_text = f"BTC Price: {btc_price}" if btc_price else ""
            
        with open(heatmap_file, 'rb') as photo:
            caption = f"📊 Bitcoin Liquidation Heatmap - {datetime.now().strftime('%Y-%m-%d')}\n"
            if price_text:
                caption += f"💰 {price_text}\n"
            
            bot.send_photo(message.chat.id, photo, caption=caption)
            
        os.remove(heatmap_file)
        
    except Exception as e:
        logger.error(f"Error handling manual heatmap request: {e}")
        bot.reply_to(message, "An error occurred while fetching the heatmap.")

def main():
    """Main function to run the bot"""
    logger.info("Starting the Coinglass Bitcoin Liquidation Heatmap bot")
    
    # Schedule the Monthly task - adjust time as needed
    schedule.every().day.at("08:00").do(send_Monthly_heatmap)  # UTC time
    
    # Send an initial heatmap
    send_Monthly_heatmap()
    
    # Start the bot polling in a separate thread
    import threading
    threading.Thread(target=bot.polling, kwargs={"none_stop": True}).start()
    
    # Run the scheduler
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()