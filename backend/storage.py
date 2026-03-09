import time
import shutil
from pathlib import Path

from backend.logger import logger
from backend.exceptions import StorageError


class StorageManager:
    ''' 
    Isolates all physical layer interactions.
    SMB/NFS environments frequently exhibit stale file locks or propogate cross-device link errors.
    '''
    @staticmethod
    def ensure_dir(path: Path) -> None:
        ''' 
        DESTRUCTIVE: Replaces os.makedirs to explicitly trap remote mount permission drops
        ARCHITECTURE: Trap remote mount permission drops to prevent container crash
        '''

        try:
            path.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            #! OPERATOR: Usually means that theres a Proxmox UID/GID mapping mismatch on the LXC mount
            logger.error(f"STORAGE ERROR: Directory constraint on {path}: {e}")
            raise StorageError(f"Cannot create directory {path}: {e}")

    @staticmethod
    def check_write_access(path: Path) -> bool:
        test_file = path / '.gamearr_test'
        try:
            StorageManager.ensure_dir(path)
            test_file.write_text('test')
            test_file.unlink()
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"STORAGE ERROR: Write test failed on {path}: {e}")
            return False

    @staticmethod
    def purge_dir(path: Path) -> None:
        '''
        DESTRUCTIVE: Specifically for cleaning up any ghost data from failed/interuppted tasks.
        '''
        if not StorageManager.path_exists(path):
            return

        try:
            for item in path.glob('**/*'):
                if item.is_file():
                    item.unlink()
            shutil.rmtree(str(path))
        except (OSError, PermissionError) as e:
            raise StorageError(
                f"STROAGE FATAL: Could not purge ghost data at {path}: {e}")

    @staticmethod
    def path_exists(path: Path) -> bool:
        '''
        ARCHITECTURE: Evalutes path existence while trapping stale network mount states
        '''
        try:
            return path.exists()
        except (OSError, PermissionError) as e:
            logger.warning(
                f"STORAGE WARNING: Path check blocked. Mount may be degraded: {e}")
            return False

    @staticmethod
    def get_disk_telem(path: Path) -> dict[str, float | int]:
        '''
        ARCHITECTURE: Encapsulates shutil.disk_usage to ensure umounted/stale NAS paths
        do not trigger an uncaught OSError during API health polls.
        '''
        try:
            total, used, free = shutil.disk_usage(str(path))
            return {
                "total_gb": total // (2**30),
                "used_gb": used // (2**30),
                "free_gb": free // (2**30),
                "percent": round((used / total) * 100, 1) if total > 0 else 0.0
            }
        except (OSError, PermissionError) as e:
            logger.warning(
                f"STORAGE WARNING: Telemetry drop for capacity on {path}: {e}")
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0.0}

    @staticmethod
    def atomic_move(src: Path, dst: Path) -> None:
        ''' 
        DESTRUCTIVE: Removed os.rename
        TRADEOFF: Attempting native rename first for performance; falling back to byte-copy for saftey
        ARCHITECTURE: Specifically ignores metadata errors during byte-copy to support limited NAS permission sets
        '''
        if not src.exists():
            raise StorageError(f"STORAGE ERROR: Source path vanished: {src}")

        if dst.exists():
            StorageManager.purge_dir(dst)

        try:
            src.rename(dst)
        except (OSError, PermissionError) as e:
            #! ARCHITECTURE: Catching cross-device link or stale NFS handles
            logger.warning(
                f"STORAGE WARNING: Rename failed ({e}). Starting byte-copy to ({dst}).")
            time.sleep(2)  # pray the NAS releases any lingering locks
            try:
                if src.is_dir():
                    #! ARCHITECTURE: copytree with dirs_exist_ok and symlinks=False
                    # to maximize compatibility with network shares
                    shutil.copytree(str(src), str(
                        dst), dirs_exist_ok=True, copy_function=shutil.copy)
                    StorageManager.purge_dir(src)
                else:
                    #! ARCHITECTURE: dropping down to shutil.copy from copy2 to ignore metadata permission failures.
                    # initially, transferring metadata was a priority, but this failed in my own homelab setup.
                    shutil.copy(str(src), str(dst))
                    src.unlink()
            except Exception as fallback_err:
                #! DEBT: byte copies were falling with no error output as to why, catch everything
                raise StorageError(
                    f"STORAGE FATAL: Byte-copy transmission failed to {dst.parent}: {str(fallback_err)}")
