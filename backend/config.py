from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
import platform as plat_lib
import shutil


class Settings(BaseSettings):
    port: int = Field(default=8000, validation_alias="PORT")
    api_key: str | None = None

    library_dir: Path = Field(
        default=Path("/library"), validation_alias="LIBRARY_DIR")
    incomplete_dir: Path = Field(
        default=Path("/downloads"), validation_alias="INCOMPLETE_DIR")
    db_path: Path = Field(default=Path("/app/data/gamearr/db"),
                          validation_alias="DB_PATH")

    #! DEBT: To fix the log error. Dynamic path traversal from db_path (e.g. parent.parent)
    # risks escaping the container's writable volume resulting in UID/GID permission
    # rejects against root paths like /app.
    log_dir: Path = Field(default=Path("/app/data/logs"),
                          validation_alias="LOG_DIR")

    igdb_client_id: str | None = Field(
        default=None, validation_alias="IGDB_CLIENT_ID")
    igdb_client_secret: str | None = Field(
        default=None, validation_alias="IGDB_CLIENT_SECRET")

    source_vita: str | None = Field(
        default=None, validation_alias="GAME_SOURCE_VITA")
    source_psp: str | None = Field(
        default=None, validation_alias="GAME_SOURCE_PSP")
    source_psx: str | None = Field(
        default=None, validation_alias="GAME_SOURCE_PSX")

    #! ARCHITECTURE: hardware aware i/o tuning timeouts, buffer, and user mapping
    disk_timeout: int = Field(default=30, validation_alias="DISK_TIMEOUT")
    io_buffer_size: int = Field(
        default=1048576, validation_alias="IO_BUFFER_SIZE")
    target_uid: int | None = Field(default=None, validation_alias="TARGET_UID")
    target_gid: int | None = Field(default=None, validation_alias="TARGET_GID")

    #! ARCHITECTURE: throttle concurrency to prevent multiple streams from saturating NAS disk heads
    max_concurent_io: int = Field(
        default=1, validation_alias="MAX_CONCURRENT_IO")

    @property
    def is_arm(self) -> bool:
        return plat_lib.machine().startswith(('arm', 'aarch'))

    def get_io_limit(self) -> int:
        #! ARCHITECTURE: Auto throttle for ARM to prevent overloading the SD cards
        return 1 if self.is_arm else self.max_concurent_io

    def validate_dependencies(self) -> list[str]:
        missing = []
        for cmd in ["aria2c", "pkg2zip"]:
            if not shutil.which(cmd):
                missing.append(cmd)
        return missing

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
