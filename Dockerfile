# --- START OF FILE Dockerfile ---

# Use a standard Python base image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install system dependencies needed for Chrome and Python libraries
# Including jq for parsing JSON and unzip
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    jq \
    && rm -rf /var/lib/apt/lists/*

# --- Install Google Chrome (Stable) ---
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# --- Install ChromeDriver (matching the installed Chrome version) ---
# This script automatically finds the correct driver for the installed Chrome version
RUN CHROME_DRIVER_URL=$(wget -qO- "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform=="linux64") | .url') \
    && echo "Downloading ChromeDriver from $CHROME_DRIVER_URL" \
    && wget -q --continue -P /tmp/ "$CHROME_DRIVER_URL" \
    && unzip -q /tmp/chromedriver-linux64.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver-linux64.zip \
    # The extracted driver is often in a subdirectory, move it to the path
    && mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rmdir /usr/local/bin/chromedriver-linux64 \
    && chmod +x /usr/local/bin/chromedriver

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Set the command to run the application using Gunicorn
# Using the post_fork hook to start background tasks in each worker
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "bot:app", "--post-fork", "bot:post_fork"]

# --- END OF FILE Dockerfile ---
