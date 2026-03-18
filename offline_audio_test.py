import argparse
import asyncio
import json
from pathlib import Path

from voice.transcription import VoiceRecorder


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
    parser.add_argument(
        "--public-context",
        help="Optional path to public evergreen context used for names, spelling, and stable campaign facts.",
    )
    parser.add_argument(
        "--session-context",
        help="Optional path to temporary session-only context for this run.",
    )
    parser.add_argument(
        "--dm-context",
        help="Optional path to DM-private context. Ignored unless --include-dm-context is set.",
    )
    parser.add_argument(
        "--include-dm-context",
        action="store_true",
        help="Allow DM-private context to be included in this offline test run.",
    )
    args = parser.parse_args()

    recorder = VoiceRecorder()
    result = await recorder.process_existing_audio_files(
        args.audio_files,
        args.output_dir,
        public_context_path=args.public_context,
        session_context_path=args.session_context,
        dm_context_path=args.dm_context,
        include_dm_context=args.include_dm_context,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
