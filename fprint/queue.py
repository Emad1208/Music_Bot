from __future__ import annotations

import asyncio
import os
import re
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from db_Project.db_init import db
from fingerprint.wrapper import AudfprintWrapper
from fprint.paths import FINGERPRINT_QUEUE_DIR


MAX_JOB_ATTEMPTS = 2
JOB_PATTERN = re.compile(
    r"^music-(?P<track_id>\d+)-(?P<job_id>[0-9a-f]{32})"
    r"(?P<suffix>\.[a-z0-9]{1,8})$"
)


@dataclass(frozen=True)
class FingerprintJob:
    track_id: int
    file_path: Path
    attempts: int = 0


wrapper = AudfprintWrapper()


async def save_fingerprint_safely(job: FingerprintJob) -> None:
    if db.has_music_fingerprint(job.track_id):
        return

    suffix = job.file_path.suffix.lower() or ".mp3"
    track_key = f"music-{job.track_id}{suffix}"

    await asyncio.to_thread(
        wrapper.add_or_create,
        [job.file_path],
        track_keys=[track_key],
    )

    try:
        # 🌟 Primary fix: pass correct argument names to database call
        db.save_music_fingerprint(
            track_id=job.track_id,
            track_key=track_key,
        )
    except Exception:
        try:
            await asyncio.to_thread(wrapper.remove_from_db, [track_key])
        except Exception as rollback_error:
            print("FINGERPRINT_ROLLBACK_ERROR:", repr(rollback_error))
        raise


class FingerprintJobQueue:
    def __init__(self):
        self._queue: asyncio.Queue[FingerprintJob | None] | None = None
        self._worker_task: asyncio.Task | None = None
        self._known_paths: set[Path] = set()
        self._stop_requested = False

    async def start(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return

        FINGERPRINT_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        self._queue = asyncio.Queue()
        self._known_paths.clear()
        self._stop_requested = False

        recovered_jobs = self._load_spooled_jobs()
        for job in recovered_jobs:
            self._put_job(job)

        self._worker_task = asyncio.create_task(
            self._worker(),
            name="fingerprint-queue-worker",
        )
        print(f"FINGERPRINT_QUEUE_STARTED: pending={len(recovered_jobs)}")

    async def stop(self) -> None:
        worker_task = self._worker_task
        if worker_task is None or worker_task.done():
            return

        self._stop_requested = True
        if self._queue is not None:
            self._queue.put_nowait(None)

        await worker_task
        self._worker_task = None
        self._queue = None
        self._known_paths.clear()
        print("FINGERPRINT_QUEUE_STOPPED")

    def submit(self, job: FingerprintJob) -> None:
        if self._stop_requested:
            print("FINGERPRINT_QUEUE_STOPPING: job preserved", job.file_path)
            return

        if self._queue is None:
            self._queue = asyncio.Queue()

        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(
                self._worker(),
                name="fingerprint-queue-worker",
            )

        self._put_job(job)
        print(
            "FINGERPRINT_QUEUED:",
            f"track_id={job.track_id}",
            f"pending={self._queue.qsize()}",
        )

    def _put_job(self, job: FingerprintJob) -> None:
        normalized_path = job.file_path.resolve()
        if normalized_path in self._known_paths:
            return

        self._known_paths.add(normalized_path)
        self._queue.put_nowait(
            FingerprintJob(
                track_id=job.track_id,
                file_path=normalized_path,
                attempts=job.attempts,
            )
        )

    def _load_spooled_jobs(self) -> list[FingerprintJob]:
        jobs = []
        for file_path in sorted(
            FINGERPRINT_QUEUE_DIR.iterdir(),
            key=lambda path: path.stat().st_mtime_ns,
        ):
            if not file_path.is_file():
                continue

            match = JOB_PATTERN.fullmatch(file_path.name)
            if not match:
                continue

            track_id = int(match.group("track_id"))
            if db.has_music_fingerprint(track_id):
                try:
                    file_path.unlink()
                except OSError as error:
                    print("FINGERPRINT_SPOOL_CLEANUP_ERROR:", repr(error))
                continue

            jobs.append(FingerprintJob(track_id, file_path))

        return jobs

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            if job is None:
                self._queue.task_done()
                return

            succeeded = False
            retry_job = None
            try:
                print(
                    "FINGERPRINT_JOB_STARTED:",
                    f"track_id={job.track_id}",
                    f"attempt={job.attempts + 1}",
                )
                await save_fingerprint_safely(job)
                succeeded = True
                print("FINGERPRINT_JOB_DONE:", f"track_id={job.track_id}")
            except Exception as error:
                print(
                    "FINGERPRINT_JOB_ERROR:",
                    f"track_id={job.track_id}",
                    repr(error),
                )
                if job.attempts + 1 < MAX_JOB_ATTEMPTS:
                    retry_job = replace(job, attempts=job.attempts + 1)
            finally:
                self._known_paths.discard(job.file_path.resolve())
                self._queue.task_done()

            if succeeded:
                try:
                    job.file_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as error:
                    print("FINGERPRINT_JOB_CLEANUP_ERROR:", repr(error))
            elif retry_job is not None and not self._stop_requested:
                self._put_job(retry_job)
            else:
                print(
                    "FINGERPRINT_JOB_PRESERVED:",
                    f"track_id={job.track_id}",
                    str(job.file_path),
                )

            if self._stop_requested:
                return


def stage_fingerprint_job(
    track_id: int,
    file_path: str | Path,
) -> FingerprintJob | None:
    if db.has_music_fingerprint(track_id):
        return None

    source_path = Path(file_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    suffix = source_path.suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".mp3"

    FINGERPRINT_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    staged_path = FINGERPRINT_QUEUE_DIR / (
        f"music-{track_id}-{uuid.uuid4().hex}{suffix}"
    )
    os.replace(source_path, staged_path)
    return FingerprintJob(track_id=track_id, file_path=staged_path.resolve())


fingerprint_job_queue = FingerprintJobQueue()


async def start_fingerprint_queue() -> None:
    await fingerprint_job_queue.start()


async def stop_fingerprint_queue() -> None:
    await fingerprint_job_queue.stop()


def submit_fingerprint_job(job: FingerprintJob) -> None:
    fingerprint_job_queue.submit(job)