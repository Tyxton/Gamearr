from pathlib import Path
import threading
import time

from backend import database, downloader, extractor
from backend.models import GameStatus, MountState
from backend.logger import logger
from backend.config import settings
from backend.storage import mount_manager
from backend.scout import scout_title
from backend.exceptions import StorageError
from backend.integrity import integrity_manager

shutdown_event = threading.Event()


def start_worker():
    logger.info("Worker standby... waiting for Database initialization.")

    while not shutdown_event.is_set():
        try:
            get_next = database.get_next_queued_task()
            if not get_next:
                return

            title_id = get_next['title_id']
            name = get_next['name']
            platform = get_next['platform']
            pkg_url = get_next['pkg_url']
            license_key = get_next['license_key']
            expected_size = get_next['size_total']

            logger.info(f"Found in queue: {name} ({platform.upper()})")

            database.update_queue_status(title_id, GameStatus.DOWNLOADING)
            success = downloader.download_pkg(pkg_url, title_id, name)

            if success:
                database.update_queue_status(title_id, GameStatus.EXTRACTING)

                from backend.downloader import get_safe_name
                safe_folder = get_safe_name(name, title_id)
                source_folder: Path = settings.incomplete_dir / safe_folder
                pkg_file: Path = source_folder / f"{title_id}.pkg"

                #! ARCHITECTURE: verify source PKG size before extraction,
                # ensures we don't waste time extracting a partial/currupt download
                if not integrity_manager.verify_file_integrity(pkg_file, expected_size):
                    logger.error(f"INTEGRITY ERROR: PKG size mismatch for {
                                 name}. Curruption detected.")
                    database.update_queue_status(title_id, GameStatus.FAILED)
                    database.update_queue_status(
                        title_id, "Downloaded PKG failed size parity check.")
                    continue

                if extractor.extract_pkg(pkg_file, license_key, platform):
                    database.update_queue_status(
                        title_id, GameStatus.VERIFYING)
                    logger.info(
                        "Extraction Complete. Veryifying file integrity...")

                    if not integrity_manager.verify_structure(source_folder, platform):
                        logger.error(f"INTEGRITY ERROR: {
                                     name} extraction failed structural validation.")
                        database.update_queue_status(
                            title_id, GameStatus.FAILED)
                        database.update_queue_status(
                            title_id, "Extraction produced invalid file structure.")
                        continue

                    database.update_queue_status(
                        title_id, GameStatus.IMPORTING)
                    final_destination: Path = settings.library_dir / safe_folder
                    logger.info(f"Verification Complete. Starting physical transfer of {
                                title_id} to library...")

                    max_retries = 5
                    attempts = 0

                    while attempts < max_retries:
                        if shutdown_event.is_set():
                            break

                        try:
                            mount_manager.atomic_move(
                                source_folder, final_destination)
                            logger.info(
                                f"Import Complete: {name} successfully commited to library.")

                            database.update_queue_status(
                                title_id, GameStatus.COMPLETED)
                            scout_title(title_id, name)

                        except StorageError as e:
                            attempts += 1
                            err_msg = str(e)

                            #! ARCHITECTURE: check if the error is a transient
                            # network issue or a fatal logic error

                            is_transient = any(x in err_msg.upper() for x in [
                                               "TIMEOUT", "OFFLINE", "VANISHED", "HOST"])

                            if is_transient and attempts < max_retries:
                                logger.warning(f"IMPORT STALLED: {
                                               name} - {err_msg}. Waiting for mount recovery (Attempt {attempts}/{max_retries})")
                                database.update_queue_status(
                                    title_id, GameStatus.STALLED)
                                database.update_queue_error(
                                    title_id, f"Transient I/O Fault: {err_msg}")

                                wait_limit = 20
                                waited = 0
                                while waited < wait_limit:
                                    if shutdown_event.is_set() or mount_manager.check_mount_health(settings.library_dir) == MountState.ONLINE:
                                        break
                                    time.sleep(30)
                                    waited += 1

                                continue
                            else:
                                #! ARCHITECTURE: Hard failure on max retries or fatal error (disk full/permissions)
                                logger.error(f"IMPORT FATAL: {name} failed aftrer {
                                             attempts} attempts. Error: {err_msg}")
                                database.update_queue_status(
                                    title_id, GameStatus.FAILED)
                                database.update_queue_error(title_id, err_msg)
                                break
        except Exception as e:
            logger.error(f"WORKER CRITICAL: Unexpected thread collapse: {e}")
            time.sleep(10)


if __name__ == "__main__":
    start_worker()
