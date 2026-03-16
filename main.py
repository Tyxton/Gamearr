# COPYRIGHT (C) 2026 nottyxton and The Gamearr Authors

import asyncio
import platform
import pandas as pd
import numpy as np
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, Depends, APIRouter, status
from fastapi.staticfiles import StaticFiles

from backend import parser, database, metadata, scout
from backend.exceptions import StorageError
from backend.models import GameModel, MountState, QueuePayload, BulkActionPayload
from backend.auth import validate_api_key
from backend.logger import logger, LOG_FILE
from backend.config import settings
from backend.storage import mount_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- Gamearr Startup ---")

    missing_bins = settings.validate_dependencies()
    if missing_bins:
        logger.critical(f"SYSTEM FATAL: Missing core dependencies for Gamearr: {
                        ', '.join(missing_bins)}"
                        "Aborting...")
        return

    initialized = await asyncio.to_thread(database.init_db)
    if not initialized:
        logger.error("CRITICAL: Database initialization failed.")
        return

    await asyncio.to_thread(database.revert_stuck_queue)

    def _provision_directories():
        mount_manager.ensure_dir(settings.library_dir)
        mount_manager.ensure_dir(settings.incomplete_dir)

    await asyncio.to_thread(_provision_directories)
    await asyncio.to_thread(database.get_or_generate_api_key)

    async def _delayed_start():
        await asyncio.to_thread(parser.sync_database)
        await asyncio.to_thread(scout.run_library_sync)

        logger.info("Background services initializing...")
        global worker_task, scout_task, heartbeat_task
        heartbeat_task = asyncio.create_task(run_async_heartbeat())
        worker_task = asyncio.create_task(run_async_worker())
        scout_task = asyncio.create_task(run_async_scout())

    asyncio.create_task(_delayed_start())

    yield


async def run_async_heartbeat():
    '''
    ARCHITECTURE: Background monitor polls the mount state every 60s
    '''
    while True:
        await asyncio.to_thread(mount_manager.heartbeat_mon)
        await asyncio.sleep(60)


async def run_async_worker():
    from backend.worker import start_worker
    while True:
        await asyncio.to_thread(start_worker)
        await asyncio.sleep(10)


async def run_async_scout():
    from backend.scout import run_library_sync
    while True:
        await asyncio.to_thread(run_library_sync)
        await asyncio.sleep(300)

app = FastAPI(title="Gamearr API", version="0.4.38", lifespan=lifespan)
api_router = APIRouter(prefix="/api", dependencies=[Depends(validate_api_key)])


@app.get("/api/config/keys")
async def get_keys_bootstrap():
    ''' Later, this will be protected by session/login.
        For now, this allows the UI to initialize itself. '''
    def _get_key():
        return {"api_key": database.get_config("api_key")}
    return await asyncio.to_thread(_get_key)


@api_router.get("/system/logs")
async def get_logs(lines: int = 100):
    def _read_logs():
        if not LOG_FILE.exists():
            return {"logs": "Log file not found."}
        try:
            with LOG_FILE.open("r") as f:
                content = f.readlines()
                return {"logs": "".join(content[-lines:])}
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to read logs: {e}")
            raise HTTPException(
                status_code=500, detail="Could not read log file.")
    return await asyncio.to_thread(_read_logs)


@api_router.get("/library")
async def get_library():
    def _fetch():
        conn = database.get_db_connection()
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

        df = df.astype(object).replace({np.nan: None})
        records = df.to_dict(orient='records')

        library_results = []
        for row in records:
            db_cover = row.get('cover_url')
            if db_cover and "placeholder.png" in db_cover:
                db_cover = None

            library_results.append(GameModel(
                title_id=row['title_id'],
                platform=row['platform'],
                region=row['region'],
                name=row['name'],
                pkg_url=row['pkg_url'],
                license_key=row['license_key'] or "MISSING",
                cover_url=row['cover_url'] if row['cover_url'] else "/assets/placeholder.png",
                status="completed"
            ))
        return {"results": library_results}

    return await asyncio.to_thread(_fetch)


