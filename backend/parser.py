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
                
                # ensure the required columns exist before sclicing to prevent Key Error
                for col in ['PKG', 'zRIF', 'RAP', 'PKG direct link']:
                    if col not in df.columns:
                        df[col] = "MISSING"

                df = df.rename(columns=mapping)
                df['platform'] = platform
                
                cols = ['title_id', 'platform', 'region', 'name', 'pkg_url', 'license_key']
                df_ready_df = df[cols].copy()

                # Drop invalid rows and DUPLICATE IDs -- PSX parsing fix
                db_ready_df = db_ready_df.dropna(subset=['title_id', 'name'])
                db_ready_df = db_ready_df.drop_duplicates(subset=['title-id'], keep='first')
                
                # THEN replace internal NaNs with 'MISSING' before sql
                db_ready_df = db_ready_df.fillna('MISSING')
                
                # Just in case, make sure any leftover NaN variables are Python None
                import numpy as np
                db_ready_df = db_ready_df.astype(object).replace({np.nan: None})

                try:
                    # Clear old entries for this platform to prevent Primary Key conflics
                    conn.execute("DELETE FROM games WHERE platform = ?", (platform,))

                    # Use 'append' because the rows have been cleared
                    db_ready_df.to_sql('games', conn, if_exists='append', index=False)
                    conn.commit() # NOT conn.close() THIS WOULD'VE WORKED VERSIONS AGO HAD I CAUGHT THIS.
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
