# gunicorn.conf.py

import os
import bot

# --- Server Mechanics ---

# The address and port to bind to.
# Koyeb provides the PORT environment variable, so we use that.
# '8000' is a fallback for local testing.
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Number of worker processes.
# For this app, which has a single stateful scheduler, we MUST use 1 worker.
workers = 1

# Number of threads per worker.
# This allows the single worker to handle multiple concurrent health checks.
threads = 4

# Worker timeout in seconds.
# This should be long enough to prevent Gunicorn from killing a worker
# during a long-running API call.
timeout = 120

# --- Hooks ---

def post_fork(server, worker):
    """
    This hook is called in the worker process after it has been forked.
    It's the perfect place to start our background bot and scheduler thread.
    """
    server.log.info(f"Worker {worker.pid} forked, starting background tasks...")
    bot.start_background_tasks()
