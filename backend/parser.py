import pandas as pd
import requests
import numpy as np
from io import StringIO
from backend import database

MANIFESTS = {
    "vita": "https://nopaystation.com/tsv/PSV_GAMES.tsv",
    "psp": "https://nopaystation.com/tsv/PSP_GAMES.tsv",
    "psx": "https://nopaystation.com/tsv/PSX_GAMES.tsv"
} 

def sync_database():
    
    mapping = {
            'Title ID': 'title_id',
            'Region': 'region',
            'Name': 'name',
            'PKG direct link': 'pkg_url',
            'PKG': 'pkg_url',
            'zRIF': 'license_key',
            'RAP': 'license_key',
    }

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
                df = pd.read_csv(data, sep='\t', on_bad_lines='skip') # handle shifted headers
                
                # map columns before init
                df = df.rename(columns=mapping)
                df['platform'] = platform
                cols = ['title_id', 'platform', 'region', 'name', 'pkg_url', 'license_key']
               
                # safely create db_ready_df
                db_ready_df = df[[c for c in cols if c in df.columns]].copy()
                for missing_col in set(cols) - set(db_ready_df.columns):
                    db_ready_df[missing_col] = None
                
                # Apply PSX specific dedup 
                if platform == "psx":
                    # PSX has multi-disc entries that can crash the primary key constraint
                    db_ready_df = db_ready_df.drop_duplicates(subset=['title_id'], keep='first')
                
                # cleanup db_ready_df
                db_ready_df = db_ready_df.dropna(subset=['title_id', 'name'])
                
                # Just in case, make sure any leftover NaN variables are Python None
                db_ready_df = db_ready_df.astype(object).replace({np.nan: None})

                conn = database.get_db_connection()
                try:
                    # Clear old entries for this platform to prevent Primary Key conflics
                    conn.execute("DELETE FROM games WHERE platform = ?", (platform,))
                    db_ready_df.to_sql('games', conn, if_exists='append', index=False)
                    conn.commit()
                except Exception as e:
                    # Don't save anything on failure, rollback implicit
                    print(f"[!] Error: Database insertion failed for {platform}: {e}")
                finally:
                    conn.close()

                if 'Last-Modified' in response.headers:
                    database.set_config(config_key, response.headers.get('Last-Modified'))
                    print(f"{platform.upper()} sync complete.")

            elif response.status_code == 304:
                print(f"{platform.upper()} manifest is unchanged. Skipping.")

        except Exception as e:
            print(f"Failure during {platform} sync: {e}")
