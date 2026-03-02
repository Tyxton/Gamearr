import time
import os
import shutil
from backend import database, downloader, extractor

INCOMPLETE_DIR = os.getenv("INCOMPLETE_DIR", "/downloads")
LIBRARY_DIR = os.getenv("LIBRARY_DIR", "/library")

def start_worker():
    print("Monitoring Queue...")

    while True:
        # check for next pending game
        get_next = database.get_next_queued_task()

        if not get_next:
            # if nothing in queue, rest for 30 seconds
            time.sleep(30)
            continue
        
        title_id = get_next['title_id']
        name = get_next['name']
        platform = get_next['platform']
        pkg_url = get_next['pkg_url']
        license_key = get_next['license_key']

        print(f"\nFound in queue: {name} ({platform.upper()})")

        # update status
        database.update_queue_status(title_id, 'downloading')

        # initiate the download
        try:
            success = downloader.download_pkg(pkg_url, title_id, name)

            if success:
                print(f"Download complete. Starting extraction for {title_id}...")

                # contruct path
                from backend.downloader import get_safe_name
                safe_folder = get_safe_name(name)

                pkg_file = os.path.join(INCOMPLETE_DIR, safe_folder, f"{title_id}.pkg")

                # now extract
                if extractor.extract_pkg(pkg_file, license_key, platform):
                    print(f"Extraction Complete. Moving to Library: {name}")
                    
                    extracted_source = os.path.join(INCOMPLETE_DIR, safe_folder)
                    destination_path = os.path.join(LIBRARY_DIR, safe_folder)
                    
                    try:
                        # Move entire folder to the persistent library mount
                        if os.path.exists(destination_path):
                            shutil.rmtree(destination_path) # overwrite if it exists

                        shutil.move(extracted_source, destination_path)
                        print(f"Successfully extracted {name} to {destination_path}")
                        database.update_queue_status(title_id, 'completed')
                    except Exception as move_error:
                        print(f"Transfer Failed: {move_error}")
                        database.update_queue_status(title_id, 'failed_move')
                else:
                    print(f"Extraction failed for {name}")
                    database.update_queue_status(title_id, 'failed_extraction')
            else:
                database.update_queue_status(title_id, 'failed_download')

        except Exception as e:
            print(f"Error during {name}: {e}")
            database.update_queue_status(title_id, 'error')

if __name__ == "__main__":
    start_worker()

