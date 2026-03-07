# COPYRIGHT (C) 2026 nottyxton and The Gamearr Authors

import os
import re
from fastapi import FastAPI, HTTPException, Query, Body, BackgroundTasks, Depends, APIRouter
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
import pandas as pd

from contextlib import asynccontextmanager
import asyncio
from backend import config_validator

from pydantic import BaseModel
from typing import List, Optional
import shutil

from pydantic_core.core_schema import PlainValidatorFunctionSchema

from backend import parser, database, metadata, scout
from backend.downloader import get_safe_name
from backend.models import GameModel, QueuePayload, QueueItem
from backend.worker import INCOMPLETE_DIR
from backend.auth import validate_api_key
from backend.logger import logger, LOG_FILE

# Standardized Path
LIBRARY_DIR = os.getenv("LIBRARY_DIR", "/library")

# --- INITIALIZATION ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    '''Initialize system on container boot.'''
    logger.info("--- Gamearr Startup ---")
    if not database.init_db():
        logger.error("CRITICAL: Database initialization failed.")
        return

    # check directories
    for path in [LIBRARY_DIR, INCOMPLETE_DIR]:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            logger.info(f"Created directory: {path}")

    # supervised startup leaving FastAPI to monitor
    logger.info("Starting Background Worker and Metadata Scout...")
    database.get_or_generate_api_key()

    worker_task = asyncio.create_task(run_async_worker())
    scout_task = asyncio.create_task(run_async_scout())

    # Sync the NPS database in a seperate thread so it doesn't block boot
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, parser.sync_database)

    yield   # app is now running

    # shutdown logic
    logger.info("Shutting down background tasks...")
    worker_task.cancel()
    scout_task.cancel()

# --- Async Wrappers for Worker/Scout ---


async def run_async_worker():
    from backend.worker import start_worker
    # run the blocking worker loop in a thread to keep the event loop free
    while True:
        await asyncio.to_thread(start_worker)
        await asyncio.sleep(10)  # Safety restart delay


async def run_async_scout():
    from backend.scout import run_meta_scout
    while True:
        await asyncio.to_thread(run_meta_scout)
        await asyncio.sleep(300)  # Only scout every 5 mins

app = FastAPI(title="Gamearr API", version="0.4.36", lifespan=lifespan)
api_router = APIRouter(prefix="/api", dependencies=[Depends(validate_api_key)])

# --- API ENDPOINTS ---


@app.get("/api/config/keys")
def get_keys_bootstrap():
    ''' Later, this will be protected by session/login.
        For now, this allows the UI to initialize itself. '''
    return {"api_key": database.get_config("api_key")}


@api_router.get("/system/logs")
async def get_logs(lines: int = 100):
    ''' returns the last N lines of the log file. '''
    if not os.path.exists(LOG_FILE):
        return {"logs": "Log file not found."}

    try:
        with open(LOG_FILE, "r") as f:
            content = f.readlines()
            last_lines = content[-lines:]
            return {"logs": "".join(last_lines)}
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        raise HTTPException(status_code=500, detail="Could not read log file.")


@api_router.get("/library")
def get_library():
    '''Fetch the full list of known games for the Grid View.'''
    conn = database.get_db_connection()

    # explicityly select colums to avoid naming collisions
    sql = '''
        SELECT
            g.title_id, g.platform, g.region, g.name, g.pkg_url, g.license_key,
            m.cover_url,
            q.status
        FROM games g
        JOIN queue q ON UPPER(TRIM(g.title_id)) = UPPER(TRIM(q.title_id))
        LEFT JOIN metadata m ON UPPER(TRIM(g.title_id)) = UPPER(TRIM(m.title_id))
        WHERE q.status = 'completed'
        ORDER BY g.name ASC
    '''

    df = pd.read_sql_query(sql, conn)
    conn.close()

    # JSON Safety
    df = df.replace({np.nan: None})
    records = df.to_dict(orient='records')

    library_results = []
    for row in records:
        db_cover = row.get('cover_url')
        if db_cover and "placeholder.png" in db_cover:
            db_cover = None

        game = GameModel(
            title_id=row['title_id'],
            platform=row['platform'],
            region=row['region'],
            name=row['name'],
            pkg_url=row['pkg_url'],
            license_key=row['license_key'] or "MISSING",
            cover_url=row['cover_url'] if row['cover_url'] else "/assets/placeholder.png",
            status="completed"
        )
        library_results.append(game)

    return {'results': library_results}


