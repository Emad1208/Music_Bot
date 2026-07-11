import shutil
import subprocess
import uuid
from pathlib import Path


def preprocess_sample(input_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = input_path.with_name(f"{input_path.stem}_clean_{uuid.uuid4()}.wav")

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg and make sure it is available in PATH."
        )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "11025",
        "-af",
        "highpass=f=80,lowpass=f=5000,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11",
        str(output_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg preprocess error:\n{result.stderr}")

    return output_path
