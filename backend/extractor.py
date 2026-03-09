import subprocess
import os

from backend.logger import logger


def extract_pkg(pkg_path, license_key, platform):
    """
    Decrypts the PKG. pkg_path should be the relative path to the file.
    """
    if not os.path.exists(pkg_path):
        logger.error(f"EXTRACT ERROR: PKG file not found at {pkg_path}")
        return False

    pkg_filename = os.path.basename(pkg_path)
    work_dir = os.path.dirname(os.path.abspath(pkg_path))

    logger.info(f"Decrypting: {pkg_filename}...")

    if platform.lower() == 'vita':
        # pkg2zip handles zRIF
        command = ["pkg2zip", "-x", pkg_filename, license_key]
    else:
        if license_key == "MISSING" or not license_key:
            command = ["pkg2zip", pkg_filename]
        else:
            command = ["pkg2zip", pkg_filename, license_key]
    try:
        # Run pkg2zip inside the game's specific download folder
        subprocess.run(command, check=True, cwd=work_dir)
        logger.info(f"Extraction complete in {work_dir}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"EXTRACT ERROR: pkg2zip failed: {e}")
        return False
    except FileNotFoundError:
        logger.error("ERROR: 'pkg2zip' is not installed or not in PATH.")
        return False
