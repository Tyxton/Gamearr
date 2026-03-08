import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

#! ARCHITECTURE: Centralized path config via settings prevent drift and hardcoded vulnerabilities.
from backend.config import settings

LOG_DIR = settings.db_path.parent.parent / "logs"
LOG_FILE = LOG_DIR / "gamearr.log"


def setup_logger():
    logger = logging.getLogger("gamearr")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        #! ARCHITECTURE: Allows for LXC/DOCKER logging
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        #! DESTRUCTIVE: os.makedirs swapped for Pathlib. Native filestructure handling.
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            str(LOG_FILE), maxBytes=5*1024*1024, backupCount=3)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()
