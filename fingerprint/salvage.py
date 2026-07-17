from __future__ import annotations

import gc
import os
import sqlite3
import struct
import sys
import time
import uuid
from pathlib import Path

import numpy as np

from fingerprint.storage import (
    FingerprintDatabaseCorruptError,
    FingerprintDatabaseStorage,
)


BASE_DIR = Path(__file__).resolve().parent.parent
AUDFPRINT_DIR = BASE_DIR / "audfprint"
PICKLE_PREFIX_SIZE = 512
UINT32_SIZE = np.dtype(np.uint32).itemsize


def salvage_truncated_hash_table(
    db_path: str | Path,
    sqlite_path: str | Path,
    semantic_validator,
    *,
    promote: bool = False,
    infer_missing_mappings: bool = False,
) -> dict[str, str | int | None]:
    db_path = Path(db_path).resolve()
    sqlite_path = Path(sqlite_path).resolve()
    storage = FingerprintDatabaseStorage(db_path)
    raw_table_path = db_path.parent / f".{db_path.stem}.table.{uuid.uuid4().hex}.bin"
    salvaged_path = db_path.with_name(f"{db_path.stem}.salvaged{db_path.suffix}")

    try:
        metadata = _extract_partial_table(storage, db_path, raw_table_path)
        max_track_id = _find_max_track_id(raw_table_path, metadata)
        track_keys, inferred_mappings = _load_track_keys(
            sqlite_path,
            required_count=max_track_id,
            allow_inference=infer_missing_mappings,
        )
        stats = _build_hash_table(
            raw_table_path,
            salvaged_path,
            track_keys,
            metadata,
        )

        quarantine_path = None
        if promote:
            quarantine_path = storage.promote_replacement(
                salvaged_path,
                semantic_validator,
            )
            _save_inferred_mappings(sqlite_path, inferred_mappings)
        else:
            storage.validate_gzip(salvaged_path)
            semantic_validator(salvaged_path)

        return {
            "database": str(db_path),
            "salvaged": str(salvaged_path),
            "quarantine": str(quarantine_path) if quarantine_path else None,
            "inferred_mappings": len(inferred_mappings),
            **metadata,
            **stats,
        }
    finally:
        _unlink_with_retry(raw_table_path)


def _unlink_with_retry(path: Path) -> None:
    gc.collect()
    deadline = time.monotonic() + 5.0
    while True:
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                return
            gc.collect()
            time.sleep(0.1)


def _extract_partial_table(
    storage: FingerprintDatabaseStorage,
    db_path: Path,
    raw_table_path: Path,
) -> dict[str, int]:
    prefix = bytearray()
    table_start = None
    table_size = None
    table_written = 0

    with open(raw_table_path, "wb+") as table_output:
        for chunk in storage.iter_decompressed_ignoring_trailer(db_path):
            if table_start is None:
                prefix.extend(chunk)
                if len(prefix) < PICKLE_PREFIX_SIZE:
                    continue

                hashbits = _read_pickle_binint1(prefix, b"hashbits")
                depth = _read_pickle_binint1(prefix, b"depth")
                maxtimebits = _read_pickle_binint1(prefix, b"maxtimebits")
                table_start, table_size = _find_table_payload(prefix)

                expected_size = (1 << hashbits) * depth * UINT32_SIZE
                if table_size != expected_size:
                    raise FingerprintDatabaseCorruptError(
                        f"Unexpected hash table size: {table_size} != {expected_size}"
                    )

                available = prefix[table_start : table_start + table_size]
                table_output.write(available)
                table_written += len(available)
                prefix.clear()
                continue

            remaining = table_size - table_written
            if remaining > 0:
                data = chunk[:remaining]
                table_output.write(data)
                table_written += len(data)

        if table_start is None or table_size is None:
            raise FingerprintDatabaseCorruptError(
                "Could not locate the NumPy table inside the damaged pickle"
            )
        if table_written == 0 or table_written > table_size:
            raise FingerprintDatabaseCorruptError("Invalid recovered table length")

        missing_bytes = table_size - table_written
        table_output.truncate(table_size)
        table_output.flush()
        os.fsync(table_output.fileno())

    return {
        "hashbits": hashbits,
        "depth": depth,
        "maxtimebits": maxtimebits,
        "table_bytes": table_size,
        "recovered_table_bytes": table_written,
        "missing_table_bytes": missing_bytes,
    }


