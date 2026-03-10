import hashlib
from pathlib import Path
from backend.logger import logger
from backend.config import settings
from backend.models import MountState
from backend.storage import mount_manager


class IntegrityManager:
    '''
    ARCHITECTURE: Provides non-blocking data validation. Uses hash verification to
    ensure that the encrypted data works as intended before importing to prevent
    corrupt files, bitrot, and other broken files from cluttering the library.
    '''

    def __init__(self):
        self._active_tasks: dict[str, float] = {}
        self._abort_requested = False

    def verify_file_integrity(self, file_path: Path, expected_size: int) -> bool:
        if mount_manager.check_mount_health(file_path.parent) == MountState.OFFLINE:
            logger.error(f"INTEGRITY ERROR: Cannot verify {
                         file_path.name} - Mount is OFFLINE.")
            return False

        if not file_path.exists():
            logger.error(
                f"INTEGRITY ERROR: File vanished before verification: {file_path}")
            return False

        try:
            actual_size = file_path.stat().st_size

            if expected_size == 0:
                logger.warning(f"INTEGRITY WARNING: No expected size for {
                               file_path.name}. Skipping verification.")
                return True

            if actual_size != expected_size:
                logger.error(f"INTEGRITY ERROR: Size mismatch for {file_path.name}. "
                             f" Expected: {expected_size}, Actual: {actual_size}")
                return False

            return True
        except OSError as e:
            logger.error(f"INTEGRITY ERROR: OS error during size verification of {
                         file_path}: {e}")
            return False

    def calculate_sha1(self, file_path: Path, title_id: str) -> str | None:
        self._active_tasks[title_id] = 0.0
        hash_function = hashlib.sha1()

        try:
            total_size = file_path.stat().st_size
            bytes_read = 0

            with file_path.open("rb") as f:
                for chunk in iter(lambda: f.read(settings.io_buffer_size), b""):
                    if self._abort_requested:
                        logger.warning(
                            f"INTEGRITY WARNING: Hash aborted for {title_id}")
                        return None

                    hash_function.update(chunk)
                    bytes_read += len(chunk)

                    self._active_tasks[title_id] = round(
                        (bytes_read / total_size) * 100, 1)

            return hash_function.hexdigest()

        except OSError as e:
            logger.error(f"INTEGRITY ERROR: Hash failed for {
                         file_path.name}: {e}")
            return None
        finally:
            self._active_tasks.pop(title_id, None)

    def verify_structure(self, folder_path: Path, platform: str) -> bool:
        if not folder_path.is_dir():
            return False

        platform_manifests = {
            "vita": ["eboot.bin", "sce_sys/param.sfo"],
            "psp": ["EBOOT.PBP"],
            # PS1 Classics are delivered as PBP files from NPS
            "psx": ["EBOOT.PBP"]
        }

        #! ARCHITECTURE: mapping ps1, psoriginal aliases to 'psx' to prevent failure
        target_platform = platform.lower()
        if target_platform in ["ps1", "psoriginal"]:
            target_platform = "psx"

        required = platform_manifests.get(target_platform, [])
        if not required:
            logger.warning(
                f"INTEGRITY WARNING: No manifest defined for platform: {platform}")
            return True  # ! ARCHITECTURE: permissive for unknown platforms to prevent a lock out

        for item in required:
            #! ARCHITECTURE: pkg2zip/NPS structures can be deeply nested like: /app/PCSB0001/...
            # using rglob here to verify the files exist if they are anywhere in the decrypted folder
            found = any(f.parts[-1].lower() == item.split('/')[-1].lower()
                        for f in folder_path.rglob('*'))
            #! unless if it's a PS Vita game, param.sfo must be in a sce_sys subfolder
            if "sce_sys" in item:
                found = any("sce_sys" in str(f).lower() and "param.sfo" in f.name.lower()
                            for f in folder_path.rglob('*.sfo'))

            if not found:
                logger.error(f"INTEGRITY ERROR: {platform.upper()} verification failed. "
                             f"Missing critical component: {item}")
                return False

        logger.info(f"INTEGRITY: {platform.upper()
                                  } structure verified for {folder_path.name}")
        return True


integrity_manager = IntegrityManager()
