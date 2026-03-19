import secrets
import sqlite3
import pandas as pd
import numpy as np
import time
import functools

from collections.abc import Callable
from typing import Any, cast

from backend.logger import logger
from backend.config import settings
from backend.models import MountState


def get_db_connection():
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.db_path), timeout=20)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                title_id TEXT PRIMARY KEY COLLATE NOCASE,
                platform TEXT,
                region TEXT,
                name TEXT,
                pkg_url TEXT,
                license_key TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                title_id TEXT PRIMARY KEY COLLATE NOCASE,
                summary TEXT,
                cover_url TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (title_id) REFERENCES games (title_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS queue (
                title_id TEXT PRIMARY KEY COLLATE NOCASE,
                platform TEXT,
                region TEXT,
                name TEXT,
                status TEXT,
                pkg_url TEXT,
                license_key TEXT,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                progress REAL DEFAULT 0.0,
                size_total INTEGER DEFAULT 0,
                size_current INTEGER DEFAULT 0,
                error_msg TEXT
            )
        ''')

        try:
            cursor.execute(
                "ALTER TABLE games ADD COLUMN monitored INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            #! DEBT SQLite lacks an 'ADD COLUMN IF NOT EXISTS' syntax.
            # trapping the OperationalError safely bypasses this duplicate column constraint on hosts
            # without masking deeper I/O locking failures
            pass

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"STORAGE FATAL: Database Initialization dropped: {e}")
        return False


def db_retry[F: Callable[..., Any]](_func: F | None = None, *, retries: int = 5, backoff: float = 0.2) -> F | Callable[[F], F]:
    '''
    ARCHTITECTURE: Decorative handler for SQLITE_BUSY errors.
    exponential backoff for lock-relase wait.
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_err: sqlite3.OperationalError | None = None

            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" not in str(e).lower():
                        raise

                    last_err = e
                    if i == retries - 1:
                        logger.error(f"DATABASE FATAL: {
                                     func.__name__} exhausted {retries} retries.")
                        raise

                    sleep_time = backoff * (2 ** i)
                    logger.warning(f"DATABASE BUSY: Retrying {func.__name__} ({
                                   i+1}/{retries}) in {sleep_time: .2f}s...")
                    time.sleep(sleep_time)

            if last_err:
                raise last_err
            raise sqlite3.OperationalError(f"Database retry loop for {
                                           func.__name__} failed.")

        return cast(F, wrapper)

    if _func is None:
        return decorator
    return decorator(_func)


