import time
import os
import re
import requests
from dotenv import load_dotenv
from backend import database

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
            print(f"Critical Error: Could not refresh IGDB token: {e}")
            return None
    return token

def get_game_metadata(title_id, game_name):
    """Queries local DB first then IGDB, strictly filtering for Main Games (category 0)."""
    # Check local cache first
    cached = database.get_cached_metadata(title_id)
    if cached:
        return {"name": game_name, "summary": cached[0], "cover": cached[1]}

    token = get_valid_token()
    if not token: return None

    # Prep metadata
    url = "https://api.igdb.com/v4/games"
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain"
    }

    # Clean name: removes "(USA)", "v1.0", etc. often found in TSV filenames
    clean_name = re.sub(r'\(.*?\)|\[.*?\]', '', game_name).strip()
    clean_name = re.sub(r'[^\w\s]', '', clean_name)

    # query: 
    # category = 0 (Main Game) ensures just the game art is downloaded not a 'Soundtrack' or 'DLC' poster.
    body = f'search "{clean_name}"; fields name, summary, cover.url, category; where category = 0; limit 1;'

    try:
        response = requests.post(url, headers=headers, data=body)
        if response.status_code == 200:
            data = response.json()
            if not data: 
                # Fallback: If no "Main Game" found, try without the category filter
                body_fallback = f'search "{clean_name}"; fields name, summary, cover.url; limit 1;'
                data = requests.post(url, headers=headers, data=body_fallback).json()
                if not data: return None

            game = data[0]
            raw_url = game.get('cover', {}).get('url', '')
            
            # Pull the 720p images for a crisper look
            if raw_url:
                hd_cover = raw_url.replace('t_thumb', 't_720p')
                if hd_cover.startswith('//'):
                    hd_cover = "https:" + hd_cover
            else:
                hd_cover = None

            summary = game.get("summary", "No description found in Motherbase archives.")

            # Persist
            database.save_metadata(title_id, summary, hd_cover)

            return {
                "name": game.get("name"),
                "summary": summary,
                "cover": hd_cover
            }
    except Exception as e:
        print(f"Comms Failure with IGDB: {e}")
        return None
