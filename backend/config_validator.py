import os
from backend.logger import logger

REQUIRED_VARS = ["IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET"]


def validate_env():
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        logger.error(f"ENV ERROR: Missing required environment variables: {
                     ', '.join(missing)}")
        return False
    return True
