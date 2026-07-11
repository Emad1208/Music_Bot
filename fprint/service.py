import asyncio
import os
import uuid
from pathlib import Path

from db_Project.db_init import db
from fingerprint.wrapper import AudfprintWrapper
from fprint.converter import preprocess_sample
from fprint.paths import BASE_DIR


SAMPLE_DIR = BASE_DIR / "temp" / "fingerprint_samples"
wrapper = AudfprintWrapper()


def get_audio_file_id(message):
    if getattr(message, "voice", None):
        return message.voice.id, message.voice.mime_type

    if getattr(message, "audio", None):
        return message.audio.id, message.audio.mime_type

    document = getattr(message, "document", None)
    if document and getattr(document, "mime_type", None):
        if document.mime_type.startswith("audio"):
            return document.id, document.mime_type

    return None, None


def get_audio_suffix(mime_type):
    suffixes = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mp4": ".m4a",
    }

    return suffixes.get(mime_type, ".mp3")


def save_sample_file(file_bytes, mime_type):
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    sample_path = SAMPLE_DIR / f"{uuid.uuid4()}{get_audio_suffix(mime_type)}"

    with open(sample_path, "wb") as sample_file:
        sample_file.write(file_bytes)

    return sample_path


def get_music_value(music, key, index):
    try:
        return music[key]
    except (IndexError, KeyError, TypeError):
        return music[index]


async def identify_sample(sample_path):
    return await asyncio.to_thread(wrapper.identify, sample_path)


async def identify_message_audio(message, bot):
    file_id, mime_type = get_audio_file_id(message)

    if not file_id:
        return {
            "found": False,
            "status": "no_audio",
        }

    sample_path = None
    processed_path = None

    try:
        file_bytes = await bot.download(file_id)
        sample_path = save_sample_file(file_bytes, mime_type)

        result = await identify_sample(sample_path)

        if not result.get("found"):
            processed_path = await asyncio.to_thread(preprocess_sample, sample_path)
            processed_result = await identify_sample(processed_path)

            if processed_result.get("found"):
                processed_result["preprocessed"] = True
                result = processed_result

        if not result.get("found"):
            return {
                "found": False,
                "status": "not_found",
                "result": result,
            }

        track_key = result["track_name"]
        music = db.get_music_by_track_key(track_key)

        if not music:
            return {
                "found": False,
                "status": "music_not_in_db",
                "track_key": track_key,
                "result": result,
            }

        return {
            "found": True,
            "status": "found",
            "music": music,
            "file_id": get_music_value(music, "file_id", 3),
            "title": get_music_value(music, "title", 1),
            "quality": get_music_value(music, "quality", 2),
            "track_key": track_key,
            "result": result,
        }

    except Exception as e:
        error = repr(e)

        if "ffmpeg not found" in error:
            return {
                "found": False,
                "status": "ffmpeg_missing",
                "error": error,
            }

        return {
            "found": False,
            "status": "error",
            "error": error,
        }

    finally:
        if processed_path and Path(processed_path).exists():
            os.remove(processed_path)

        if sample_path and Path(sample_path).exists():
            os.remove(sample_path)
