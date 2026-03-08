from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    #! ARCHITECTURE: Pydantic will rase a ValidationError if .env paths are invalid.
    port: int = Field(default=8000, validation_alias="PORT")
    api_key: str | None = None

    #! DESTRUCTIVE: all paths are strictly Path objects. No string concatenation allowed.
    library_dir: Path = Field(
        default=Path("/library"), validation_alias="LIBRARY_DIR")
    incomplete_dir: Path = Field(
        default=Path("/downloads"), validation_alias="INCOMPLETE_DIR")
    db_path: Path = Field(default=Path("/app/data/gamearr/db"),
                          validation_alias="DB_PATH")

    igdb_client_id: str | None = Field(
        default=None, validation_alias="IGDB_CLIENT_ID")
    igdb_cleint_secret: str | None = Field(
        default=None, validation_alias="IGDB_CLIENT_SECRET")

    source_vita: str | None = Field(
        default=None, validation_alias="GAME_SOURCE_VITA")
    source_psp: str | None = Field(
        default=None, validation_alias="GAME_SOURCE_PSP")
    source_psx: str | None = Field(
        default=None, validation_alias="GAME_SOURCE_PSX")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
