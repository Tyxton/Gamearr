import logging
import os
from logging.handlers import RotatingFileHandler

from pandas.core.frame import console

# Define path - /app/data for persistence
LOG_DIR = os.getenv("LOG_DIR", "/app/data/logs")
LOG_FILE = os.path.join(LOG_DIR, "gamearr.log")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)


def setup_logger():
    logger = logging.getLogger("gamearr")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handler if setup is called multiple times
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # console handler for docker/lxc logs
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # rotating file handler for UI and troubleshooting
        # max size 5MB, keep 3 backup files
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# global
logger = setup_logger()
