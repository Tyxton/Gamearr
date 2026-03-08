import time
from pathlib import Path

from backend import database, downloader, extractor
from backend.models import GameStatus
from backend.logger import logger
from backend.config import settings
from backend.storage import StorageManager
from backend.scout import scout_title


def start_worker():
    #! ARCHITECTURE: This loop is designed to be called via asyncio.to_thread.
    # it consumes the SQLite queue sequentially to prevent file lock contention.
    logger.info("Worker standby... waiting for Database initialization.")

    while True:
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

                    try:
                        #! ARCHITECTURE: Utilizing StorageManager for atomic operations across shares
                        #! DESTRUCTIVE: This breaks the previous shutil.move
                        StorageManager.atomic_move(
                            source_folder, final_destination)

                        database.update_queue_status(
                            title_id, GameStatus.COMPLETED)
                        scout_title(title_id, name)
                    except Exception as e:
                        logger.error(f"Import Failed: {e}")
                        database.update_queue_status(
                            title_id, GameStatus.FAILED)
                else:
                    logger.error(f"Extraction Failed: {name}")
                    database.update_queue_status(title_id, GameStatus.FAILED)
            else:
                database.update_queue_status(title_id, GameStatus.FAILED)
        except Exception as e:
            logger.error(f"Worker Error: {e}")


if __name__ == "__main__":
    start_worker()
