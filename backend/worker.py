from pathlib import Path
import threading

from backend import database, downloader, extractor
from backend.models import GameStatus
from backend.logger import logger
from backend.config import settings
from backend.storage import mount_manager
from backend.scout import scout_title
from backend.exceptions import StorageError

shutdown_event = threading.Event()


def start_worker():
    #! ARCHITECTURE: This loop is designed to be called via asyncio.to_thread.
    # it consumes the SQLite queue sequentially to prevent file lock contention.
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

            logger.info(f"Found in queue: {name} ({platform.upper()})")

            database.update_queue_status(title_id, GameStatus.DOWNLOADING)
            success = downloader.download_pkg(pkg_url, title_id, name)

            if success:
                logger.info(
                    f"Download complete. Starting extraction for {title_id}...")
                database.update_queue_status(title_id, GameStatus.EXTRACTING)

                from backend.downloader import get_safe_name
                safe_folder = get_safe_name(name, title_id)

                #! DESTRUCTIVE: os.path replaced in favor of pathlib
                source_folder: Path = settings.incomplete_dir / safe_folder
                pkg_file: Path = source_folder / f"{title_id}.pkg"

                if extractor.extract_pkg(pkg_file, license_key, platform):
                    logger.info(
                        f"extraction Complete. Moving to Library: {name}")

                    database.update_queue_status(
                        title_id, GameStatus.IMPORTING)
                    final_destination: Path = settings.library_dir / safe_folder
                    logger.info(f"IMPORT: Starting physical transfer of {
                                title_id} to library...")
                    try:
                        mount_manager.atomic_move(
                            source_folder, final_destination)
                        logger.info(
                            f"IMPORT: {name} successfully commited to library.")

                        database.update_queue_status(
                            title_id, GameStatus.COMPLETED)
                        scout_title(title_id, name)
                    except Exception as e:
                        #! DEBT: byte-copy transfer failed, capure specific error message
                        logger.error(f"Import Failed: {e}")
                        database.update_queue_error(title_id, str(e))
                        database.update_queue_status(
                            title_id, GameStatus.FAILED)
                else:
                    logger.error(f"Extraction Failed: {name}")
                    database.update_queue_status(title_id, GameStatus.FAILED)
        except Exception as e:
            #! ARCHITECTURE: The worker is a daemonized background loop.
            # it must trap broad exceptions at the highest level to survive unforseen drops
            # (e.g. SQLite lock timeouts) without exiting the thread permanently
            logger.error(f"Worker Error: {e}")


if __name__ == "__main__":
    start_worker()
