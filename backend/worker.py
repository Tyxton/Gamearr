import time
import os
import shutil
from typing import final
from backend import database, downloader, extractor
from backend.models import GameStatus
from backend.logger import logger

# Force absolute path if not already to avoid permission failures
raw_incomplete = os.getenv("INCOMPLETE_DIR", "/downloads")
if not raw_incomplete.startswith("/"):
    raw_incomplete = f"/{raw_incomplete}"
INCOMPLETE_DIR = os.path.abspath(raw_incomplete)

raw_library = os.getenv("LIBRARY_DIR", "/library")
if not raw_library.startswith("/"):
    raw_library = f"/{raw_library}"
LIBRARY_DIR = os.path.abspath(raw_library)


def start_worker():
    logger.info("Worker standby... waiting for Database initialization.")

    while True:
        try:
            # check for next pending game
            get_next = database.get_next_queued_task()
            if not get_next:
                return  # nothing to do, return to the async wrapper's sleep

            title_id = get_next['title_id']
            name = get_next['name']
            platform = get_next['platform']
            pkg_url = get_next['pkg_url']
            license_key = get_next['license_key']

            logger.info(f"\nFound in queue: {name} ({platform.upper()})")

            # update status
            database.update_queue_status(title_id, GameStatus.DOWNLOADING)

            success = downloader.download_pkg(pkg_url, title_id, name)

            if success:
                logger.info(
                    f"Download complete. Starting extraction for {title_id}...")
                database.update_queue_status(title_id, GameStatus.EXTRACTING)

                # contruct path
                from backend.downloader import get_safe_name
                # add the title_id so that the folder is globally unique
                safe_folder = get_safe_name(name, title_id)

                pkg_file = os.path.join(
                    INCOMPLETE_DIR, safe_folder, f"{title_id}.pkg")

                # now extract
                if extractor.extract_pkg(pkg_file, license_key, platform):
                    logger.info(
                        f"Extraction Complete. Moving to Library: {name}")

                    # Importing Logic
                    database.update_queue_status(
                        title_id, GameStatus.IMPORTING)
                    source_folder = os.path.join(INCOMPLETE_DIR, safe_folder)
                    final_destination = os.path.join(LIBRARY_DIR, safe_folder)
                    try:
                        if os.path.exists(final_destination):
                            shutil.rmtree(final_destination)

                        # Atomic Moves: 1. Try Rename, 2. Fall back to copytree+rmtree
                        try:
                            os.rename(source_folder, final_destination)
                        except OSError:
                            logger.info(
                                f"Cross-device move detected for {name}. Copying...")
                            shutil.copytree(source_folder, final_destination)
                            shutil.rmtree(source_folder)

                        database.update_queue_status(
                            title_id, GameStatus.COMPLETED)
                        # Trigger Scout for just this ID
                        from backend.scout import scout_title
                        scout_title(title_id, name)
                    except Exception as e:
                        logger.error(f"Import Failed: {e}")
                        database.update_queue_status(
                            title_id, GameStatus.FAILED)
                else:
                    logger.error(f"Extraction failed for {name}")
                    database.update_queue_status(title_id, GameStatus.FAILED)
            else:
                database.update_queue_status(title_id, GameStatus.FAILED)

        except Exception as e:
            logger.error(f"Worker Error during {name}: {e}")


if __name__ == "__main__":
    start_worker()
