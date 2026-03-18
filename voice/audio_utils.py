import subprocess
from pathlib import Path

from config import (
    AUDIO_BITRATE,
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    FFMPEG_INPUT_DEVICE,
    FFMPEG_INPUT_FORMAT,
)


def get_category_id_voice(voice_channel):
    if voice_channel and voice_channel.category:
        return voice_channel.category.id
    return None


def build_ffmpeg_command(audio_filename: Path, duration: int) -> list[str]:
    if not FFMPEG_INPUT_FORMAT or not FFMPEG_INPUT_DEVICE:
        raise RuntimeError(
            "FFmpeg input source is not configured for this platform. "
            "Set FFMPEG_INPUT_FORMAT and FFMPEG_INPUT_DEVICE in .env."
        )
    return [
        "ffmpeg",
        "-f",
        FFMPEG_INPUT_FORMAT,
        "-i",
        FFMPEG_INPUT_DEVICE,
        "-t",
        str(duration),
        "-acodec",
        "libmp3lame",
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-ac",
        str(AUDIO_CHANNELS),
        "-b:a",
        AUDIO_BITRATE,
        str(audio_filename),
    ]


def probe_audio_duration(audio_file: Path, fallback_duration: int) -> int:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_file),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return max(1, int(round(float(result.stdout.strip()))))
    except Exception:
        return fallback_duration


def split_audio_file_for_offline(audio_file: Path, output_dir: Path, segment_seconds: int) -> list[Path]:
    duration = probe_audio_duration(audio_file, segment_seconds)
    if duration <= segment_seconds:
        return [audio_file]

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = audio_file.suffix or ".mp3"
    output_pattern = output_dir / f"{audio_file.stem}_part_%03d{suffix}"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(audio_file),
                "-f",
                "segment",
                "-segment_time",
                str(segment_seconds),
                "-reset_timestamps",
                "1",
                "-c",
                "copy",
                str(output_pattern),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return [audio_file]

    segment_paths = sorted(output_dir.glob(f"{audio_file.stem}_part_*{suffix}"))
    return segment_paths or [audio_file]
