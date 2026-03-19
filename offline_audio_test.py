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
        "--discord-category-id",
        type=int,
        help="Optional Discord category ID to load compiled context directly from Discord.",
    )
    parser.add_argument(
        "--include-dm-context",
        action="store_true",
        help="Allow DM-private context to be included in this offline test run.",
    )
    parser.add_argument(
        "--generate-images",
        action="store_true",
        help="After transcript and summaries are generated, also run the image pipeline.",
    )
    parser.add_argument(
        "--image-quality",
        choices=["auto", "fast", "hq"],
        default="auto",
        help="Quality mode for offline image generation.",
    )
    parser.add_argument(
        "--image-aspect-ratio",
        choices=["auto", "1:1", "3:4", "4:3", "9:16", "16:9"],
        default="auto",
        help="Override image aspect ratio. Auto lets the scene decide.",
    )
    parser.add_argument(
        "--image-max-scenes",
        type=int,
        help="Optional cap on how many scenes can be selected for offline image generation.",
    )
    parser.add_argument(
        "--image-ref",
        action="append",
        default=[],
        help="Optional local image reference path for offline image generation. Can be supplied multiple times.",
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
        discord_category_id=args.discord_category_id,
        generate_images=args.generate_images,
        image_quality=args.image_quality,
        image_aspect_ratio=None if args.image_aspect_ratio == "auto" else args.image_aspect_ratio,
        image_max_scenes=args.image_max_scenes,
        image_reference_paths=args.image_ref,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
