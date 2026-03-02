import subprocess
import os
import re

INCOMPLETE_DIR = os.getenv("INCOMPLETE_DIR", "/downloads")

def download_pkg(url, title_id, name):
    '''
    Uses aria2c to download the PKG files, creates a dedicated folder for each game
    '''
    safe_name = get_safe_name(name)

    download_dir = os.path.join(INCOMPLETE_DIR, safe_name)

    if not os.path.exists(download_dir):
        os.makedirs(download_dir, exist_ok=True)

    print(f"\nInitiating download for: {name}")
    print(f" Destination: {download_dir}/{title_id}.pkg")
    
    threads = str(os.getenv("ARIA2_THREADS", "16"))

    command = [
        "aria2c",
        "-x", threads,
        "-s", threads,
        "-d", download_dir,
        "-o", f"{title_id}.pkg",
        "--summary-interval", "0",
        url
    ]

    try:
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"Download failed for {name}")
        return False

def get_safe_name(name, title_id=None):
    '''
    Creates a filesystem-safe name. 
    '''
    # Remove special characters but keep spaces and dashes
    clean = re.sub(r'[^\w\s\-]', '', name).strip()
    
    if title_id:
        return f"{clean} [{title_id}]"
    return clean
