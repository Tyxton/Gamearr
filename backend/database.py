import os
import sqlite3
import pandas as pd
import numpy as np

# Fallback to local if the ENV isn't set (like during local dev)
DB_PATH = os.getenv("DB_PATH", "/app/data/gamearr.db")

# --- Helper for thread-safe/process-safe connections ---
def get_db_connection():
    # timeout=20 tells the worker to wait if the UI is currently writing
    conn = sqlite3.connect(DB_PATH, timeout=20)
    # Enable WAL mode: allows simultaneous reading and writing
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
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
            title_id TEXT PRIMARY KEY,
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
            title_id TEXT PRIMARY KEY,
            summary TEXT,
            cover_url TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (title_id) REFERENCES games (title_id)
        )
    ''')

    # The Queue / Status Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue (
            title_id TEXT PRIMARY KEY,
            platform TEXT,
            region TEXT,
            name TEXT,
            status TEXT,        -- 'pending', 'downloading', 'completed', 'failed'
            pkg_url TEXT,
            license_key TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def get_config(key):
    conn = get_db_connection()
    res = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return res[0] if res else None

def set_config(key, value):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
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
    cursor.execute('''
        INSERT OR REPLACE INTO metadata (title_id, summary, cover_url)
        VALUES (?, ?, ?)
    ''', (title_id, summary, cover_url))
    conn.commit()
    conn.close()
    print(f"Metadata cached for {title_id}")

def get_cached_metadata(title_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT summary, cover_url FROM metadata WHERE title_id = ?', (title_id,))
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
    sql = '''
        SELECT g.platform, g.title_id, g.region, g.name, g.pkg_url, g.license_key, m.cover_url
        FROM games g
        LEFT JOIN metadata m ON g.title_id = m.title_id
        WHERE g.name LIKE ?
    '''
    df = pd.read_sql_query(sql, conn, params=(f'%{query}%',))
    conn.close()
    
    # force datafram to object to prevent pandas from reverting none to NaN 
    # then replace all numpy NaN values with Python None
    df = df.astype(object).replace({np.nan: None})

    return df.to_dict(orient='records') # Should now be a safe list of dicts

def add_to_queue(platform, title_id, region, name, pkg_url, license_key):
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO queue (
                platform, title_id, region, name, status, pkg_url, license_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (platform, title_id, region, name, 'pending', pkg_url, license_key))
        conn.commit()
        print(f"{name} [{title_id}] added to queue.")
        return True
    except Exception as e:
        print(f"Failure: Failed to queue {name} - {e}")
        return False
    finally:
        conn.close()

def update_queue_status(title_id, status):
    conn = get_db_connection()
    conn.execute("UPDATE queue SET status = ? WHERE title_id = ?", (status, title_id))
    conn.commit()
    conn.close()

def get_next_queued_task():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row # Access columns by name
    cursor = conn.cursor()
    # find the oldest pending task
    res = cursor.execute("SELECT * FROM queue WHERE status = 'pending' ORDER BY added_at ASC LIMIT 1").fetchone()
    conn.close()
    return res