@api_router.get("/search")
async def search_games(q: str):
    '''Search games in local SQLite Cache first.'''
    results = database.search_game_db(q)

    if not results:
        return {"result": []}

    # we enrich only the top 10 results to keep the search fast
    # the rest will still use placeholders until the background scout hits them
    top_results = results[:10]

    tasks = []
    for game in top_results:
        # If it's a placeholder or missing, fetch now
        if not game.get('cover_url') or "placeholder.png" in game.get('cover_url'):
            tasks.append(asyncio.to_thread(
                metadata.get_game_metadata, game['title_id'], game['name']))
        else:
            # already has metadata, just wrap it in a dummy task
            tasks.append(asyncio.sleep(0))

    # wait for all metadata fetches to finish
    enriched_data = await asyncio.gather(*tasks)

    # merge the enriched metadata back into our results
    for i, data in enumerate(enriched_data):
        if data and isinstance(data, dict):
            results[i]['cover_url'] = data.get('cover_url')
            results[i]['summary'] = data.get('summary')

    return {"results": results}


@api_router.get("/details/{title_id}")
def get_game_details(title_id: str, name: str):
    '''Fetch full metadata and system status for the Detail Modal'''
    tid = title_id.strip().upper()

    # This will now return the fresh IGDB data
    meta = metadata.get_game_metadata(tid, name)

    conn = database.get_db_connection()
    conn.row_factory = database.sqlite3.Row

    # Check if we already have this game monitored or in queue
    game_info = conn.execute(
        "SELECT monitored FROM games WHERE title_id = ?", (tid,)).fetchone()
    queued_item = conn.execute(
        "SELECT status FROM queue WHERE title_id = ?", (tid,)).fetchone()
    conn.close()

    status = "available"
    if queued_item:
        status = queued_item['status']

    return {
        "metadata": meta,
        "status": status,
        "title_id": tid,
        "monitored": bool(game_info['monitored']) if game_info else False
    }


@api_router.post("/queue")
async def queue_endpoint(game: QueuePayload):
    # Pydantic Automaticcaly validates incoming JSON against QueuePayload
    success = database.add_to_queue(
        game.platform,
        game.title_id,
        game.region,
        game.name,
        game.pkg_url,
        game.license_key
    )
    return {"message": "Success"} if success else {"error": "Failed"}


@api_router.get("/queue")
def view_queue(view: str = "active"):
    '''Return filtered queue items, "active" "history" "blocklist" '''
    conn = database.get_db_connection()
    conn.row_factory = database.sqlite3.Row

    if view == "active":
        # show everything current in the pipeline
        query = "SELECT * FROM queue WHERE status NOT IN ('completed', 'failed') ORDER BY added_at DESC"
    elif view == "history":
        # show successful imports, limit to 50 so it doesn't lag
        query = "SELECT * FROM queue WHERE status = 'completed' ORDER BY added_at DESC LIMIT 50"
    elif view == "blocklist":
        # show failed attempts
        query = "SELECT * FROM queue WHERE status = 'failed' ORDER BY added_at DESC"
    else:
        query = "SELECT * FROM queue ORDER BY added_at DESC"

    queue = conn.execute(query).fetchall()
    conn.close()
    return {"queue": [dict(row) for row in queue], "current-view": view}


@api_router.delete("/queue/{title_id}")
def delete_queue_item(title_id: str):
    ''' Allow users to remove items from History or Blocklist '''
    conn = database.get_db_connection()
    conn.execute("DELETE FROM queue WHERE title_id = ?", (title_id,))
    conn.commit()
    conn.close()
    return {"message": "Deleted"}


