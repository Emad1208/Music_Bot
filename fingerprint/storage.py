from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import threading
import time
import uuid
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, TypeVar


CHUNK_SIZE = 1024 * 1024
DEFAULT_BACKUP_COUNT = 5
DEFAULT_LOCK_TIMEOUT = 300.0

T = TypeVar("T")


class FingerprintDatabaseError(RuntimeError):
    pass


class FingerprintDatabaseCorruptError(FingerprintDatabaseError):
    pass


class FingerprintDatabaseLockTimeout(FingerprintDatabaseError):
    pass


_thread_locks_guard = threading.Lock()
_thread_locks: dict[str, threading.RLock] = {}


def _get_thread_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _thread_locks_guard:
        return _thread_locks.setdefault(key, threading.RLock())


class DatabaseFileLock:
    """Thread and process lock that is released automatically after a crash."""

    def __init__(self, path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT):
        self.path = Path(path)
        self.timeout = timeout
        self._thread_lock = _get_thread_lock(self.path)
        self._file = None

    def __enter__(self):
        if not self._thread_lock.acquire(timeout=self.timeout):
            raise FingerprintDatabaseLockTimeout(
                f"Timed out waiting for fingerprint database lock: {self.path}"
            )

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self.path, "a+b")
            self._ensure_lock_byte()
            self._acquire_os_lock()
            return self
        except Exception:
            if self._file is not None:
                self._file.close()
                self._file = None
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._file is not None:
                self._release_os_lock()
                self._file.close()
                self._file = None
        finally:
            self._thread_lock.release()

    def _ensure_lock_byte(self) -> None:
        self._file.seek(0, os.SEEK_END)
        if self._file.tell() == 0:
            self._file.write(b"0")
            self._file.flush()

    def _acquire_os_lock(self) -> None:
        deadline = time.monotonic() + self.timeout

        while True:
            try:
                self._file.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(
                        self._file.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                return
            except (BlockingIOError, OSError) as exc:
                if time.monotonic() >= deadline:
                    raise FingerprintDatabaseLockTimeout(
                        f"Timed out waiting for fingerprint database lock: {self.path}"
                    ) from exc
                time.sleep(0.1)

    def _release_os_lock(self) -> None:
        self._file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)


