import subprocess
import errno
import os
from sys import stderr
import zipfile
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

        with subprocess.Popen(
                command,
                cwd=str(work_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
        ) as proc:
            try:
                _, stderr = proc.communicate(timeout=7200)
                if proc.returncode != 0:
                    logger.error(f"EXTRACTION FAILURE: pkg2zip exited {
                                 proc.returncode}. Error: {stderr}")
                    return False
            except subprocess.TimeoutExpired:
                proc.kill()
                logger.error(
                    "EXTRACTION CRITICAL: pkg2zip timed out after 2 hours.")
                return False

        if platform.lower() in ['psx', 'psp']:
            zip_files = list(work_dir.glob("*.zip"))
            if not zip_files:
                logger.error(
                    "EXTRACTION ERROR: pkg2zip succeeded but no ZIP archive was found.")
                return False

            for z_file in zip_files:
                logger.info(
                    f"EXTRACTION: Unpacking PSX/PSP archive: {z_file.name}")
                with zipfile.ZipFile(z_file, 'r') as zip_ref:
                    zip_ref.extractall(work_dir)

                z_file.unlink()

        logger.info(f"Extraction block finalized in {work_dir}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"EXTRACTION ERROR: Subprocess trace failed: {e}")
        return False
    except zipfile.BadZipFile:
        logger.error("EXRACTION ERROR: Created ZIP archive is corrupt.")
        return False
    except FileNotFoundError:
        logger.error(
            "EXTRACTION FATAL: 'pkg2zip' binary unreachable in host PATH.")
        return False
    except OSError as e:
        if e.errno == errno.ENOENT:
            logger.error(
                "EXTRACTION FATAL: 'pkg2zip' binary unreachable in host PATH.")
