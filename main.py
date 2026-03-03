import os
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import shutil

from backend import parser, database, metadata, scout
from backend.downloader import get_safe_name

# Standardized Path
LIBRARY_DIR = os.getenv("LIBRARY_DIR", "/library")

app = FastAPI(title="Gamearr API", version="0.4.3")

# --- INITIALIZATION ---
@app.on_event("startup")
def startup_event():
    '''Initialize system on container boot.'''
    print("Syncing Database...")
    database.init_db()
    parser.sync_database()

    import threading
    threading.Thread(target=scout.run_meta_scout, daemon=True).start()

# --- API ENDPOINTS ---

@app.get("/api/library")
def get_library():
    '''Fetch the full list of known games for the Grid View.'''
    results = database.get_all_games()
    return {"results": results.to_dict(orient="records")}

@app.get("/api/search")
def search_games(q: str = Query(..., min_length=2)):
    '''Search games in local SQLite Cache first.'''
    results = database.search_game_db(q)
    if results.empty:
        return {"results": []}
    return {"results": results.to_dict(orient="records")}

@app.get("/api/details/{title_id}")
def get_game_details(title_id: str, name: str):
    '''Fetch metadata and check system status (Library/Queue).'''
    meta = metadata.get_game_metadata(title_id, name)

    safe_folder = get_safe_name(name, title_id)
    final_path = os.path.join(LIBRARY_DIR, safe_folder)

    conn = database.get_db_connection()
    queued_item = conn.execute(
            "SELECT status FROM queue WHERE title_id = ?", (title_id,)).fetchone()
    conn.close()

    status = "available"
    if os.path.exists(final_path):
        status = "installed"
    elif queued_item:
        status = queued_item['status']

    return {
            "metadata": meta,
            "status": status,
            "title_id": title_id
    }

class GamePayload(BaseModel):
    platform: str
    title_id: str
    region: str
    name: str
    pkg_url: str
    license_key: str | None = None

@app.post("/api/queue")
async def queue_endpoint(game: GamePayload):
    success = database.add_to_queue(
            game.platform,
            game.title_id,
            game.region,
            game.name,
            game.pkg_url,
            game.license_key
    )
    return {"message": "Success"} if success else {"error": "Failed"}

@app.get("/api/queue")
def view_queue():
    '''Return the current status of all downloads for the Dashboard.'''
    conn = database.get_db_connection()
    queue = conn.execute("SELECT * FROM queue ORDER BY title_id DESC").fetchall()
    conn.close()
    return {"queue": [dict(row) for row in queue]}

app.get("/api/system/health")
def get_system_health():
    ''' Returns disk usage and library stats'''
    total, used, free = shutil.disk_usage(LIBRARY_DIR)
    # get total games count
    conn = database.get_db_connection()
    game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    conn.close()

    return {
        "disk": {
            "total": total,
            "free": free,
            "used": used,
            "percent": round((used / total) * 100, 1)
        },
        "stats": {
            "games": game_count
        }
    }

# --- FRONTEND MOUNT ---
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
