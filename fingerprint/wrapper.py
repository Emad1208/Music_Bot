import subprocess
import sys
from pathlib import Path
import os
import re
import shutil

from fprint.paths import FINGERPRINT_DB_PATH
from fingerprint.storage import FingerprintDatabaseStorage

BASE_DIR = Path(__file__).resolve().parent.parent
AUDFPRINT_SCRIPT = BASE_DIR / "audfprint" / "audfprint.py"
AUDFPRINT_DIR = BASE_DIR / "audfprint"

DEFAULT_DENSITY = 50
DEFAULT_FANOUT = 6
DEFAULT_MIN_COUNT = 5
DEFAULT_SEARCH_DEPTH = 200
MIN_COMMON_HASHES = 8


class AudfprintWrapper:
    def __init__(self, db_path: Path = FINGERPRINT_DB_PATH):
        self.db_path = Path(db_path).resolve()
        self.storage = FingerprintDatabaseStorage(self.db_path)

    def _analysis_args(self) -> list[str]:
        return [
            "--density",
            str(DEFAULT_DENSITY),
            "--fanout",
            str(DEFAULT_FANOUT),
        ]

    def _match_args(self) -> list[str]:
        return [
            *self._analysis_args(),
            "--min-count",
            str(DEFAULT_MIN_COUNT),
            "--search-depth",
            str(DEFAULT_SEARCH_DEPTH),
        ]

    def _run(
        self,
        args: list[str],
        *,
        require_ffmpeg: bool = True,
        discard_stdout: bool = False,
    ) -> str:
        if require_ffmpeg and shutil.which("ffmpeg") is None:
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
            stdout=subprocess.DEVNULL if discard_stdout else subprocess.PIPE,
            stderr=subprocess.PIPE,
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
                f"Audfprint error:\n{result.stderr}\n{result.stdout or ''}"
            )

        return (result.stdout or "").strip()

    def _write_database(
        self,
        audio_files: list[str | Path],
        *,
        mode: str,
        track_keys: list[str] | None = None,
    ) -> str:
        files = [str(Path(file).resolve()) for file in audio_files]
        if not files:
            raise ValueError("At least one audio file is required")

        for file in files:
            if not Path(file).is_file():
                raise FileNotFoundError(file)

        if track_keys is not None:
            if len(track_keys) != len(files):
                raise ValueError("track_keys must match the number of audio files")
            for track_key in track_keys:
                if not track_key or Path(track_key).name != track_key:
                    raise ValueError(f"Invalid track key: {track_key!r}")

        def update(working_path: Path, current_exists: bool) -> str:
            command = mode
            if mode == "auto":
                command = "add" if current_exists else "new"

            ingest_files = files
            aliases: list[Path] = []
            if track_keys is not None:
                ingest_files, aliases = self._create_ingest_aliases(files, track_keys)

            try:
                return self._run([
                    command,
                    "--dbase",
                    str(working_path),
                    *self._analysis_args(),
                    *ingest_files,
                ])
            finally:
                for alias in aliases:
                    try:
                        alias.unlink()
                    except FileNotFoundError:
                        pass

        return self.storage.atomic_update(
            update,
            require_existing=mode == "add",
            require_missing=mode == "new",
        )

    def _create_ingest_aliases(
        self,
        files: list[str],
        track_keys: list[str],
    ) -> tuple[list[str], list[Path]]:
        ingest_dir = self.db_path.parent / ".ingest"
        ingest_dir.mkdir(parents=True, exist_ok=True)

        aliases = [ingest_dir / track_key for track_key in track_keys]
        created_aliases: list[Path] = []
        try:
            for source, alias in zip(files, aliases):
                try:
                    alias.unlink()
                except FileNotFoundError:
                    pass

                try:
                    os.link(source, alias)
                except OSError:
                    shutil.copy2(source, alias)
                created_aliases.append(alias)
        except Exception:
            for alias in created_aliases:
                try:
                    alias.unlink()
                except FileNotFoundError:
                    pass
            raise

        return [str(alias.resolve()) for alias in aliases], aliases

    def create_db(
        self,
        audio_files: list[str | Path],
        *,
        track_keys: list[str] | None = None,
    ) -> str:
        return self._write_database(
            audio_files,
            mode="new",
            track_keys=track_keys,
        )

    def add_to_db(
        self,
        audio_files: list[str | Path],
        *,
        track_keys: list[str] | None = None,
    ) -> str:
        return self._write_database(
            audio_files,
            mode="add",
            track_keys=track_keys,
        )

    def add_or_create(
        self,
        audio_files: list[str | Path],
        *,
        track_keys: list[str] | None = None,
    ) -> str:
        return self._write_database(
            audio_files,
            mode="auto",
            track_keys=track_keys,
        )

    def remove_from_db(self, track_keys: list[str]) -> str:
        if not track_keys:
            return ""
        for track_key in track_keys:
            if not track_key or Path(track_key).name != track_key:
                raise ValueError(f"Invalid track key: {track_key!r}")

        stored_paths = [
            str((self.db_path.parent / ".ingest" / track_key).resolve())
            for track_key in track_keys
        ]

        def update(working_path: Path, current_exists: bool) -> str:
            return self._run(
                [
                    "remove",
                    "--dbase",
                    str(working_path),
                    *stored_paths,
                ],
                require_ffmpeg=False,
            )

        return self.storage.atomic_update(update, require_existing=True)

    def validate_db(self) -> None:
        self.storage.validate_gzip()
        self._semantic_validate(self.db_path)

    def recover_database(self, *, promote: bool = False) -> dict:
        return self.storage.recover_corrupted_gzip(
            self._semantic_validate,
            promote=promote,
        )

    def _semantic_validate(self, db_path: Path) -> None:
        self._run(
            ["list", "--dbase", str(db_path)],
            require_ffmpeg=False,
            discard_stdout=True,
        )

    def match(self, sample_file: str | Path) -> str:
        return self._run([
            "match",
            "--dbase",
            str(self.db_path),
            *self._match_args(),
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

        if result["common_hashes"] < MIN_COMMON_HASHES:
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
