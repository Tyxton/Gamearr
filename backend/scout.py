import os
import time
import sqlite3
from backend import database, metadata
from backend.downloader import get_safe_name

LIBRARY_DIR = os.getenv("LIBRARY_DIR", "/library")

def run_meta_scout():
    print("Scouting local library archives for metadata...")
    
    # Fetch all games that are missing metadata
    conn = database.get_db_connection()
    # find only results in games
    query = """
        SELECT title_id, name FROM games 
        WHERE title_id NOT IN (SELECT title_id FROM metadata)
    """
    targets = conn.execute(query).fetchall()
    conn.close()

    if not targets:
        print("Archives are fully indexed. No new fetch required.")
        return

    found_count = 0
    for title_id, name in targets:
        # check if the folder exists in library
        safe_name = get_safe_name(name, title_id)
        folder_path = os.path.join(LIBRARY_DIR, safe_name)

        if os.path.exists(folder_path):
            print(f"Local asset detected: {name} [{title_id}]. Requesting posters...")
            
            # Trigger the IGDB fetch and auto-save to the DB
            metadata.get_game_metadata(title_id, name)
            found_count += 1
            
            # Throttle: Avoid alerting IGDB rate limits (approx 4 requests/sec max)
            time.sleep(0.25)

    print(f"Cached intel for {found_count} local titles.")

if __name__ == "__main__":
    run_intel_scout()
