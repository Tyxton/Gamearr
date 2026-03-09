import subprocess
import os
import re
import subprocess
import time

from backend.logger import logger

# Force absolute path if not already to prevent permission errors
raw_incomplete = os.getenv("INCOMPLETE_DIR", "/downloads")
if not raw_incomplete.startswith("/"):
    raw_incomplete = f"/{raw_incomplete}"
INCOMPLETE_DIR = os.path.abspath(raw_incomplete)

PROGRESS_RE = re.compile(r'\((\d+)%\)')


def download_pkg(url, title_id, name):
    '''
    Uses aria2c to download the PKG files, creates a dedicated folder for each game
    '''
    from backend.downloader import get_safe_name
    from backend.database import update_queue_status

    safe_name = get_safe_name(name, title_id)
    download_dir = os.path.join(
        os.getenv("INCOMPLETE_DIR", "/downloads"), safe_name)
    os.makedirs(download_dir, exist_ok=True)

    # -x16 -s16 for speed, timeout kills the connection if its dead for 60s
    command = [
        "aria2c", "-x", "16", "-s", "16",
        "-d", download_dir, "-o", f"{title_id}.pkg",
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

        # Ensure the process and its stdout actually exist
        if process.stdout is None:
            logger.error(f"DOWNLOADER ERROR: Failed to open pipes for {name}")
            return False

        last_update_time = 0
        current_percent = 0

        for line in process.stdout:
            match = PROGRESS_RE.search(line)
            if match:
                new_percent = int(match.group(1))

                # Throttle DB and Log updates (Every 2 seconds)
                if new_percent != current_percent and (time.time() - last_update_time) > 2.0:
                    current_percent = new_percent
                    last_update_time = time.time()

                    update_progress(title_id, float(current_percent), 0, 0)
                    # Corrected logging (no end='\r')
                    logger.info(f"Downloading {name}: {current_percent}%")

        process.wait()

        if process.returncode == 0:
            # ensure we hit 100% in DB on finish
            update_progress(title_id, 100.0, 0, 0)
            return True
        else:
            logger.error(f"\nERROR: aria2c exited with error code {
                         process.returncode}")
            return False
    except Exception as e:
        logger.error(f"DOWNLOADER ERROR: for {name}: {e}")
        return False


def update_progress(title_id, progress, size_current, size_total):
    ''' Updates the database with the current download status for the UI '''
    from backend import database
    conn = database.get_db_connection()
    conn.execute('''
        UPDATE queue
        SET progress = ?, size_current = ?, size_total = ?
        WHERE title_id = ?
    ''', (progress, size_current, size_total, title_id))
    conn.commit()
    conn.close()


def get_safe_name(name, title_id=None):
    '''
    Creates a filesystem-safe name. Outright removes all non-ASCII characters
    and restricts to safe symbols. (for both filesystem and NAS)
    '''
    # Outright remove non-ASCII characters (like ™, ©, or emoji)
    # This turns something like "Metal Gear™ Solid" into "Metal Gear Solid"
    ascii_name = name.encode("ascii", "ignore").decode("ascii")

    # Strict REGEX (only allow letters, numbers, spaces, and hyphens
    clean = re.sub(r'[^a-zA-Z0-9\s\-]', '', ascii_name).strip()

    # collapse multiple spaces into one
    clean = re.sub(r'\s+', ' ', clean)

    # CRUCIAL: remove dots and slashes to prevent directory traversal
    clean = clean.replace("..", "").replace("/", "").replace("\\", "")

    if title_id:
        return f"{clean} [{title_id.upper()}]"
    return clean