def _read_pickle_binint1(prefix: bytes, key: bytes) -> int:
    marker = bytes((0x8C, len(key))) + key + bytes((0x94, 0x4B))
    position = prefix.find(marker)
    if position < 0:
        raise FingerprintDatabaseCorruptError(
            f"Could not read {key.decode('ascii')} from pickle header"
        )
    return prefix[position + len(marker)]


def _find_table_payload(prefix: bytes) -> tuple[int, int]:
    table_marker = b"\x8c\x05table\x94"
    table_position = prefix.find(table_marker)
    bytearray_position = prefix.find(b"\x96", table_position + len(table_marker))
    if table_position < 0 or bytearray_position < 0:
        raise FingerprintDatabaseCorruptError(
            "Could not locate the table bytearray in pickle header"
        )

    size_start = bytearray_position + 1
    size_end = size_start + 8
    return size_end, struct.unpack("<Q", prefix[size_start:size_end])[0]


def _find_max_track_id(
    raw_table_path: Path,
    metadata: dict[str, int],
) -> int:
    table_map = np.memmap(
        raw_table_path,
        dtype=np.uint32,
        mode="r",
        shape=(1 << metadata["hashbits"], metadata["depth"]),
    )
    try:
        max_track_id = 0
        rows_per_chunk = 4096
        for start in range(0, table_map.shape[0], rows_per_chunk):
            end = min(start + rows_per_chunk, table_map.shape[0])
            block = table_map[start:end]
            if np.any(block):
                max_track_id = max(
                    max_track_id,
                    int((block >> metadata["maxtimebits"]).max()),
                )
        return max_track_id
    finally:
        del table_map
        gc.collect()


def _load_track_keys(
    sqlite_path: Path,
    *,
    required_count: int,
    allow_inference: bool,
) -> tuple[list[str], list[tuple[int, str]]]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(sqlite_path)

    with sqlite3.connect(sqlite_path) as connection:
        rows = connection.execute("""
            SELECT music_id, track_key
            FROM music_fingerprints
            WHERE engine = 'audfprint'
            ORDER BY id
        """).fetchall()

        track_keys = [row[1] for row in rows]
        missing_count = required_count - len(track_keys)
        if missing_count < 0:
            raise FingerprintDatabaseCorruptError(
                "SQLite contains more fingerprint mappings than the hash table"
            )

        inferred_mappings: list[tuple[int, str]] = []
        if missing_count:
            if not allow_inference:
                raise FingerprintDatabaseCorruptError(
                    f"Hash table has {missing_count} IDs without SQLite mappings. "
                    "Re-run with explicit mapping inference only after verifying order."
                )

            last_mapped_music_id = max(row[0] for row in rows)
            candidates = connection.execute("""
                SELECT m.id
                FROM musics m
                LEFT JOIN music_fingerprints f
                    ON f.music_id = m.id
                    AND f.engine = 'audfprint'
                WHERE m.id > ?
                AND f.id IS NULL
                ORDER BY m.id
                LIMIT ?
            """, (last_mapped_music_id, missing_count)).fetchall()

            if len(candidates) != missing_count:
                raise FingerprintDatabaseCorruptError(
                    "Could not infer all missing fingerprint mappings from SQLite"
                )

            inferred_mappings = [
                (row[0], f"music-{row[0]}.mp3")
                for row in candidates
            ]
            track_keys.extend(track_key for _, track_key in inferred_mappings)

    if not track_keys or len(set(track_keys)) != len(track_keys):
        raise FingerprintDatabaseCorruptError(
            "SQLite fingerprint keys are missing or duplicated"
        )
    return track_keys, inferred_mappings