class FingerprintDatabaseStorage:
    def __init__(
        self,
        db_path: str | Path,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    ):
        self.db_path = Path(db_path).resolve()
        self.backup_count = max(1, backup_count)
        self.lock_path = self.db_path.parent / f".{self.db_path.name}.lock"
        self.backup_dir = self.db_path.parent / "backups"
        self.quarantine_dir = self.db_path.parent / "quarantine"
        self.lock_timeout = lock_timeout
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def write_lock(self) -> Iterator[None]:
        with DatabaseFileLock(self.lock_path, self.lock_timeout):
            yield

    def atomic_update(
        self,
        updater: Callable[[Path, bool], T],
        *,
        require_existing: bool = False,
        require_missing: bool = False,
    ) -> T:
        with self.write_lock():
            current_exists = self.db_path.is_file()
            if require_existing and not current_exists:
                raise FingerprintDatabaseError(
                    f"Fingerprint database does not exist: {self.db_path}"
                )
            if require_missing and current_exists:
                raise FingerprintDatabaseError(
                    f"Fingerprint database already exists: {self.db_path}"
                )

            working_path = self._temporary_path("working")
            try:
                if current_exists:
                    self._copy_with_fsync(self.db_path, working_path)

                result = updater(working_path, current_exists)
                self.validate_gzip(working_path)
                self._fsync_file(working_path)

                if current_exists:
                    self._create_backup()
                    self._prune_backups()

                self._replace_with_retry(working_path, self.db_path)
                self._fsync_directory(self.db_path.parent)
                return result
            finally:
                self._unlink_if_exists(working_path)

    def validate_gzip(self, path: str | Path | None = None) -> int:
        candidate = Path(path) if path is not None else self.db_path
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise FingerprintDatabaseCorruptError(
                f"Fingerprint database is missing or empty: {candidate}"
            )

        uncompressed_size = 0
        try:
            with gzip.open(candidate, "rb") as source:
                while True:
                    chunk = source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    uncompressed_size += len(chunk)
        except (EOFError, OSError, zlib.error) as exc:
            raise FingerprintDatabaseCorruptError(
                f"Fingerprint database gzip validation failed: {candidate}"
            ) from exc

        if uncompressed_size == 0:
            raise FingerprintDatabaseCorruptError(
                f"Fingerprint database contains no data: {candidate}"
            )
        return uncompressed_size

    def recover_corrupted_gzip(
        self,
        semantic_validator: Callable[[Path], None],
        *,
        promote: bool = False,
    ) -> dict[str, str | int | None]:
        with self.write_lock():
            if not self.db_path.is_file():
                raise FingerprintDatabaseError(
                    f"Fingerprint database does not exist: {self.db_path}"
                )

            recovered_path = self.db_path.with_name(
                f"{self.db_path.stem}.recovered{self.db_path.suffix}"
            )
            working_path = self._temporary_path("recovery")
            try:
                recovered_bytes = self._rebuild_gzip_stream(
                    self.db_path,
                    working_path,
                )
                self.validate_gzip(working_path)
                semantic_validator(working_path)
                self._fsync_file(working_path)
                self._replace_with_retry(working_path, recovered_path)
                self._fsync_directory(recovered_path.parent)

                quarantine_path = None
                if promote:
                    quarantine_path = self._promote_recovered_locked(
                        recovered_path,
                    )

                return {
                    "database": str(self.db_path),
                    "recovered": str(recovered_path),
                    "quarantine": (
                        str(quarantine_path) if quarantine_path else None
                    ),
                    "uncompressed_bytes": recovered_bytes,
                }
            finally:
                self._unlink_if_exists(working_path)

    def promote_replacement(
        self,
        replacement_path: str | Path,
        semantic_validator: Callable[[Path], None],
    ) -> Path:
        replacement_path = Path(replacement_path).resolve()
        with self.write_lock():
            self.validate_gzip(replacement_path)
            semantic_validator(replacement_path)
            return self._promote_recovered_locked(replacement_path)

    def _promote_recovered_locked(
        self,
        recovered_path: Path,
    ) -> Path:
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        quarantine_path = self.quarantine_dir / self._versioned_name("corrupt")
        self._copy_with_fsync(self.db_path, quarantine_path)

        replacement = self._temporary_path("replacement")
        try:
            self._copy_with_fsync(recovered_path, replacement)
            self._replace_with_retry(replacement, self.db_path)
            self._fsync_directory(self.db_path.parent)
        finally:
            self._unlink_if_exists(replacement)

        return quarantine_path

    def _rebuild_gzip_stream(self, source_path: Path, output_path: Path) -> int:
        uncompressed_size = 0
        with open(output_path, "wb") as raw_output:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_output,
                compresslevel=6,
                mtime=0,
            ) as gzip_output:
                for data in self.iter_decompressed_ignoring_trailer(source_path):
                    gzip_output.write(data)
                    uncompressed_size += len(data)

            raw_output.flush()
            os.fsync(raw_output.fileno())

        return uncompressed_size

    @classmethod
    def iter_decompressed_ignoring_trailer(
        cls,
        source_path: str | Path,
    ) -> Iterator[bytes]:
        source_path = Path(source_path)
        source_size = source_path.stat().st_size
        if source_size < 18:
            raise FingerprintDatabaseCorruptError(
                f"Fingerprint database is too small to be a gzip file: {source_path}"
            )

        with open(source_path, "rb") as source:
            payload_start = cls._gzip_payload_start(source)
            payload_end = source_size - 8
            if payload_start >= payload_end:
                raise FingerprintDatabaseCorruptError(
                    f"Fingerprint database has no compressed payload: {source_path}"
                )

            source.seek(payload_start)
            remaining = payload_end - payload_start
            decompressor = zlib.decompressobj(-zlib.MAX_WBITS)

            while remaining:
                compressed = source.read(min(CHUNK_SIZE, remaining))
                if not compressed:
                    break
                remaining -= len(compressed)

                pending = compressed
                while pending:
                    data = decompressor.decompress(pending, CHUNK_SIZE)
                    pending = decompressor.unconsumed_tail
                    if data:
                        yield data
                    if not data and not pending:
                        break

            tail = decompressor.flush()
            if tail:
                yield tail

        if remaining != 0 or not decompressor.eof:
            raise FingerprintDatabaseCorruptError(
                "The compressed fingerprint payload is truncated and cannot be "
                f"recovered safely: {source_path}"
            )
        if decompressor.unused_data:
            raise FingerprintDatabaseCorruptError(
                f"Unexpected data exists after the gzip payload: {source_path}"
            )

    @staticmethod
    def _gzip_payload_start(source) -> int:
        header = source.read(10)
        if len(header) != 10 or header[:3] != b"\x1f\x8b\x08":
            raise FingerprintDatabaseCorruptError("Invalid gzip header")

        flags = header[3]
        if flags & 0xE0:
            raise FingerprintDatabaseCorruptError("Invalid gzip flags")

        if flags & 0x04:
            extra_length_data = source.read(2)
            if len(extra_length_data) != 2:
                raise FingerprintDatabaseCorruptError("Truncated gzip extra field")
            extra_length = int.from_bytes(extra_length_data, "little")
            if len(source.read(extra_length)) != extra_length:
                raise FingerprintDatabaseCorruptError("Truncated gzip extra field")

        if flags & 0x08:
            FingerprintDatabaseStorage._skip_zero_terminated(source, "filename")
        if flags & 0x10:
            FingerprintDatabaseStorage._skip_zero_terminated(source, "comment")
        if flags & 0x02 and len(source.read(2)) != 2:
            raise FingerprintDatabaseCorruptError("Truncated gzip header CRC")

        return source.tell()

    @staticmethod
    def _skip_zero_terminated(source, field_name: str) -> None:
        while True:
            byte = source.read(1)
            if not byte:
                raise FingerprintDatabaseCorruptError(
                    f"Truncated gzip {field_name} field"
                )
            if byte == b"\x00":
                return

    def _create_backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self.backup_dir / self._versioned_name("backup")
        self._copy_with_fsync(self.db_path, backup_path)
        return backup_path

    def _prune_backups(self) -> None:
        if not self.backup_dir.exists():
            return
        backups = sorted(
            self.backup_dir.glob(f"{self.db_path.stem}.backup.*{self.db_path.suffix}"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for old_backup in backups[self.backup_count :]:
            self._unlink_if_exists(old_backup)

    def _versioned_name(self, label: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return (
            f"{self.db_path.stem}.{label}.{timestamp}.{uuid.uuid4().hex[:8]}"
            f"{self.db_path.suffix}"
        )

    def _temporary_path(self, label: str) -> Path:
        return self.db_path.parent / (
            f".{self.db_path.stem}.{label}.{uuid.uuid4().hex}{self.db_path.suffix}"
        )

    @staticmethod
    def _copy_with_fsync(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        FingerprintDatabaseStorage._fsync_file(destination)
        if (
            FingerprintDatabaseStorage._sha256(source)
            != FingerprintDatabaseStorage._sha256(destination)
        ):
            FingerprintDatabaseStorage._unlink_if_exists(destination)
            raise FingerprintDatabaseError(
                f"Fingerprint database copy verification failed: {destination}"
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _replace_with_retry(source: Path, destination: Path) -> None:
        deadline = time.monotonic() + 5.0
        while True:
            try:
                os.replace(source, destination)
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    @staticmethod
    def _fsync_file(path: Path) -> None:
        with open(path, "rb+") as file_handle:
            os.fsync(file_handle.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        try:
            directory_fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _unlink_if_exists(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
