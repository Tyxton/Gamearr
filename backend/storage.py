import time
import shutil
from pathlib import Path
from typing import TypedDict, Union

from backend.logger import logger
from backend.exceptions import StorageError
from backend.models import MountState
from backend.config import settings


class MountManager:
    ''' 
    ARCHITECTURE: Replaces the passive StorageManager with active hardware awareness.
    All static methods are removed to enforce service level state tracking. 
    '''

    def __init__(self):
        self._mount_cache: dict[str, MountState] = {}
        self._failure_timestamps: dict[str, float] = {}

    def _update_state(self, path: Path, state: MountState):
        path_str = str(path.resolve())
        if self._mount_cache.get(path_str) != state:
            self._mount_cache[path_str] = state
            logger.info(f"STORAGE: Mount {path_str} is now {state.upper()}")

    def check_mount_health(self, path: Path) -> MountState:
        '''
        ARCHITECTURE: Performs a non-destructive STAT check, if the mount is stale or
        unresponsive, it updates the stat map.
        '''
        path_str = str(path.resolve())
        try:
            if path.exists():
                self._update_state(path, MountState.ONLINE)
                return MountState.ONLINE
            else:
                self._update_state(path, MountState.OFFLINE)
                return MountState.OFFLINE
        except (OSError, PermissionError):
            self._update_state(path, MountState.OFFLINE)
            self._failure_timestamps[path_str] = time.time()
            return MountState.OFFLINE

    def ensure_dir(self, path: Path) -> None:
        '''
        ARCHITECTURE: Reject if the parent mount is flagged as OFFLINE
        '''
        if self.check_mount_health(path) == MountState.OFFLINE:
            raise StorageError(
                f"I/O ABORTED: Target mount {path} is OFFLINE.")

        try:
            path.mkdir(parents=True, exist_ok=True)
            if settings.target_uid and settings.target_gid:
                self._apply_identity_mapping(path)
        except (OSError, PermissionError) as e:
            self._update_state(path, MountState.OFFLINE)
            raise StorageError(f"Cannot create directory {path}: {e}")

    def _apply_identity_mapping(self, path: Path):
        '''
        ARCHITECTURE: Enforce UID/GID for LXC/NAS compatibility.
        '''
        uid = settings.target_uid
        gid = settings.target_gid

        if uid is not None and gid is not None:
            try:
                shutil.chown(str(path), user=uid, group=gid)
            except (OSError, PermissionError) as e:
                logger.warning("STORAGE WARNING: Could not set ownership on {path} "
                               f"Error: {e}. (Common on non-POSIX filesystems or unpriviledged LXCs)")
                pass

    def atomic_move(self, src: Path, dst: Path) -> None:
        if self.check_mount_health(dst.parent) == MountState.OFFLINE:
            raise StorageError(f"IMPORTING ABORTED: Destination mount {
                               dst.parent} is OFFLINE.")
        if not src.exists():
            raise StorageError(f"SOURCE MISSING: {src}")
        if dst.exists():
            logger.warning(
                f"STORAGE WARNING: Overwriting existing destination: {dst}")
            self.purge_dir(dst)

        try:
            src.rename(dst)
            logger.info("STORAGE: Atomic rename successful: {src.name}")
        except (OSError, PermissionError):
            logger.warning(f"STORAGE WARNING: Atomic rename failed. Starting buffered copy: {
                           src.name} -> {dst.name}")
            self._buffered_copy(src, dst)

    def _buffered_copy(self, src: Path, dst: Path) -> None:
        '''
        ARCHITECTURE: Moving from byte-copy to buffered copy
        uses io_buffer_size from settings to mitigate NAS i/o wait
        '''
        try:
            if src.is_dir():
                shutil.copytree(
                    src, dst,
                    dirs_exist_ok=True,
                    copy_function=shutil.copy
                )
            else:
                shutil.copy(src, dst)

            if not dst.exists():
                raise StorageError(
                    "Copy verification failed: Destination does not exist.")

            self.purge_dir(src) if src.is_dir() else src.unlink()

        except Exception as e:
            raise StorageError(f"BUFFERED COPY FATAL: {str(e)}")

    def purge_dir(self, path: Path) -> None:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        except (OSError, PermissionError) as e:
            logger.error(f"CLEANUP ERROR: Could not purge {path}: {e}")

    class DiskTelemetry(TypedDict):
        total_gb: int
        used_gb: int
        free_gb: int
        percent: float
        status: str

    def get_disk_telem(self, path: Path) -> DiskTelemetry:
        '''
        ARCHITECTURE: Returns zero'd data if the mount is OFFLINE instead of crashing the API
        '''
        if self.check_mount_health(path) == MountState.OFFLINE:
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0.0, "status": "offline"}

        try:
            total, used, free = shutil.disk_usage(str(path))
            return {
                "total_gb": total // (2**30),
                "used_gb": used // (2**30),
                "free_gb": free // (2**30),
                "percent": round((used / total) * 100, 1) if total > 0 else 0.0,
                "status": "online"
            }
        except (OSError, PermissionError):
            return {
                "total_gb": 0,
                "used_gb": 0,
                "free_gb": 0,
                "percent": 0.0,
                "status": "degraded"
            }

    def is_populated(self, path: Path) -> bool:
        try:
            return path.is_dir() and any(path.iterdir())
        except (OSError, PermissionError):
            return False


mount_manager = MountManager()
