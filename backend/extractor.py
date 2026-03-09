import subprocess
from pathlib import Path

from backend.logger import logger


def extract_pkg(pkg_path: Path, license_key: str, platform: str) -> bool:
    '''
    #! DESTRUCTIVE: os.path.dirname replace by Path.parent mapping.
    Isolates cwd context to strictly defines directories to prevent extraction bleed.
    '''

    if not pkg_path.exists():
        logger.error(f"EXTRACTION ERROR: PKG missing at {pkg_path}")
        return False

    pkg_filename = pkg_path.name
    work_dir = pkg_path.parent

    logger.info(f"Decrypting: {pkg_filename}...")

    if platform.lower() == 'vita':
        command = ["pkg2zip", "-x", pkg_filename, license_key]
    else:
        if license_key == "MISSING" or not license_key:
            command = ["pkg2zip", pkg_filename]
        else:
            command = ["pkg2zip", pkg_filename, license_key]

    try:
        subprocess.run(command, check=True, cwd=str(work_dir))
        logger.info(f"Extraction block finalized in {work_dir}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"EXTRACTION ERROR: Subprocess trace failed: {e}")
        return False
    except FileNotFoundError:
        logger.error(
            "EXTRACTION FATAL: 'pkg2zip' binary unreachable in host PATH.")
        return False