def get_config(key):
    conn = get_db_connection()
    res = conn.execute(
        "SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return res[0] if res else None


def set_config(key, value):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def save_game(platform, title_id, region, name, pkg_url, license_key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO games (platform, title_id, region, name, pkg_url, license_key)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (platform, title_id, region, name, pkg_url, license_key))
    conn.commit()
    conn.close()


def save_metadata(title_id, summary, cover_url):
    conn = get_db_connection()
    cursor = conn.cursor()
    clean_id = title_id.strip().upper()
    cursor.execute('''
        INSERT OR REPLACE INTO metadata (title_id, summary, cover_url)
        VALUES (?, ?, ?)
    ''', (clean_id, summary, cover_url))
    conn.commit()
    conn.close()
    logger.info(f"Metadata cached for {title_id}")


def get_cached_metadata(title_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    clean_id = title_id.strip().upper()
    cursor.execute(
        'SELECT summary, cover_url FROM metadata WHERE title_id = ?', (clean_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_all_games(limit=50):
    conn = get_db_connection()
    sql = '''
        SELECT g.platform, g.title_id, g.region, g.name, g.pkg_url, m.cover_url
        FROM games g
        LEFT JOIN metadata m ON g.title_id = m.title_id
        LIMIT ?
    '''
    df = pd.read_sql_query(sql, conn, params=(limit,))
    conn.close()

    df = df.astype(object).replace({np.nan: None})
    return df


"""
ARCHTITECTURE: get_unmapped_folders transfered to scout.run_library_import
as it was more fitting there. The logic changed slightly to allow Gamearr
to syncronize the pre-existing folers to the DB. It also cross-references the
NPS manifest, and moves it to 'completed.' This allows for indexing without redownloading
if unneeded.
"""


@db_retry()
def get_unmapped_games(title_id: str, name: str, platform: str, region: str):
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT OR IGNORE INTO queue (
                title_id, platform, region, name, status, pkg_url, license_key, progress, added_at
            ) VALUES (?, ?, ?, ?, 'completed', 'COLD_IMPORT', 'COLD_IMPORT', 100.0, CURRENT_TIMESTAMP)
        ''', (title_id.upper(), platform, region, name))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"DATABASE ERROR: Failed to adopt {title_id}: {e}")
        return False
    finally:
        conn.close()


def search_game_db(query):
    conn = get_db_connection()
    terms = query.split()
    if not terms:
        return []

    sql = '''
        SELECT g.platform, g.title_id, g.region, g.name, g.pkg_url, g.license_key, m.cover_url
        FROM games g
        LEFT JOIN metadata m ON g.title_id = m.title_id
    '''

    where_clauses = []
    params = []

    for term in terms:
        where_clauses.append(
            "(g.name LIKE ? OR g.title_id LIKE ? OR g.region LIKE ? OR g.platform LIKE ?)")
        search_pattern = f"%{term}%"
        params.extend([search_pattern, search_pattern,
                      search_pattern, search_pattern])

    full_sql = f"{sql} WHERE {' AND '.join(where_clauses)} LIMIT 100"

    try:
        df = pd.read_sql_query(full_sql, conn, params=params)
    finally:
        conn.close()

    df = df.astype(object).replace({np.nan: None})
    return df.to_dict(orient='records')


@db_retry()
def add_to_queue(platform, title_id, region, name, pkg_url, license_key):
    conn = get_db_connection()
    clean_id = title_id.strip().upper()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO queue (
                platform, title_id, region, name, status, pkg_url, license_key,
                progress, size_total, size_current
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0, 0)
        ''', (platform, clean_id, region, name, 'pending', pkg_url, license_key))
        conn.commit()
        logger.info(f"QUEUE: {name} [{title_id}] added to queue.")
        return True
    except sqlite3.Error as e:
        logger.error(f"QUEUE ERROR: Failed to queue {name} - {e}")
        return False
    finally:
        conn.close()


@db_retry()
def update_queue_status(title_id, status):
    '''
    ARCHTITECTURE: IMMEDIATE to lock the DB when write starts
    '''
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE queue SET status = ? WHERE title_id = ?",
                     (status, title_id))
        conn.commit()
    finally:
        conn.close()


def get_next_queued_task():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    res = cursor.execute(
        "SELECT * FROM queue WHERE status = 'pending' ORDER BY added_at ASC LIMIT 1").fetchone()
    conn.close()
    return res


def revert_stuck_queue():
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE queue
            SET status = 'pending'
            WHERE status IN ('downloading', 'extracting', 'importing', 'verifying', 'stalled')
        ''')
        conn.commit()
        logger.info("Database: Reverted stale queue items to 'pending'.")
    except sqlite3.Error as e:
        logger.error(f"STORAGE ERROR: Failed to recover queue state - {e}")
    finally:
        conn.close()


def update_queue_error(title_id: str, error_msg: str):
    conn = get_db_connection()
    conn.execute("UPDATE queue SET error_msg = ? WHERE title_id = ?",
                 (error_msg, title_id))
    conn.commit()
    conn.close()


@db_retry
def update_progress(title_id: str, progress: float, size_current: int, size_total: int) -> None:
    '''
    ARCHTITECTURE: Optimized progress updater for the UI
    '''
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute('''
            UPDATE queue
            SET progress = ?, size_current = ?, size_total = ?
            WHERE title_id = ?
        ''', (progress, size_current, size_total, title_id))
        conn.commit()
    finally:
        conn.close()


def get_or_generate_api_key():
    key = get_config("api_key")
    if not key:
        key = secrets.token_hex(16)
        set_config("api_key", key)
        logger.info(f"--- NOTICE: New API Key generated: {key} ---")
    return key
