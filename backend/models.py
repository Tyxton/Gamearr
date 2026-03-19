from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import TypedDict


class GameModel(BaseModel):
    title_id: str
    platform: str
    region: str
    name: str
    pkg_url: str
    license_key: str | None = "MISSING"
    cover_url: str | None = "/assets/placeholder.png"
    status: str | None = "available"

    class Config:
        from_attributes = True


class QueuePayload(BaseModel):
    title_id: str
    platform: str
    region: str
    name: str
    pkg_url: str
    license_key: str | None = "MISSING"


class QueueItem(QueuePayload):
    status: str
    added_at: datetime | None = None
    progress: float = 0.0
    size_total: int = 0
    size_current: int = 0
    error_msg: str | None = None


class MountState(str, Enum):
    '''
    ARCHITECTURE: Represents the physical health of a network mount, which can be used to halt/resume the workers
    '''
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class GameStatus(str, Enum):
    AVAILABLE = "available"      # Not in DB, found via search
    PENDING = "pending"          # In queue, waiting for worker
    DOWNLOADING = "downloading"  # aria2c is active
    EXTRACTING = "extracting"    # pkg2zip is active
    VERIFYING = "verifying"      # checking the hash/size
    IMPORTING = "importing"      # Moving files to /library
    STALLED = "stalled"          # I/O halt (forex NAS offline)
    COMPLETED = "completed"      # Succcessfully installed
    FAILED = "failed"            # General Failure


class BulkActionPayload(BaseModel):
    title_ids: list[str]
    action: str


class ShutdownStatus(TypedDict):
    tasks_closed: int
    force_killed: bool
    storage_synced: bool