@api_router.get("/search")
async def search_games(q: str):
    def _search():
        return database.search_game_db(q)

    results = await asyncio.to_thread(_search)

    if not results:
        return {"result": []}

    top_results = results[:10]
    tasks = []
    for game in top_results:
        if not game.get('cover_url') or "placeholder.png" in game.get('cover_url'):
            def _fetch_meta(tid=game['title_id'], gname=game['name']):
                return metadata.get_game_metadata(tid, gname)
            tasks.append(asyncio.to_thread(_fetch_meta))
        else:
            tasks.append(asyncio.sleep(0))

    enriched_data = await asyncio.gather(*tasks)

    for i, data in enumerate(enriched_data):
        if data and isinstance(data, dict):
            results[i]['cover_url'] = data.get('cover_url')
            results[i]['summary'] = data.get('summary')

    return {"results": results}


@api_router.get("/details/{title_id}")
async def get_game_details(title_id: str, name: str):
    def _details():
        tid = title_id.strip().upper()

        # This will now return the fresh IGDB data
        meta = metadata.get_game_metadata(tid, name)

        conn = database.get_db_connection()
        conn.row_factory = database.sqlite3.Row

        game_info = conn.execute(
            "SELECT monitored FROM games WHERE title_id = ?", (tid,)).fetchone()
        queued_item = conn.execute(
            "SELECT status FROM queue WHERE title_id = ?", (tid,)).fetchone()
        conn.close()

        status = queued_item['status'] if queued_item else "available"

        return {
            "metadata": meta,
            "status": status,
            "title_id": tid,
            "monitored": bool(game_info['monitored']) if game_info else False
        }
    return await asyncio.to_thread(_details)


@api_router.post("/queue")
async def queue_endpoint(game: QueuePayload):
    '''
    ARCHITECTURE: Pre-flight test must succeed to add games to queue
    503 Service Unavailable = Mount point is mising or offline
    403 Forbidden = Mount point is degraded/RO
    '''
    def _preflight_add():
        try:
            library_state = mount_manager.get_state(settings.library_dir)
            incomplete_state = mount_manager.get_state(settings.incomplete_dir)

            if MountState.DEGRADED in (library_state, incomplete_state):
                raise StorageError(
                    "Storage is in DEGRADED state.", is_permission_error=True)

            if MountState.OFFLINE in (library_state, incomplete_state):
                raise StorageError("Storage is OFFLINE.")

            mount_manager.preflight_test()

            return database.add_to_queue(
                game.platform,
                game.title_id,
                game.region,
                game.name,
                game.pkg_url,
                game.license_key
            )
        except StorageError as se:
            if se.is_permission_error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Failed to add to queue, permission error in destination: {
                        str(se)}"
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to add to queue, destination is OFFLINE: {
                    str(se)}"
            )

    success = await asyncio.to_thread(_preflight_add)
    return {"message": "Success"} if success else {"error": "Failed to add to queue"}


@api_router.get("/queue")
async def view_queue(view: str = "active"):
    def _queue():
        conn = database.get_db_connection()
        conn.row_factory = database.sqlite3.Row

        if view == "active":
            query = "SELECT * FROM queue WHERE status NOT IN ('completed', 'failed') ORDER BY added_at DESC"
        elif view == "history":
            query = "SELECT * FROM queue WHERE status = 'completed' ORDER BY added_at DESC LIMIT 50"
        elif view == "blocklist":
            query = "SELECT * FROM queue WHERE status = 'failed' ORDER BY added_at DESC"
        else:
            query = "SELECT * FROM queue ORDER BY added_at DESC"

        queue = conn.execute(query).fetchall()
        conn.close()
        return {"queue": [dict(row) for row in queue], "current-view": view}
    return await asyncio.to_thread(_queue)


@api_router.delete("/queue/{title_id}")
async def delete_queue_item(title_id: str):
    def _delete():
        conn = database.get_db_connection()
        conn.execute("DELETE FROM queue WHERE title_id = ?", (title_id,))
        conn.commit()
        conn.close()

    await asyncio.to_thread(_delete)
    return {"message": "Deleted"}


@api_router.get("/queue/count")
async def get_queue_count():
    def _count():
        conn = database.get_db_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE status NOT IN ('completed', 'failed')").fetchone()[0]
        conn.close()
        return count
    return {"count": await asyncio.to_thread(_count)}


@api_router.get("/wanted")
async def get_wanted_games():
    def _wanted():
        conn = database.get_db_connection()
        conn.row_factory = database.sqlite3.Row

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
    return await asyncio.to_thread(_wanted)


