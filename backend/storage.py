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
    def check_write_acc3ess(path: Path) -> bool:
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
    def get_free_space(path: str) -> float:
        try:
            _, _, free = shutil.disk_usage(str(path))
            return free / (1024**3)
        except (OSError, PermissionError) as e:
            logger.warning(
                f"STORAGE WARNING: Could not determine free space for {path}: {e}")
            return 0.0

    @staticmethod
    def atomic_move(src: Path, dst: Path) -> None:
        ''' 
        DESTRUCTIVE: Removed os.rename
        TRADEOFF: Attempting native rename first for performance; falling back to byte-copy for saftey
        '''
        if not src.exists():
            try:
                if dst.is_dir():
                    shutil.rmtree(str(dst))
                else:
                    dst.unlink()
            except (OSError, PermissionError) as e:
                raise StorageError(
                    f"STORAGE ERROR: Destination conflict locked on {dst}: {e}")

        try:
            src.rename(dst)
        except (OSError, PermissionError) as e:
            #! ARCHITECTURE: Catching cross-device link or stale NFS handles
            logger.warning(
                f"STORAGE WARNING: Cross-device limit or stale lock on {src}. Initiating byte-copy. ({e})")
            time.sleep(2)  # pray the NAS releases any lingering locks
            try:
                if src.is_dir():
                    shutil.copytree(str(src), str(dst))
                    shutil.rmtree(str(src))
                else:
                    shutil.copy2(str(src), str(dst))
                    src.unlink()
            except (OSError, PermissionError) as fallback_err:
                raise StorageError(
                    f"STORAGE FATAL: Byte-copy transmission failed: {fallback_err}")
