import subprocess
import re
import time
from pathlib import Path

from backend.logger import logger
from backend.config import settings
from backend.storage import MountManager
from backend import database
from backend.worker import shutdown_event
from backend.models import GameStatus

PROGRESS_RE = re.compile(r'\((\d+)%\)')


def download_pkg(url, title_id, name, expected_size: int):
    safe_name = get_safe_name(name, title_id)
    download_dir: Path = settings.incomplete_dir / safe_name
    pkg_file = download_dir / f"{title_id}.pkg"

    MManager = MountManager()
    MManager.ensure_dir(download_dir)

    if pkg_file.exists():
        try:
            actual_size = pkg_file.stat().st_size
            if actual_size == expected_size:
                logger.info(f"DOWNLOADER: {
                            name} already exists and matches size. Skipping download.")
                return True
            if actual_size > expected_size:
                logger.warning(f"DOWNLOADER: size mismatch for existing {
                               name}. Purging.")
                MManager.purge_dir(pkg_file)
        except OSError as e:
            logger.error(f"DOWNLOADER: Failed to stat existing file: {e}")

    threads = "4" if settings.is_arm else "16"

    command = [
        "aria2c", "-x", threads, "-s", threads,
        "-d", str(download_dir), "-o", f"{title_id}.pkg",
        "--connect-timeout=30", "--timeout=60", "--split=16",
        "--summary-interval=1", "--console-log-level=notice",
        "-continue=true", "--allow-overwrite=false", "--allow-file-renaming=false", url
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
                update_progress(title_id, current_percent, 0, 0)
                database.update_queue_status(title_id, GameStatus.PENDING)
                process.terminate()
                logger.warning(f"DOWNLOADER WARNING: Terminating aria2c process for {
                               name} due to system shutdown.")
                return False

            match = PROGRESS_RE.search(line)
            if match:
                new_percent = int(match.group(1))
                if new_percent != current_percent and (time.time() - last_update_time) > 5.0:
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
