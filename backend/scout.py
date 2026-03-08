import re
import time
from pathlib import Path

from backend import database, metadata
from backend.models import GameStatus
from backend.logger import logger
from backend.config import settings


def run_meta_scout(single_id=None):
    conn = database.get_db_connection()
    target_ids = []

    if single_id:
        target_ids.append(single_id.upper())
    else:
        #! DESTRUCTIVE: os module removed. iterdir() protects against symlink loops natively.
        if settings.library_dir.exists():
            for folder in settings.library_dir.iterdir():
                if folder.is_dir():
                    match = re.search(r'\[(.*?)\]', folder.name)
                    if match:
                        target_ids.append(match.group(1).upper())

        active_statuses = [
            GameStatus.PENDING,
            GameStatus.DOWNLOADING,
            GameStatus.EXTRACTING,
            GameStatus.IMPORTING,
            GameStatus.FAILED,
            GameStatus.COMPLETED
        ]

        placeholders = ', '.join(['?'] * len(active_statuses))
        sql = f"SELECT title_id FROM queue WHERE status IN ({placeholders})"

        queued_items = conn.execute(
            sql, [s.value for s in active_statuses]).fetchall()
        for item in queued_items:
            target_ids.append(item['title_id'].upper())

    target_ids = list(set(target_ids))

    if not target_ids:
        conn.close()
        return

    placeholders = ', '.join(['?'] * len(target_ids))
    sql = f'''
        SELECT title_id, name FROM games
        WHERE title_id IN ({placeholders})
        AND title_id NOT IN (SELECT title_id FROM metadata)
    '''

    targets = conn.execute(sql, target_ids).fetchall()
    conn.close()

    if targets:
        logger.info(f"Scout: Found {
                    len(targets)} active titles missing metadata. Fetching...")
        for title_id, name in targets:
            metadata.get_game_metadata(title_id, name)
            # Small sleep to be polite to IGDB
            import time
            time.sleep(1)
    return


def scout_title(title_id, name):
    cached = database.get_cached_metadata(title_id)
    if cached and "placeholder.png" not in str(cached[1]):
        return cached

    logger.info(f"Scout: Fetching missing metadata for {name} [{title_id}]...")
    return metadata.get_game_metadata(title_id, name)


def run_library_sync():
    import sqlite3
    from backend.downloader import get_safe_name
    from backend.storage import StorageManager

    conn = database.get_db_connection()
    conn.row_factory = sqlite3.Row

    #! ARCHITECTURE: Disk reality enforcement. Cleans up DB orphans if user manually deleted folder from disk
    completed = conn.execute(
        "SELECT title_id, name FROM queue WHERE status = 'completed'").fetchall()
    missing_from_disk = []
    for row in completed:
        tid = row['title_id']
        name = row['name']
        safe_folder = get_safe_name(name, tid)
        expected_path = settings.library_dir / safe_folder

        if not StorageManager.path_exists(expected_path):
            missing_from_disk.append((tid,))
            logger.info(
                f"Scout: {name} missing from disk. Marking for database removal.")

    if missing_from_disk:
        conn.executemany(
            "DELETE FROM queue WHERE title_id = ?", missing_from_disk)
        conn.commit()

    sql = '''
        SELECT g.title_id, g.name FROM games g
        LEFT JOIN metadata m ON g.title_id = m.title_id
        WHERE (g.title_id IN (SELECT title_id FROM queue) OR g.monitored = 1)
        AND (m.cover_url IS NULL or m.cover_url LIKE '%placeholder.png')
        LIMIT 50
    '''

    missing = conn.execute(sql).fetchall()
    conn.close()

    if not missing:
        logger.info(
            "Scout: No active or monitored games require metadata updates.")
        return

    logger.info(f"Scout: Syncing metadata for {
                len(missing)} managed titles...")
    for item in missing:
        scout_title(item['title_id'], item['name'])
        import time
        time.sleep(1)


if __name__ == "__main__":
    run_meta_scout()
