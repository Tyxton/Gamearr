import subprocess
import re
import time
from pathlib import Path

from backend.logger import logger
from backend.config import settings
from backend.storage import StorageManager
from backend import database
from backend.worker import shutdown_event

PROGRESS_RE = re.compile(r'\((\d+)%\)')


def download_pkg(url, title_id, name):
    safe_name = get_safe_name(name, title_id)

    #! DESTRUCTIVE: os.makedirs removed,
    download_dir: Path = settings.incomplete_dir / safe_name

    #! ARCHITECTURE: Purge ghost data from previous failed/crashed attempts.
    StorageManager.purge_dir(download_dir)

    #! ARCHITECTURE: StorageManager ensures the mount is writable **before** calling aria2c
    StorageManager.ensure_dir(download_dir)

    command = [
        # 16 threads split to allow full saturation of gigabit lan
        "aria2c", "-x", "16", "-s", "16",
        "-d", str(download_dir), "-o", f"{title_id}.pkg",
        # connect timeout set to 30s to catch drops early
        "--connect-timeout=30", "--timeout=60", "--split=16",
        "--summary-interval=1", "--console-log-level=notice",
        "--allow-overwrite=true", url
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        if process.stdout is None:
            logger.error(f"DOWNLOADER ERROR: Pipe collapsed for {name}")
            return False

        last_update_time = 0.0
        current_percent = 0

        for line in process.stdout:
            if shutdown_event.is_set():
                #! Abors native subprocess gracefully preventing Uvicorn hang
                process.terminate()
                logger.warning(f"DOWNLOADER WARNING: Terminating aria2c process for {
                               name} due to system shutdown.")
                return False

            match = PROGRESS_RE.search(line)
            if match:
                new_percent = int(match.group(1))

                if new_percent != current_percent and (time.time() - last_update_time) > 2.0:
                    current_percent = new_percent
                    last_update_time = time.time()

                    update_progress(title_id, float(current_percent), 0, 0)
                    logger.info(f"Downloading {name}: {current_percent}%")

        process.wait()

        if process.returncode == 0:
            update_progress(title_id, 100.0, 0, 0)
            return True
        else:
            logger.error(f"CRITICAL ERROR: aria2c exited with status {
                         process.returncode}")
            return False
    except (OSError, subprocess.SubprocessError) as e:
        #! ARCHITECTURE: isolated to OS and subprocess layers to trap pipe collapses
        # and execution faults cleanly without swalling standard python runtime errors.
        logger.error(f"DOWNLOADER ERROR: Transfer failed for {name}: {e}")


def update_progress(title_id: str, progress: float, size_current: int, size_total: int) -> None:
    conn = database.get_db_connection()
    conn.execute('''
        UPDATE queue
        SET progress = ?, size_current = ?, size_total = ?
        WHERE title_id = ?
    ''', (progress, size_current, size_total, title_id))
    conn.commit()
    conn.close()


def get_safe_name(name: str, title_id: str | None = None) -> str:
    ascii_name = name.encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r'[^a-zA-Z0-9\s\-]', '', ascii_name).strip()
    clean = re.sub(r'\s+', ' ', clean)
    clean = clean.replace("..", "").replace("/", "").replace("\\", "")

    if title_id:
        return f"{clean} [{title_id.upper()}]"
    return clean
