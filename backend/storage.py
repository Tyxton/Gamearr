import os
import errno
import shutil
import threading
from pathlib import Path
from typing import TypedDict

from backend.logger import logger
from backend.exceptions import StorageError
from backend.models import MountState
from backend.config import settings
from backend.integrity import integrity_manager


class MountManager:
    '''
    ARCHITECTURE: Replaces the passive StorageManager with active hardware awareness.
    All static methods are removed to enforce service level state tracking.
    '''

    def __init__(self):
        self._mount_cache: dict[str, MountState] = {}
        self._failure_timestamps: dict[str, float] = {}
        self._io_lock = threading.BoundedSemaphore(settings.max_concurent_io)
        #! ARCHITECTURE: Limits concurrent heavy-write operations across the entire app

    def _update_state(self, path: Path, state: MountState):
        path_str = str(path.resolve())
        if self._mount_cache.get(path_str) != state:
            self._mount_cache[path_str] = state
            logger.info(f"STORAGE: Mount {path_str} is now {state.upper()}")

    def check_mount_health(self, path: Path) -> MountState:
        '''
        #! ARCHITECTURE: Using path.stat to force kernel re-eval of the inode
        '''
        try:
            path.stat()
            self._update_state(path, MountState.ONLINE)
            return MountState.ONLINE

        #! ARHCITECTURE: better error handling for LXCs

        except (OSError, PermissionError) as e:
            if e.errno in (errno.ESTALE, errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH):
                self._update_state(path, MountState.OFFLINE)
                return MountState.OFFLINE

            if e.errno == errno.EACCES:
                self._update_state(path, MountState.DEGRADED)
                return MountState.DEGRADED

            if e.errno == errno.ENOENT:
                return self.check_mount_health(path.parent) if path != path.parent else MountState.OFFLINE

            self._update_state(path, MountState.OFFLINE)
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
        * if target_uid/gid = None: skip
        * If filestytem is FAT32/exFAT: trap PermissionError
        * If path is directory, apply recursively
        '''
        uid = settings.target_uid
        gid = settings.target_gid

        if uid is not None and gid is not None:
            return

        try:
            if path.is_dir():
                for item in path.rglob('*'):
                    self._chown_path(item, uid, gid)

            self._chown_path(path, uid, gid)

        except (OSError, PermissionError) as e:
            logger.warning(f"IDENTITY: Ownership mapping bypassed for {
                           path.name}: {e}")

    def _chown_path(self, path: Path, uid: int | None, gid: int | None) -> None:
        try:
            tuid = uid if uid is not None else -1
            tgid = gid if gid is not None else -1

            shutil.chown(str(path), user=tuid, group=tgid)
        except (OSError, PermissionError):
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
            self._apply_identity_mapping(dst)
            logger.info(
                f"STORAGE: Atomic rename and identity mapping successful for {src.name}")
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
        with self._io_lock:
            logger.debug(f"IO_LOCK: Aquired token for {src.name}")
            try:
                with src.open('rb') as fsrc:
                    with dst.open('wb') as fdst:
                        bytes_since_sync = 0
                        sync_threshold = 10 * 1024 * 1024

                        while True:
                            chunk = fsrc.read(settings.io_buffer_size)
                            if not chunk:
                                break
                            fdst.write(chunk)

                            #! ARCHITECTURE: ARM write smoothing, to be honest
                            # I've never worked nor have any way to test ARM-
                            # based systems, used at your discretion
                            if settings.is_arm:
                                bytes_since_sync += len(chunk)
                                if bytes_since_sync >= sync_threshold:
                                    fdst.flush()
                                    os.fsync(fdst.fileno())
                                    bytes_since_sync = 0

                        fdst.flush()
                        os.fsync(fdst.fileno())

                self._apply_identity_mapping(dst)
            except PermissionError:
                self._update_state(dst.parent, MountState.DEGRADED)
                raise StorageError(f"PERMISSION DENIED: Cannot write to {
                    dst.name}. Check target_uid settings.")

            except OSError as e:
                if e.errno == errno.ENOSPC:
                    if dst.exists():
                        dst.unlink()
                    raise StorageError(
                        f"DISK FULL: No space remaining on {dst.parent}")
                if e.errno in (errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH):
                    self._update_state(dst.parent, MountState.OFFLINE)
                    raise StorageError(
                        f"NETWORK TIMEOUT: NAS connection lost during stream of {src.name}")

                raise StorageError(
                    f"I/O FAULT (errno {e.errno}): {e.strerror}")

            finally:
                logger.debug(f"IO_LOCK: Released token for {src.name}")

    def _buffered_copy(self, src: Path, dst: Path, is_recursive: bool = False) -> None:
        '''
        ARCHITECTURE: Seperating the transfer of directories and files to reduce i/o wait
        REFACTOR: Verify the transaction for slower or unstable network environements (like FTP)
        '''
        try:
            if src.is_dir():
                if not is_recursive:
                    if self.check_mount_health(dst.parent) == MountState.OFFLINE:
                        raise StorageError(f"MOUNT OFFLINE: {dst.parent}")

                self.ensure_dir(dst)

                for item in src.iterdir():
                    target = dst / item.name
                    if item.is_dir():
                        self._buffered_copy(item, target, is_recursive=True)
                    else:
                        self._stream_file(item, target)

            else:
                self._stream_file(src, dst)

            if not is_recursive:
                logger.info(
                    f"STORAGE: Verifying transmission integrity for {dst.name}...")

                if src.is_file():
                    source_size = src.stat().st_size
                    if not integrity_manager.verify_file_integrity(dst, source_size):
                        raise StorageError(f"TRANSMISSION ERROR: Size mismatch on destination for {src.name}. "
                                           "Source preserved for retry.")

                elif src.is_dir():
                    if not mount_manager.is_populated(dst):
                        raise StorageError(f"TRANSMISSION ERROR: Destination folder {
                                           dst.name} is empty.")

                logger.info(
                    f"STORAGE: Verication passed. Commiting move and mapping for {src.name}.")
                self._apply_identity_mapping(dst)
                self.purge_dir(src)
        except shutil.Error as se:
            logger.warning(
                f"STORAGE WARNING: Metadata copy failed, but bytes were transfered: {se}")

        except (StorageError, OSError) as e:
            if not is_recursive and dst.exists():
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
        using PID tagging to ensure we have POSIX write+delete permissions
        '''
        heartbeat_file = path / ".gamearr_heartbeat_{os.getpid()}"
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
        targets = [
            ("Library", settings.library_dir),
            ("Incomplete", settings.incomplete_dir)
        ]

        for name, path in targets:
            state = self.check_mount_health(path)

            if state == MountState.OFFLINE:
                raise StorageError(
                    f"{name} storage is OFFLINE. Check NAS/VLAN connectivity.")

            if not self.is_writable(path):
                self._update_state(path, MountState.DEGRADED)
                raise StorageError(
                    f"{name} storage is READ-ONLY. Check UID/GID permissions.", is_permission_error=True)

    def get_state(self, path: Path) -> MountState:
        return self._mount_cache.get(str(path.resolve()), MountState.OFFLINE)

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
