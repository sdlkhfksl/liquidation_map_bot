# gunicorn.conf.py

import bot

# Gunicorn config variables
bind = "0.0.0.0:8000"  # Koyeb 会自动覆盖这个端口，但最好写上
workers = 1
threads = 4
timeout = 120

def post_fork(server, worker):
    """
    This hook is called in the worker process after it's been forked.
    It's the perfect place to start our background thread.
    """
    # 调用 bot.py 中的启动函数
    bot.start_background_tasks()