@api_router.post("/games/monitor")
async def toggle_monitor(payload: dict = Body(...)):
    def _toggle():
        title_id = payload.get("title_id")
        monitored = payload.get("monitored", 0)

        conn = database.get_db_connection()
        conn.execute("UPDATE games SET monitored = ? WHERE title_id = ?",
                     (monitored, title_id))
        conn.commit()
        conn.close()
        return monitored

    monitored = await asyncio.to_thread(_toggle)
    return {"message": "Updated", "monitored": monitored}


@api_router.get("/library/unmapped")
async def get_unmapped():
    return await asyncio.to_thread(database.get_unmapped_folders)


@api_router.post("/library/import")
async def import_unmapped(payload: dict = Body(...)):
    '''
    ARCHITECTURE: Moves an unmapped folder into the 'completed' state and triggers
    identity mapping and matadata scouting for that title
    '''
    title_id = payload.get("title_id").upper()

    def _adopt():
        conn = database.get_db_connection()
        game = conn.execute(
            "SELECT * FROM games WHERE title_id = ?", (title_id,)).fetchone()
        if not game:
            raise HTTPException(
                status_code=404, detail="Title ID not found in NPS manifest.")

        conn.execute('''
            INSERT OR REPLACE INTO queue (
            title_id, platform, region, name, status, pkg_url, license_key, added_at, progress
            ) VALUES (?, ?, ?, ?, 'completed', ?, ?, CURRENT_TIMESTAMP, 100.0)
        ''', (game['title_id'], game['platform'], game['region'], game['name'], game['pkg_url'], game['license_key']))
        conn.commit()
        conn.close()

        from backend.downloader import get_safe_name
        safe_folder = get_safe_name(game['name'], game['title_id'])
        mount_manager._apply_identity_mapping(
            settings.library_dir / safe_folder)

        scout.scout_title(game['title_id'], game['name'])

        return {"message": f"Successfully adopted {game['name']}"}
    return await asyncio.to_thread(_adopt)


@api_router.post("/games/bulk")
async def bulk_games_action(payload: BulkActionPayload, background_tasks: BackgroundTasks):
    def _bulk():
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
                conn.executemany("DELETE FROM queue WHERE title_id = ?", [
                    (i,) for i in ids])
                logger.info(f"Bulk Delete triggered for {len(ids)} items.")
            elif payload.action == "refresh":
                for tid in ids:
                    game = conn.execute(
                        "SELECT name FROM games WHERE title_id = ?", (tid,)).fetchone()
                    if game:
                        # FastAPI utilizes a secondary worker pool for background_tasks; safe from main loop
                        background_tasks.add_task(
                            scout.scout_title, tid, game[0])

            conn.commit()
            return {"message": f"Successfully processed {payload.action} for {len(ids)} games."}
        finally:
            conn.close()

    return await asyncio.to_thread(_bulk)


@api_router.post("/system/update-all")
async def trigger_update_all(background_tasks: BackgroundTasks):
    background_tasks.add_task(scout.run_library_sync)
    background_tasks.add_task(parser.sync_database)
    return {"message": "System update tasks started in background."}


@api_router.get("/system/health")
async def get_system_health():
    '''
    ARCHITECTURE: making this state aware so we get the current mount status
    '''
    def _health():
        return {
            "library": mount_manager.get_disk_telem(settings.library_dir),
            "incomplete": mount_manager.get_disk_telem(settings.incomplete_dir),

            "states": {
                "library": mount_manager.check_mount_health(settings.library_dir),
                "incomplete": mount_manager.check_mount_health(settings.incomplete_dir)
            }
        }
    return await asyncio.to_thread(_health)


@api_router.post("/system/health/refresh")
async def trigger_mount_refresh():
    '''
    ARCHITECTURE: Allows refreshing rather than a strict 60s poll
    '''
    #! DEBUG:
    logger.info("SYSTEM: Manual hardware health refresh triggered by UI.")
    await asyncio.to_thread(mount_manager.heartbeat_mon)

    return {"message": "Hardware status updated.", "status": "success"}


@api_router.get("/system/status")
async def get_system_status():
    def _status():
        sources_configured = any([
            settings.source_vita,
            settings.source_psp,
            settings.source_psx
        ])

        return {
            "status": "online",
            "sources_configured": sources_configured,
            "warning": None if sources_configured else "No game sources configured. Please check your .env file."
        }
    return await asyncio.to_thread(_status)

app.include_router(api_router)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
