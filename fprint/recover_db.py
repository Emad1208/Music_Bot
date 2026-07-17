from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fingerprint.wrapper import AudfprintWrapper
from fingerprint.salvage import salvage_truncated_hash_table
from fprint.paths import FINGERPRINT_DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recover an audfprint gzip database without overwriting the source."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=FINGERPRINT_DB_PATH,
        help="Path to the damaged .pklz database.",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Replace the active database after validation and quarantine the damaged file.",
    )
    parser.add_argument(
        "--salvage-table",
        action="store_true",
        help="Rebuild a pickle truncated inside its NumPy hash table.",
    )
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=BASE_DIR / "db_music_Bot.db",
        help="SQLite database containing music_fingerprints track keys.",
    )
    parser.add_argument(
        "--infer-missing-mappings",
        action="store_true",
        help="Map extra hash IDs to consecutive unmapped music rows after manual verification.",
    )
    args = parser.parse_args()

    wrapper = AudfprintWrapper(args.db)
    if args.salvage_table:
        result = salvage_truncated_hash_table(
            args.db,
            args.sqlite_db,
            wrapper._semantic_validate,
            promote=args.promote,
            infer_missing_mappings=args.infer_missing_mappings,
        )
    else:
        result = wrapper.recover_database(promote=args.promote)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
