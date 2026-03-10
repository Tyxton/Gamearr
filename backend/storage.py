import time
import errno
import shutil
from pathlib import Path
from typing import TypedDict

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
        '''
        REFACTOR: Update the MountState during a failure
        '''
        if self.check_mount_health(dst.parent) == MountState.OFFLINE:
            raise StorageError(f"IMPORT ABORTED: Mount {
                               dst.parent} is OFFLINE.")

        try:
            src.rename(dst)
            logger.info(f"STORAGE: Atomic rename successful for {src.name}")
        except (OSError, PermissionError):
            logger.warning(
                f"STORAGE: Falling back to buffered stream for {src.name}")

            self._buffered_copy(src, dst)

    def _stream_file(self, src: Path, dst: Path) -> None:
        '''
        ARCHITECTURE: Transitioning to shutil.copyfileobj for files, this dodges the
        aggressive system calls for metadata/permissions preservations.
        Ultimately, reducing the i/o wait of the network share.
        '''
        try:
            with src.open('rb') as fsrc:
                with dst.open('wb') as fdst:
                    shutil.copyfileobj(
                        fsrc, fdst, length=settings.io_buffer_size)

            self._apply_identity_mapping(dst)
        except PermissionError:
            self._update_state(dst.parent, MountState.DEGRADED)
            raise StorageError(f"PERMISSION DENIED: Cannot write to {
                               dst.name}. Check target_uid settings.")

        except OSError as e:
            if e.errno == errno.ENOSPC:
                raise StorageError(
                    f"DISK FULL: No space remaining on {dst.parent}")
            if e.errno in (errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH):
                self._update_state(dst.parent, MountState.OFFLINE)
                raise StorageError(
                    f"NETWORK TIMEOUT: NAS connection lost during stream of {src.name}")

            raise StorageError(f"I/O FAULT (errno {e.errno}): {e.strerror}")

    def _buffered_copy(self, src: Path, dst: Path) -> None:
        '''
        ARCHITECTURE: Seperating the transfer of directories and files to reduce i/o wait
        '''
        try:
            if src.is_dir():
                self.ensure_dir(dst)

            for item in src.iterdir():
                target = dst / item.name
                if item.is_dir():
                    self._buffered_copy(item, target)
                else:
                    self._stream_file(item, target)

            else:
                self._stream_file(src, dst)

            if src.exists() and dst.exists():
                try:
                    if src.stat().st_size != dst.stat().st_size:
                        raise StorageError(
                            f"VERIFICATION FAILED: Size mismatch for {src.name}")
                except OSError:
                    self._update_state(dst.parent, MountState.OFFLINE)
                    raise StorageError(
                        "VERIFICATION FAILED: Mount vanished during integrity check.")

            self.purge_dir(src)

        except shutil.Error as se:
            logger.warning(
                f"STORAGE WARNING: Metadata copy failed, but bytes were transfered: {se}")

        except (StorageError, OSError) as e:
            if dst.exists():
                self.purge_dir(dst)
            raise e

    def purge_dir(self, path: Path) -> None:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        except (OSError, PermissionError) as e:
            logger.error(f"CLEANUP ERROR: Could not purge {path}: {e}")

    def is_writable(self, path: Path) -> bool:
        '''
        ARCHITECTURE: Can tell the difference between a stale mount and a RO permission error.
        '''
        heartbeat_file = path / ".gamearr_heartbeat"
        try:
            path.mkdir(parents=True, exist_ok=True)

            heartbeat_file.write_text("1")
            heartbeat_file.unlink()
            return True
        except (OSError, PermissionError) as e:
            logger.warning(f"STORAGE: Failed write text on {path}: {e}")
            return False

    def heartbeat_mon(self):
        '''
        ARCHITECTURE: Periodic health sweep for all configured hardware paths
        '''
        targets = {
            "Library": settings.library_dir,
            "Incomplete": settings.incomplete_dir
        }

        for name, path in targets.items():
            stat_test = self.check_mount_health(path)
            if stat_test == MountState.ONLINE:
                if not self.is_writable(path):
                    self._update_state(path, MountState.DEGRADED)
                else:
                    self._update_state(path, MountState.ONLINE)

    def preflight_test(self) -> None:
        '''
        ARCHITECTURE: Validates the entire i/o pipeline before accepting new tasks.
        '''
        incomplete_state = self.check_mount_health(settings.incomplete_dir)
        if incomplete_state == MountState.OFFLINE:
            raise StorageError(
                "Download directory is OFFLINE. Check NAS connectivity. Aborting...")
        if incomplete_state == MountState.DEGRADED:
            raise StorageError(
                "Download directory is READ-ONLY. Check NAS/LXC/Docker permissions. Aborting...")

        library_state = self.check_mount_health(settings.library_dir)
        if library_state == MountState.OFFLINE:
            raise StorageError(
                "Library directory is OFFLINE. Check NAS connectivity. Aborting...")
        if library_state == MountState.DEGRADED:
            raise StorageError(
                "Library directory is READ-ONLY. Check destination privileges. Aborting...")

        if not self.is_writable(settings.incomplete_dir):
            raise StorageError(
                "Pre-flight write test failed on download buffer. Aborting...")

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
        state = self.check_mount_health(path)

        if self.check_mount_health(path) == MountState.OFFLINE:
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0.0, "status": state.value}

        try:
            total, used, free = shutil.disk_usage(str(path))
            return {
                "total_gb": total // (2**30),
                "used_gb": used // (2**30),
                "free_gb": free // (2**30),
                "percent": round((used / total) * 100, 1) if total > 0 else 0.0,
                "status": state.value
            }
        except (OSError, PermissionError):
            return {
                "total_gb": 0,
                "used_gb": 0,
                "free_gb": 0,
                "percent": 0.0,
                "status": MountState.OFFLINE.value
            }

    def is_populated(self, path: Path) -> bool:
        try:
            return path.is_dir() and any(path.iterdir())
        except (OSError, PermissionError):
            return False


mount_manager = MountManager()
