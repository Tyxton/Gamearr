import logging
import sys
from logging.handlers import RotatingFileHandler

#! ARCHITECTURE: Centralized path config via settings prevent drift and hardcoded vulnerabilities.
from backend.config import settings

#! DESTRUCTIVE: removed dynamic path traversal (db_path.parent.parent) which escaped
# the mapped writing volumes. Logging now maps strictly to the pydantic scheme.
LOG_DIR = settings.log_dir
LOG_FILE = LOG_DIR / "gamearr.log"


def setup_logger():
    logger = logging.getLogger("gamearr")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        #! ARCHITECTURE: Allows for LXC/DOCKER logging
        #! DEBT: Direct to stdout to ensure container orchestation captures output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        #! DEBT: Environment Variables (like LOG_DIR=/app/logs) mapped by user to unchowed
        # root level container paths will crash the application during python's module import phase.
        # Trap the OSError/PermissionError to survive the init sequence and boot with console-only
        # logging rather than fatally exiting with Errno13 before FastAPI lifespan triggers.
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                str(LOG_FILE), maxBytes=5*1024*1024, backupCount=3)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            #! OPERATOR: Degrades to console-only logging if host
            # orchestration fails to map the LOG_DIR, so you're not in the dark
            logger.warning(f"LOGGING WARNING: Volume permission error on {
                           LOG_DIR}. File logging disabled. ({e})")

    return logger


logger = setup_logger()
