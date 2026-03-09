import secrets
import os
import sqlite3
import pandas as pd
import numpy as np

from backend.logger import logger

# Fallback to local if the ENV isn't set (like during local dev)
DB_PATH = os.getenv("DB_PATH", "/app/data/gamearr.db")

# --- Helper for thread-safe/process-safe connections ---


def get_db_connection():
    # timeout=20 tells the worker to wait if the UI is currently writing
    conn = sqlite3.connect(DB_PATH, timeout=20)
    # Enable WAL mode: allows simultaneous reading and writing
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    # Allows user to look up a game not found the local TSV, just in case
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # TSV Parser Config
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Raw Sony Data
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

        # IGDB Metadata Cache
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                title_id TEXT PRIMARY KEY COLLATE NOCASE,
                summary TEXT,
                cover_url TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (title_id) REFERENCES games (title_id)
            )
        ''')

        # The Queue / Status Table
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

        # add monitored column to games table if it doesn't exist
        try:
            cursor.execute(
                "ALTER TABLE games ADD COLUMN monitored INTEGER DEFAULT 0")
        except:
            pass  # already exists

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Database Init Error: {e}")
        return False


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
    # Pull library grid posters from metadata.
    sql = '''
        SELECT g.platform, g.title_id, g.region, g.name, g.pkg_url, m.cover_url
        FROM games g
        LEFT JOIN metadata m ON g.title_id = m.title_id
        LIMIT ?
    '''
    df = pd.read_sql_query(sql, conn, params=(limit,))
    conn.close()

    # sanitize, see search_game_db below
    df = df.astype(object).replace({np.nan: None})
    return df


def search_game_db(query):
    conn = get_db_connection()
    # split the query into individual words to allow multisearch (e.g. "psx us" -> ["psx", "us"])
    terms = query.split()
    if not terms:
        return []

    sql = '''
        SELECT g.platform, g.title_id, g.region, g.name, g.pkg_url, g.license_key, m.cover_url
        FROM games g
        LEFT JOIN metadata m ON g.title_id = m.title_id
    '''

    # each term must match one of our 4 columns (Name, ID, Region, or Platform)
    where_clauses = []
    params = []

    for term in terms:
        where_clauses.append(
            "(g.name LIKE ? OR g.title_id LIKE ? OR g.region LIKE ? OR g.platform LIKE ?)")
        search_pattern = f"%{term}%"
        # add the pattern 4 times because there are 4 ? placeholders in the clause above
        params.extend([search_pattern, search_pattern,
                      search_pattern, search_pattern])

    # join the clauses with AND (this ensures both "psx" and "us" are present
    full_sql = f"{sql} WHERE {' AND '.join(where_clauses)} LIMIT 100"

    try:
        # Execute with our flattened params list
        df = pd.read_sql_query(full_sql, conn, params=params)
    finally:
        conn.close()

    df = df.astype(object).replace({np.nan: None})
    return df.to_dict(orient='records')


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
    except Exception as e:
        logger.error(f"QUEUE ERROR: Failed to queue {name} - {e}")
        return False
    finally:
        conn.close()


def update_queue_status(title_id, status):
    conn = get_db_connection()
    conn.execute("UPDATE queue SET status = ? WHERE title_id = ?",
                 (status, title_id))
    conn.commit()
    conn.close()


def get_next_queued_task():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row  # Access columns by name
    cursor = conn.cursor()
    # find the oldest pending task
    res = cursor.execute(
        "SELECT * FROM queue WHERE status = 'pending' ORDER BY added_at ASC LIMIT 1").fetchone()
    conn.close()
    return res


def get_or_generate_api_key():
    key = get_config("api_key")
    if not key:
        key = secrets.token_hex(16)
        set_config("api_key", key)
        logger.info(f"--- NOTICE: New API Key generated: {key} ---")
    return key