@api_router.get("/queue/count")
def get_queue_count():
    conn = database.get_db_connection()
    # exclude completed and failed
    count = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE status NOT IN ('completed', 'failed')").fetchone()[0]
    conn.close()
    return {"count": count}


@api_router.get("/wanted")
def get_wanted_games():
    ''' Returns games that are monitored but not yet completed/installed. '''
    conn = database.get_db_connection()
    conn.row_factory = database.sqlite3.Row

    # Monitored = 1 AND (Not in library AND not in queue as completed)
    sql = '''
        SELECT g.*, m.cover_url
        FROM games g
        LEFT JOIN metadata m ON g.title_id = m.title_id
        WHERE g.monitored = 1
        AND g.title_id NOT IN (SELECT title_id FROM queue WHERE status = 'completed')
        ORDER BY g.name ASC
    '''
    results = conn.execute(sql).fetchall()
    conn.close()
    return {"results": [dict(row) for row in results]}


@api_router.post("/games/monitor")
def toggle_monitor(payload: dict = Body(...)):
    ''' Toggles the monitored status for a game '''
    title_id = payload.get("title_id")
    monitored = payload.get("monitored", 0)

    conn = database.get_db_connection()
    conn.execute("UPDATE games SET monitored = ? WHERE title_id = ?",
                 (monitored, title_id))
    conn.commit()
    conn.close()
    return {"message": "Updated", "monitored": monitored}


class BulkActionPayload(BaseModel):
    title_ids: List[str]
    action: str  # "monitor", "unmonitor", "delete", "refresh"


@api_router.post("/games/bulk")
async def bulk_games_action(payload: BulkActionPayload, background_tasks: BackgroundTasks):
    conn = database.get_db_connection()
    ids = [tid.strip().upper() for tid in payload.title_ids]

    try:
        if payload.action == "monitor":
            conn.executemany("UPDATE games SET monitored = 1 WHERE title_id = ?", [
                             (i,) for i in ids])
        elif payload.action == "unmonitor":
            conn.executemany("UPDATE games SET monitored = 0 WHERE title_id = ?", [
                             (i,) for i in ids])
        elif payload.action == "delete":
            # 1. Remove from Queue/Library DB
            conn.executemany("DELETE FROM queue WHERE title_id = ?", [
                             (i,) for i in ids])
            # 2. Logic for physical deletion would go here in v0.5
            logger.info(f"Bulk Delete triggered for {len(ids)} items.")
        elif payload.action == "refresh":
            for tid in ids:
                # We fetch the name from DB first to refresh metadata
                game = conn.execute(
                    "SELECT name FROM games WHERE title_id = ?", (tid,)).fetchone()
                if game:
                    background_tasks.add_task(scout.scout_title, tid, game[0])

        conn.commit()
        return {"message": f"Successfully processed {payload.action} for {len(ids)} games."}
    finally:
        conn.close()


@api_router.post("/system/update-all")
def trigger_update_all(background_tasks: BackgroundTasks):
    ''' Triggers a full library metadata sync and NPS database refresh '''
    from backend import scout, parser
    background_tasks.add_task(scout.run_library_sync)
    background_tasks.add_task(parser.sync_database)
    return {"message": "System update tasks started in background."}


@api_router.get("/system/health")
def get_system_health():
    ''' Returns disk usage and library stats'''
    total, used, free = shutil.disk_usage(LIBRARY_DIR)
    # get total games count
    conn = database.get_db_connection()
    conn.close()

    return {
        "disk": {
            "total_gb": total // (2**30),
            "free_gb": free // (2**30),
            "used_gb": used // (2**30),
            "percent": round((used / total) * 100, 1)
        },
    }


@api_router.get("/system/status")
def get_system_status():
    from backend.parser import MANIFESTS
    sources_configured = any(v for v in MANIFESTS.values())

    return {
        "status": "online",
        "sources_configured": sources_configured,
        "warning": None if sources_configured else "No game sources configured. Please check your .env file."
    }


# --- ROUTER MOUNT ---
app.include_router(api_router)

# --- FRONTEND MOUNT ---
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
