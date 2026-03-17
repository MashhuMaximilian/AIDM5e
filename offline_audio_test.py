import argparse
import asyncio
import json
from pathlib import Path

from transcription import VoiceRecorder


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the transcript + audio-summary pipeline on existing audio files."
    )
    parser.add_argument(
        "audio_files",
        nargs="+",
        help="Absolute or relative paths to audio files. Multiple files are processed in order.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for generated transcript/summary artifacts. Defaults to offline_test_outputs/ in the repo.",
    )
    args = parser.parse_args()

    recorder = VoiceRecorder()
    result = await recorder.process_existing_audio_files(args.audio_files, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
