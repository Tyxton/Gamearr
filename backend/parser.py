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
                
                # Direct load with only the columns needed
                cols = ['Title ID', 'Region', 'Name', 'PKG direct link']
                # NPS headers vary slightly between platforms; handle zRIF/RAP specifically
                df = pd.read_csv(data, sep='\t', usecols=lambda x: x in cols or x in ['zRIF', 'RAP'])

                # Normalize the license key column
                if 'zRIF' in df.columns:
                    df['license_key'] = df['zRIF'].fillna("MISSING")
                elif 'RAP' in df.columns:
                    df['license_key'] = df['RAP'].fillna("MISSING")
                else:
                    df['license_key'] = "MISSING"

                # Rename columns to match DB schema
                df = df.rename(columns={
                    'Title ID': 'title_id',
                    'Region': 'region',
                    'Name': 'name',
                    'PKG direct link': 'pkg_url'
                })
                df['platform'] = platform

                # BATCH INSERT:
                # Instead of 10,000 individual calls, use pandas a batch insert
                conn = database.get_db_connection()
                try:
                    conn.execute("DELETE FROM games WHERE platform = ?", (platform,))
                    
                    df[['title_id', 'platform', 'region', 'name', 'pkg_url', 'license_key']].to_sql(
                        'games', conn, if_exists='append', index=False
                    )
                    conn.commit()
                finally:
                    conn.close()

                if 'Last-Modified' in response.headers:
                    database.set_config(config_key, response.headers.get('Last-Modified'))
                    print(f"{platform.upper()} sync complete.")

            elif response.status_code == 304:
                print(f"{platform.upper()} manifest is unchanged. Skipping.")

        except Exception as e:
            print(f"Failure during {platform} sync: {e}")
