import time
import os
import re
import requests
from dotenv import load_dotenv
from backend import database
from backend.logger import logger

load_dotenv()

client_id = os.getenv("IGDB_CLIENT_ID")
client_secret = os.getenv("IGDB_CLIENT_SECRET")


def get_valid_token():
    """Checks the DB for a valid token, refreshes from Twitch if expired."""
    token = database.get_config("igdb_token")
    expiry = database.get_config("igdb_expiry")
    current_time = int(time.time())

    if not token or not expiry or current_time >= (int(expiry) - 60):
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials"
        }
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            data = response.json()
            token = data['access_token']
            new_expiry = current_time + data['expires_in']
            database.set_config("igdb_token", token)
            database.set_config("igdb_expiry", str(new_expiry))
            return token
        except Exception as e:
            logger.error(f"CRITIAL ERROR: Could not refresh IGDB token: {e}")
            return None
    return token


def get_game_metadata(title_id, game_name):
    """Queries local DB first then IGDB."""
    cached = database.get_cached_metadata(title_id)
    if cached and "placeholder.png" not in str(cached[1]):
        return {"name": game_name, "summary": cached[0], "cover_url": cached[1]}

    token = get_valid_token()
    if not token:
        return None

    # ONLY remove (USA), [PCSE00120], etc.
    # KEEP colons, hyphens, and apostrophes (e.g., "Metal Gear Solid: Peace Walker")
    clean_name = re.sub(r'\(.*?\)|\[.*?\]', '', game_name).strip()

    url = "https://api.igdb.com/v4/games"
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain"
    }

    # We search for the name, but we ask for 5 results so we can find the best "Main Game"
    body = f'search "{
        clean_name}"; fields name, summary, cover.url, category; limit 5;'

    try:
        logger.info(f"IGDB: Searching for '{clean_name}'...")
        response = requests.post(url, headers=headers, data=body)

        if response.status_code == 200:
            results = response.json()

            if results:
                # Filter results for: 0 (Main Game), 8 (Remake), 9 (Remaster), 10 (Expanded Game)
                # This ignores Soundtracks, DLCs, and Bundles
                valid_categories = [0, 8, 9, 10, 11]
                best_match = None

                for res in results:
                    if res.get('category') in valid_categories and 'cover' in res:
                        best_match = res
                        break

                # Fallback: If no "Main Game" found, just take the first result with a cover
                if not best_match:
                    for res in results:
                        if 'cover' in res:
                            best_match = res
                            break

                if best_match:
                    raw_url = best_match.get('cover', {}).get('url', '')
                    hd_cover = "https:" + raw_url.replace('t_thumb', 't_720p')
                    summary = best_match.get(
                        "summary", "No description found.")

                    database.save_metadata(title_id, summary, hd_cover)
                    logger.info(f"IGDB: Success! Found art for {clean_name}")
                    return {"name": best_match.get("name"), "summary": summary, "cover_url": hd_cover}

            logger.info(f"IGDB: No suitable match found for '{clean_name}'")
    except Exception as e:
        logger.error(f"IGDB Comms Failure: {e}")

    return {"cover_url": "/assets/placeholder.png", "summary": "Metadata not found."}
