import os
import re

from backend import database, metadata
from backend.models import GameStatus
from backend.logger import logger

LIBRARY_DIR = os.getenv("LIBRARY_DIR", "/library")


def run_meta_scout(single_id=None):
    conn = database.get_db_connection()
    target_ids = []

    # If we are scouting a specific ID (i.e. just finished download)
    if single_id:
        target_ids.append(single_id.upper())
    else:
        # Scan the physical library for Title IDs
        if os.path.exists(LIBRARY_DIR):
            folders = [f for f in os.listdir(LIBRARY_DIR) if os.path.isdir(
                os.path.join(LIBRARY_DIR, f))]
            for folder in folders:
                match = re.search(r'\[(.*?)\]', folder)
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
        # Scan the queue to grab metadata as they download
        queued_items = conn.execute(
            sql, [s.value for s in active_statuses]).fetchall()
        for item in queued_items:
            target_ids.append(item['title_id'].upper())

    # remove duplicates
    target_ids = list(set(target_ids))

    if not target_ids:
        conn.close()
        return

    # only fetch metadata for these IDs if it doesn't exist yet
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
    ''' Scout for a single title '''
    # check if it exists already
    cached = database.get_cached_metadata(title_id)
    if cached and "placeholder.png" not in str(cached[1]):
        return cached

    logger.info(f"Scout: Fetching missing metadata for {name} [{title_id}]...")
    return metadata.get_game_metadata(title_id, name)


def run_library_sync():
    ''' Full sync that only runs on startup or manual trigger '''
    import sqlite3
    conn = database.get_db_connection()
    conn.row_factory = sqlite3.Row

    # We only want games that are in the Queue (Active/Completed) OR Monitored
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
        time.sleep(1)  # Polite delay for IGDB


if __name__ == "__main__":
    run_meta_scout()
