import argparse
import asyncio
import json
from pathlib import Path

from ai_services.context_compiler import CompiledContextPacket, compile_context_packet_from_category_id
from ai_services.gemini_client import gemini_client
from ai_services.scene_pipeline import scene_pipeline
from voice.context_support import build_context_block


def _read_optional_text(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Context file not found: {resolved}")
    return resolved.read_text(encoding="utf-8").strip() or None


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run scene extraction and image generation from existing session summaries.")
    parser.add_argument("objective_summary", help="Path to the objective summary markdown/text file.")
    parser.add_argument("narrative_summary", help="Path to the narrative summary markdown/text file.")
    parser.add_argument("--output-dir", help="Directory for scene manifests, prompts, and generated images.")
    parser.add_argument("--public-context", help="Optional public context text file.")
    parser.add_argument("--session-context", help="Optional session context text file.")
    parser.add_argument("--dm-context", help="Optional DM context text file.")
    parser.add_argument("--discord-category-id", type=int, help="Optional Discord category ID to load compiled context directly from Discord.")
    parser.add_argument("--include-dm-context", action="store_true", help="Include DM context in this offline image test.")
    parser.add_argument("--ref-image", action="append", default=[], help="Optional local reference image path. Can be provided multiple times.")
    parser.add_argument("--quality", choices=["auto", "fast", "hq"], default="auto")
    parser.add_argument("--aspect-ratio", choices=["auto", "1:1", "3:4", "4:3", "9:16", "16:9"], default="auto")
    parser.add_argument("--max-scenes", type=int, help="Optional cap on the number of selected scenes.")
    parser.add_argument("--generate-images", action="store_true", help="Actually call Gemini image generation. Otherwise only scene manifests and prompts are written.")
    args = parser.parse_args()

    objective_path = Path(args.objective_summary).expanduser()
    narrative_path = Path(args.narrative_summary).expanduser()
    if not objective_path.exists():
        raise FileNotFoundError(f"Objective summary not found: {objective_path}")
    if not narrative_path.exists():
        raise FileNotFoundError(f"Narrative summary not found: {narrative_path}")

    objective_summary = objective_path.read_text(encoding="utf-8")
    narrative_summary = narrative_path.read_text(encoding="utf-8")
    public_text = _read_optional_text(args.public_context)
    session_text = _read_optional_text(args.session_context)
    dm_text = _read_optional_text(args.dm_context) if args.include_dm_context else None

    packet = (
        await compile_context_packet_from_category_id(args.discord_category_id, include_dm_context=args.include_dm_context)
        if args.discord_category_id
        else CompiledContextPacket()
    )
    if public_text:
        packet.public_text = "\n\n".join(part for part in [packet.public_text, public_text] if part)
    if session_text:
        packet.session_text = "\n\n".join(part for part in [packet.session_text, session_text] if part)
    if dm_text:
        packet.dm_text = "\n\n".join(part for part in [packet.dm_text, dm_text] if part)
    packet.text_block = build_context_block(
        public_text=packet.public_text,
        session_text=packet.session_text,
        dm_text=packet.dm_text,
    )

    output_root = Path(args.output_dir).expanduser() if args.output_dir else Path("offline_test_outputs") / "image_test"
    output_root.mkdir(parents=True, exist_ok=True)

    candidates = await scene_pipeline.extract_scene_candidates(
        objective_summary=objective_summary,
        narrative_summary=narrative_summary,
        context_packet=packet,
        max_scenes_cap=args.max_scenes,
    )
    selected_scenes, rationale = await scene_pipeline.select_final_scenes(
        candidates,
        context_packet=packet,
        max_scenes_cap=args.max_scenes,
    )

    manifest = {
        "candidate_count": len(candidates),
        "selected_count": len(selected_scenes),
        "selection_rationale": rationale,
        "selected_scenes": [scene.__dict__ for scene in selected_scenes],
    }
    (output_root / "scene_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    generated_outputs = []
    for index, scene in enumerate(selected_scenes, start=1):
        request = scene_pipeline.prepare_scene_image_request(
            scene,
            context_packet=packet,
            quality_mode=args.quality,
            aspect_ratio_override=None if args.aspect_ratio == "auto" else args.aspect_ratio,
        )
        prompt_path = output_root / f"scene_{index:02d}_prompt.txt"
        prompt_path.write_text(request.prompt, encoding="utf-8")
        output_info = {
            "scene_id": scene.scene_id,
            "title": scene.title,
            "prompt_path": str(prompt_path),
            "aspect_ratio": request.aspect_ratio,
            "model_name": request.model_name,
        }
        if args.generate_images:
            combined_reference_images = [asset for asset in request.reference_assets if asset.is_image]
            combined_reference_images.extend(Path(path).expanduser() for path in args.ref_image)
            images = gemini_client.generate_image(
                request.prompt,
                model_name=request.model_name,
                aspect_ratio=request.aspect_ratio,
                reference_images=combined_reference_images,
            )
            for image_index, image in enumerate(images, start=1):
                extension = ".png" if image["mime_type"] == "image/png" else ".jpg"
                image_path = output_root / f"scene_{index:02d}_image_{image_index:02d}{extension}"
                image_path.write_bytes(image["image_bytes"])
                output_info.setdefault("images", []).append(str(image_path))
        generated_outputs.append(output_info)

    result = {
        "output_dir": str(output_root),
        "scene_manifest_path": str(output_root / "scene_manifest.json"),
        "generated_outputs": generated_outputs,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
