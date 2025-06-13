# --- START OF Dockerfile ---

# 使用一个标准的 Python 3.11 slim 基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖，包括 Chrome 浏览器运行所需要的一切
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    jq \
    && rm -rf /var/lib/apt/lists/*

# --- 安装 Google Chrome (稳定版) ---
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# --- 安装 ChromeDriver (自动匹配已安装的 Chrome 版本) ---
RUN CHROME_DRIVER_URL=$(wget -qO- "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform=="linux64") | .url') \
    && wget -q --continue -P /tmp/ "$CHROME_DRIVER_URL" \
    && unzip -q /tmp/chromedriver-linux64.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver-linux64.zip \
    && mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rmdir /usr/local/bin/chromedriver-linux64 \
    && chmod +x /usr/local/bin/chromedriver

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制整个应用程序代码
COPY . .

# 暴露 Gunicorn 运行的端口
EXPOSE 8000

# --- 最终启动命令 ---
# 这是 Koyeb 将会执行的唯一命令。
# 它使用 Gunicorn 启动 bot.py 中的 'app' Flask 应用。
# post_fork hook 是 Gunicorn 的一个高级功能，用于在 web 服务器启动后，安全地启动我们的后台任务。
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "bot:app", "--post-fork", "bot:post_fork"]

# --- END OF Dockerfile ---
