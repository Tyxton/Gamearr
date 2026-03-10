import subprocess
import os
from pathlib import Path

from backend.logger import logger
from backend.config import settings


def extract_pkg(pkg_path: Path, license_key: str, platform: str) -> bool:
    '''
    Lower the process priority on ARM-based systems to ensure the web UI is responsive
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
        priority = 15 if settings.is_arm else 0

        logger.info(f"EXTRACTION: Starting pkg2zip (Priotity: {
                    priority}) for {pkg_filename}")

        def _set_priority():
            try:
                os.nice(priority)
            except AttributeError:
                #! ARCHITECTURE: Non-POSIX (i.e Windows) don't support nice
                pass

        subprocess.run(
            command,
            check=True,
            cwd=str(work_dir),
            preexec_fn=_set_priority if priority > 0 else None,
            capture_output=True,
            text=True
        )
        logger.info(f"Extraction block finalized in {work_dir}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"EXTRACTION ERROR: Subprocess trace failed: {e}")
        return False
    except FileNotFoundError:
        logger.error(
            "EXTRACTION FATAL: 'pkg2zip' binary unreachable in host PATH.")
        return False
