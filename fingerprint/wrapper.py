import subprocess
import sys
from pathlib import Path
import os
import re
import shutil

from fprint.paths import FINGERPRINT_DB_PATH, FINGERPRINT_DB_DIR

BASE_DIR = Path(__file__).resolve().parent.parent
AUDFPRINT_SCRIPT = BASE_DIR / "audfprint" / "audfprint.py"
AUDFPRINT_DIR = BASE_DIR / "audfprint"


class AudfprintWrapper:
    def __init__(self, db_path: Path = FINGERPRINT_DB_PATH):
        self.db_path = Path(db_path)
        FINGERPRINT_DB_DIR.mkdir(parents=True, exist_ok=True)

    def _run(self, args: list[str]) -> str:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "ffmpeg not found. Install ffmpeg and make sure it is available in PATH."
            )

        command = [
            sys.executable,
            str(AUDFPRINT_SCRIPT),
            *args
        ]

        result = subprocess.run(
        command,
        cwd=str(AUDFPRINT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "PYTHONIOENCODING": "utf-8"
        }
    )

        if result.returncode != 0:
            raise RuntimeError(
                f"Audfprint error:\n{result.stderr}\n{result.stdout}"
            )

        return result.stdout.strip()

    def create_db(self, audio_files: list[str | Path]) -> str:
        files = [str(Path(file).resolve()) for file in audio_files]

        return self._run([
            "new",
            "--dbase",
            str(self.db_path),
            *files
        ])

    def add_to_db(self, audio_files: list[str | Path]) -> str:
        files = [str(Path(file).resolve()) for file in audio_files]

        return self._run([
            "add",
            "--dbase",
            str(self.db_path),
            *files
        ])

    def match(self, sample_file: str | Path) -> str:
        return self._run([
            "match",
            "--dbase",
            str(self.db_path),
            str(Path(sample_file).resolve())
        ])
    
    def parse_match_output(self, output: str) -> dict:
        pattern = re.search(
            r"Matched\s+(?P<sample>.+?)\s+"
            r"(?P<sample_duration>\d+\.?\d*)\s+sec\s+"
            r"(?P<raw_hashes>\d+)\s+raw hashes as\s+"
            r"(?P<track>.+?)\s+at\s+"
            r"(?P<offset>\d+\.?\d*)\s+s\s+with\s+"
            r"(?P<common_hashes>\d+)\s+of\s+"
            r"(?P<total_hashes>\d+)\s+common hashes",
            output
        )

        if not pattern:
            return {
                "matched": False,
                "raw_output": output
            }

        data = pattern.groupdict()

        common_hashes = int(data["common_hashes"])
        total_hashes = int(data["total_hashes"])

        confidence = round((common_hashes / total_hashes) * 100, 2) if total_hashes else 0

        return {
            "matched": True,
            "sample_path": data["sample"].strip(),
            "sample_duration": float(data["sample_duration"]),
            "raw_hashes": int(data["raw_hashes"]),
            "track_path": data["track"].strip(),
            "track_name": Path(data["track"]).name,
            "offset": float(data["offset"]),
            "common_hashes": common_hashes,
            "total_hashes": total_hashes,
            "confidence": confidence,
            "raw_output": output
        }

    def match_parsed(self, sample_file: str | Path) -> dict:
        output = self.match(sample_file)
        return self.parse_match_output(output)
    
    def identify(self, sample_file: str | Path) -> dict:
        result = self.match_parsed(sample_file)

        if not result["matched"]:
            return {
                "found": False,
                "message": "No match found"
            }

        if result["common_hashes"] < 50:
            return {
                "found": False,
                "message": "Weak match",
                "result": result
            }

        return {
            "found": True,
            "track_name": result["track_name"],
            "track_path": result["track_path"],
            "offset": result["offset"],
            "confidence": result["confidence"],
            "common_hashes": result["common_hashes"]
        }
