from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

FINGERPRINT_DB_DIR = BASE_DIR / "data" / "fingerprint_db"
FINGERPRINT_DB_PATH = FINGERPRINT_DB_DIR / "music_fingerprints.pklz"
FINGERPRINT_QUEUE_DIR = BASE_DIR / "temp" / "fingerprint_queue"

TEST_TRACKS_DIR = BASE_DIR / "data" / "fingerprint"
TEST_SAMPLES_DIR = BASE_DIR / "data" / "samples"
