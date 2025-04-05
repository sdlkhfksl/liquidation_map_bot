# Bitcoin Liquidation Heatmap Bot

A Telegram bot that automatically captures and posts Bitcoin liquidation heatmaps from Coinglass to a specified Telegram channel.

## Overview

This bot uses Selenium to capture screenshots of the Bitcoin liquidation heatmap from Coinglass.com and posts them to a Telegram channel at scheduled intervals. It provides valuable market insights for cryptocurrency traders by visualizing liquidation data.

## Features

- Captures high-resolution screenshots of Coinglass Bitcoin liquidation heatmaps
- Supports multiple timeframes (24h, 1 month, 3 month)
- Posts images automatically to a configured Telegram channel
- Runs on a schedule with configurable intervals
- Containerized with Docker for easy deployment

## Prerequisites

- Docker and Docker Compose
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Telegram Channel ID where the bot will post updates

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/signalorange/liquidation_map_bot.git
cd liquidation_map_bot
```

### 2. Create a .env file

Create a `.env` file in the project root with the following variables:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHANNEL_ID=@your_channel_name
```

### 3. Build and run with Docker Compose

```bash
docker-compose up -d
```

## Docker Compose Configuration

The project uses two containers:
- **selenium**: Runs a standalone Chrome browser for web scraping
- **bot**: Contains the Python bot code that connects to Selenium and Telegram

## Customization

You can modify the schedule and timeframes by editing the `bot.py` file.

## Troubleshooting

### Connection Issues with Selenium

If the bot cannot connect to the Selenium container, ensure that:
- The Selenium container is running (`docker-compose ps`)
- The network between containers is properly configured
- The Selenium service has had enough time to start up

### Image Capture Problems

If the captured images are blank or incomplete:
- Try increasing the wait time for page elements to load
- Adjust the window size in the Chrome options
- Check if Coinglass has changed their website layout

## Logs

Logs are stored in the `logs` directory and can be viewed with:

```bash
docker-compose logs bot
```

## License

[MIT License](LICENSE)

## Acknowledgements

- [Coinglass](https://www.coinglass.com) for providing the liquidation data
- [Selenium](https://www.selenium.dev/) for web automation capabilities
- [python-telegram-bot](https://python-telegram-bot.org/) for Telegram integration
