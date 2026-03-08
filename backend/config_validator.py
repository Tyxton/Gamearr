from backend.logger import logger
from backend.config import settings


def validate_env():
    '''
    ARCHITECTURE: Pydantic Settings handles structural runtime validation during boot.
    This functio nnow operates against the parsed settings rather than polling the host directly.
    Acts as a secondary verification for external API dependencies prior to worker init.
    '''
    missing = []

    if not settings.igdb_client_id:
        missing.append("IGDB_CLIENT_ID")
    if not settings.igdb_client_secret:
        missing.append("IGDB_CLIENT_SECRET")

    if missing:
        logger.error(f"ENV ERROR: Missing required config params: {
                     ', '.join(missing)}")
        return False
    return True
