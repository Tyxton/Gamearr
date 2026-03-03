import pandas as pd
import requests
from io import StringIO
from backend import database

MANIFESTS = {
    "vita": "https://nopaystation.com/tsv/PSV_GAMES.tsv",
    "psp": "https://nopaystation.com/tsv/PSP_GAMES.tsv",
    "psx": "https://nopaystation.com/tsv/PSX_GAMES.tsv"
} 

def sync_database():
    for platform, url in MANIFESTS.items():
        config_key = f"tsv_last_modified_{platform}"
        last_modified = database.get_config(config_key)
        headers = {"If-Modified-Since": last_modified} if last_modified else {}
    
        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                print(f"New {platform.upper()} manifest available. Parsing and seeding to database...")
                data = StringIO(response.text)
                
                # preload the TSV to avoid 'usecols' mismatch errors
                df = pd.read_csv(data, sep='\t')

                # Normalize column names (NPS can be inconsistent)
                # Maps their headers to our variables
                mapping = {
                        'Title ID': 'title_id',
                        'Region': 'region',
                        'Name': 'name',
                        'PKG direct link': 'pkg_url',
                        'PKG': 'pkg_url',
                        'zRIF': 'license_key',
                        'RAP': 'license_key'
                }

                # Rename columns to match DB schema
                df = df.rename(columns=mapping)

                # explicitly set the platform 
                df['platform'] = platform

                # Reorder and reliter to ONLY the 6 columns in the database scheme
                db_ready_df = df[['title_id', 'platform', 'region', 'name', 'pkg_url', 'license_key']].copy()

                # BATCH INSERT:
                # Instead of 10,000 individual calls, use pandas a batch insert
                conn = database.get_db_connection()
                try:
                    # Clear old entries for this platform to prevent Primary Key conflics
                    conn.execute("DELETE FROM games WHERE platform = ?", (platform,))

                    # Use 'append' because the rows have been cleared
                    db_ready_df.to_sql('games', conn, if_exists='append', index=False)
                    conn.close()
                finally:
                    conn.close()

                if 'Last-Modified' in response.headers:
                    database.set_config(config_key, response.headers.get('Last-Modified'))
                    print(f"{platform.upper()} sync complete.")

            elif response.status_code == 304:
                print(f"{platform.upper()} manifest is unchanged. Skipping.")

        except Exception as e:
            print(f"Failure during {platform} sync: {e}")
