from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Standardize the structure for a game entry in the library or search


class GameModel(BaseModel):
    title_id: str
    platform: str
    region: str
    name: str
    pkg_url: str
    license_key: str | None = "MISSING"
    # centralized naming
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


class GameStatus(str, Enum):
    # Discover States
    AVAILABLE = "available"      # Not in DB, found via search

    # Queue/Worker States
    PENDING = "pending"          # In queue, waiting for worker
    DOWNLOADING = "downloading"  # aria2c is active
    EXTRACTING = "extracting"    # pkg2zip is active
    IMPORTING = "importing"      # Moving files to /library

    # Final States
    COMPLETED = "completed"      # Succcessfully installed
    FAILED = "failed"            # General Failure
