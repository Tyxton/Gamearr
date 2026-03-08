import os
import pandas as pd
import requests
import numpy as np
from io import StringIO
from backend import database
from backend.logger import logger


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

    #! DESTRUCTIVE: os.getenv stripped entirely. Valued loaded stricly through Pydantic config.
    active_manifests = {
        "vita": settings.source_vita,
        "psp": settings.source_psp,
        "psx": settings.source_psx
    }

    active_manifests = {k: v for k, v in active_manifests.items() if v}

    if not active_manifests:
        logger.warning(
            "NPS Sync: No Source URLs provided in environment variables. Database Sync Skipped.")
        return

    for platform, url in active_manifests.items():
        logger.info(f"NPS Sync: Checking for updates from {
                    platform.upper()} source...")

        config_key = f"tsv_last_modified_{platform}"
        last_modified = database.get_config(config_key)
        headers = {"If-Modified-Since": last_modified} if last_modified else {}

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                logger.info(
                    f"New {platform.upper()} manifest available. Parsing and seeding to database...")
                data = StringIO(response.text)
                df = pd.read_csv(data, sep='\t', on_bad_lines='skip')

                df = df.rename(columns=mapping)
                df['platform'] = platform

                #! CRUCIAL: Sanitize Title ID to prevent Primary Key collisions, PSX manifests often
                # have trailing/leading spaces in IDs.
                # also implementing forced casing which should catch 'scus-123' vs 'SCUS-123'
                if 'title_id' in df.columns:
                    df['title_id'] = df['title_id'].astype(
                        str).str.strip().str.upper()

                cols = ['title_id', 'platform', 'region',
                        'name', 'pkg_url', 'license_key']

                db_ready_df = df[[c for c in cols if c in df.columns]].copy()
                for missing_col in set(cols) - set(db_ready_df.columns):
                    db_ready_df[missing_col] = np.nan

                db_ready_df = db_ready_df.sort_values(
                    by=['title_id', 'pkg_url', 'license_key'],  # as List[str]
                    na_position='last'
                )

                # The original parser in v0.2.0 used a for loop, which included all platofrms, keeping it
                # universal guarantees that even if the PSP, and PSV titles aren't clean (which I assumed
                # that they were) ensures a clean to_sql().
                # PSX has multi-disc entries that can crash the primary key constraint
                db_ready_df = db_ready_df.drop_duplicates(
                    subset=['title_id'], keep='first')

                db_ready_df = db_ready_df.dropna(subset=['title_id', 'name'])
                db_ready_df['license_key'] = db_ready_df['license_key'].fillna(
                    "MISSING")
                #! CRUCIAL: Make sure any NaNs are converted to JSON None
                db_ready_df = db_ready_df.astype(
                    object).replace({np.nan: None})

                conn = database.get_db_connection()
                try:
                    sql = '''
                        INSERT OR REPLACE INTO games (title_id, platform, region, name, pkg_url, license_key)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(title_id) DO UPDATE SET
                            pkg_url=excluded.pkg_url,
                            license_key=excluded.license_key
                    '''

                    columns_to_insert = ['title_id', 'platform',
                                         'region', 'name', 'pkg_url', 'license_key']
                    records = db_ready_df[columns_to_insert].values.tolist()
                    conn.executemany(sql, records)
                    conn.commit()
                    logger.info(
                        "Database sync: UPSERT complete. No downtime occurred.")
                except Exception as e:
                    logger.error(f"PARSING ERROR: Database insertion failed for {
                                 platform}: {e}")
                finally:
                    conn.close()

                if 'Last-Modified' in response.headers:
                    database.set_config(
                        config_key, response.headers.get('Last-Modified'))
                    logger.info(f"{platform.upper()} sync complete.")

            elif response.status_code == 304:
                logger.info(
                    f"{platform.upper()} manifest is unchanged. Skipping.")

        except Exception as e:
            logger.error(f"Failure during {platform} sync: {e}")