def _save_inferred_mappings(
    sqlite_path: Path,
    inferred_mappings: list[tuple[int, str]],
) -> None:
    if not inferred_mappings:
        return

    with sqlite3.connect(sqlite_path, timeout=30) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany("""
            INSERT INTO music_fingerprints (
                music_id,
                engine,
                track_key
            )
            VALUES (?, 'audfprint', ?)
            ON CONFLICT(music_id, engine) DO UPDATE SET
                track_key = excluded.track_key
        """, inferred_mappings)


def _build_hash_table(
    raw_table_path: Path,
    salvaged_path: Path,
    track_keys: list[str],
    metadata: dict[str, int],
) -> dict[str, int]:
    if str(AUDFPRINT_DIR) not in sys.path:
        sys.path.insert(0, str(AUDFPRINT_DIR))
    import hash_table

    row_count = 1 << metadata["hashbits"]
    depth = metadata["depth"]
    maxtimebits = metadata["maxtimebits"]
    table_map = np.memmap(
        raw_table_path,
        dtype=np.uint32,
        mode="r+",
        shape=(row_count, depth),
    )
    try:
        table = np.asarray(table_map)
        counts = np.zeros(row_count, dtype=np.int32)
        id_hash_counts = np.zeros(len(track_keys) + 1, dtype=np.uint64)
        max_track_id = 0
        discarded_invalid_entries = 0

        rows_per_chunk = 4096
        for start in range(0, row_count, rows_per_chunk):
            end = min(start + rows_per_chunk, row_count)
            block = table[start:end]
            encoded_ids = block >> maxtimebits
            valid_entries = (encoded_ids > 0) & (encoded_ids <= len(track_keys))
            invalid_entries = (block != 0) & ~valid_entries
            if np.any(invalid_entries):
                discarded_invalid_entries += int(np.count_nonzero(invalid_entries))
                affected_rows = np.nonzero(np.any(invalid_entries, axis=1))[0]
                for row_index in affected_rows:
                    row = block[row_index]
                    row_ids = row >> maxtimebits
                    valid_values = row[
                        (row_ids > 0) & (row_ids <= len(track_keys))
                    ].copy()
                    row.fill(0)
                    row[: len(valid_values)] = valid_values

                encoded_ids = block >> maxtimebits

            counts[start:end] = np.count_nonzero(block, axis=1).astype(np.int32)
            present_ids = encoded_ids[encoded_ids != 0].astype(np.int64, copy=False)
            if present_ids.size:
                block_max_id = int(present_ids.max())
                max_track_id = max(max_track_id, block_max_id)
                if block_max_id > len(track_keys):
                    raise FingerprintDatabaseCorruptError(
                        "Hash table contains more track IDs than SQLite"
                    )
                id_hash_counts += np.bincount(
                    present_ids,
                    minlength=len(track_keys) + 1,
                )[: len(track_keys) + 1].astype(np.uint64)

        if max_track_id != len(track_keys):
            raise FingerprintDatabaseCorruptError(
                "SQLite track count does not match IDs recovered from hash table: "
                f"{len(track_keys)} != {max_track_id}"
            )

        recovered = object.__new__(hash_table.HashTable)
        recovered.hashbits = metadata["hashbits"]
        recovered.depth = depth
        recovered.maxtimebits = maxtimebits
        recovered.table = table
        recovered.counts = counts
        recovered.names = list(track_keys)
        recovered.hashesperid = id_hash_counts[1:].astype(np.uint32)
        recovered.params = {"samplerate": 11025}
        recovered.ht_version = hash_table.HT_VERSION
        recovered.dirty = True
        recovered.save(str(salvaged_path))

        total_hashes = int(counts.sum())
        del recovered.table
        del recovered
        del table
        table_map.flush()
    finally:
        mmap_handle = getattr(table_map, "_mmap", None)
        if mmap_handle is not None:
            mmap_handle.close()
        del table_map
        gc.collect()

    return {
        "tracks": len(track_keys),
        "stored_hashes": total_hashes,
        "discarded_invalid_entries": discarded_invalid_entries,
    }
