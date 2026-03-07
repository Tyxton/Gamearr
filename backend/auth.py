from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from backend import database

API_KEY_NAME = "X-Api-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def validate_api_key(api_key: str = Security(api_key_header)):
    ''' Validates the X-Api-Key header against the database '''
    db_key = database.get_config("api_key")

    # allow if key matches
    if api_key == db_key:
        return api_key

    # if no key or wrong key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key"
    )
