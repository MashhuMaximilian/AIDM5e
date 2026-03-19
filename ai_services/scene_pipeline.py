import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

from ai_services.context_compiler import CompiledContextPacket, ContextAsset, ManagedContextEntry
from ai_services.gemini_client import gemini_client
from config import GEMINI_IMAGE_DEFAULT_ASPECT_RATIO, GEMINI_IMAGE_HQ_MODEL, GEMINI_IMAGE_MODEL
from prompts.image_prompts import (
    BASE_DND_STYLE_BLOCK,
    build_direct_image_brief_prompt,
    build_scene_extraction_prompt,
    build_scene_selection_prompt,
)


logger = logging.getLogger(__name__)
SUPPORTED_ASPECT_RATIOS = {"1:1", "3:4", "4:3", "9:16", "16:9"}
IMAGE_REFERENCE_LIMIT = 6


@dataclass
class SceneCandidate:
    scene_id: str
    title: str
    why_it_matters: str
    visual_distinctiveness: str
    moment_type: str
    subject_focus: str
    location: str
    scene_core: str
    must_include: list[str]
    avoid: list[str]
    lighting_mood: str
    composition: str
    style_additions: list[str]
    priority_reason: str
    aspect_ratio_suggestion: str


@dataclass
class DirectImageBrief:
    title: str
    subject_focus: str
    scene_core: str
    location: str
    must_include: list[str]
    avoid: list[str]
    lighting_mood: str
    composition: str
    style_additions: list[str]
    aspect_ratio_suggestion: str


@dataclass
class PreparedImageRequest:
    title: str
    prompt: str
    aspect_ratio: str
    reference_assets: list[ContextAsset]
    quality_mode: str
    model_name: str


class ScenePipeline:
    def _extract_json_payload(self, raw_text: str) -> Any:
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("Model returned empty text where JSON was expected.")

        fenced = text
        if fenced.startswith("```"):
            fenced = fenced.split("\n", 1)[1] if "\n" in fenced else fenced
            if fenced.endswith("```"):
                fenced = fenced[:-3]
            fenced = fenced.strip()
            if fenced.lower().startswith("json"):
                fenced = fenced[4:].strip()
        for candidate in (fenced, text):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        start = min([idx for idx in (text.find("{"), text.find("[")) if idx != -1], default=-1)
        end_object = text.rfind("}")
        end_array = text.rfind("]")
        end = max(end_object, end_array)
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise ValueError(f"Could not parse JSON payload from model output: {text[:400]}")

    def _normalize_aspect_ratio(self, value: str | None) -> str:
        cleaned = (value or "").strip()
        if cleaned in SUPPORTED_ASPECT_RATIOS:
            return cleaned
        return GEMINI_IMAGE_DEFAULT_ASPECT_RATIO if GEMINI_IMAGE_DEFAULT_ASPECT_RATIO in SUPPORTED_ASPECT_RATIOS else "4:3"

    def _extract_campaign_style_shift(self, packet: CompiledContextPacket | None) -> str | None:
        if packet is None:
            return None

        collected: list[str] = []
        for entry in [*packet.public_entries, *packet.session_entries, *packet.dm_entries]:
            tags = {tag.lower() for tag in entry.tags}
            text = entry.text.strip()
            if not text:
                continue
            if "style" in tags or "visual-reference" in tags:
                collected.append(text)
                continue
            lowered = text.lower()
            if any(marker in lowered for marker in ("art style", "style shift", "visual style", "tone and style")):
                collected.append(text)
        if not collected:
            text_block = packet.text_block or ""
            style_lines = [
                line.strip()
                for line in text_block.splitlines()
                if "style" in line.lower() or "visual" in line.lower() or "look" in line.lower()
            ]
            collected.extend(style_lines)
        if not collected:
            return None
        return "\n\n".join(collected)

    def _normalize_scene(self, payload: dict[str, Any], fallback_index: int) -> SceneCandidate:
        return SceneCandidate(
            scene_id=str(payload.get("scene_id") or f"scene_{fallback_index:02d}"),
            title=str(payload.get("title") or f"Scene {fallback_index}"),
            why_it_matters=str(payload.get("why_it_matters") or ""),
            visual_distinctiveness=str(payload.get("visual_distinctiveness") or ""),
            moment_type=str(payload.get("moment_type") or "other"),
            subject_focus=str(payload.get("subject_focus") or "mixed"),
            location=str(payload.get("location") or ""),
            scene_core=str(payload.get("scene_core") or ""),
            must_include=[str(item) for item in payload.get("must_include", []) if str(item).strip()],
            avoid=[str(item) for item in payload.get("avoid", []) if str(item).strip()],
            lighting_mood=str(payload.get("lighting_mood") or ""),
            composition=str(payload.get("composition") or ""),
            style_additions=[str(item) for item in payload.get("style_additions", []) if str(item).strip()],
            priority_reason=str(payload.get("priority_reason") or ""),
            aspect_ratio_suggestion=self._normalize_aspect_ratio(payload.get("aspect_ratio_suggestion")),
        )

    def _normalize_direct_brief(self, payload: dict[str, Any]) -> DirectImageBrief:
        return DirectImageBrief(
            title=str(payload.get("title") or "Generated Scene"),
            subject_focus=str(payload.get("subject_focus") or "mixed"),
            scene_core=str(payload.get("scene_core") or ""),
            location=str(payload.get("location") or ""),
            must_include=[str(item) for item in payload.get("must_include", []) if str(item).strip()],
            avoid=[str(item) for item in payload.get("avoid", []) if str(item).strip()],
            lighting_mood=str(payload.get("lighting_mood") or ""),
            composition=str(payload.get("composition") or ""),
            style_additions=[str(item) for item in payload.get("style_additions", []) if str(item).strip()],
            aspect_ratio_suggestion=self._normalize_aspect_ratio(payload.get("aspect_ratio_suggestion")),
        )

    def _pick_reference_assets(self, packet: CompiledContextPacket | None) -> list[ContextAsset]:
        if packet is None:
            return []
        preferred_entries: list[ManagedContextEntry] = []
        fallback_entries: list[ManagedContextEntry] = []
        for entry in [*packet.public_entries, *packet.session_entries, *packet.dm_entries]:
            if not entry.assets:
                continue
            fallback_entries.append(entry)
            tags = {tag.lower() for tag in entry.tags}
            if tags & {"style", "visual-reference", "character", "location", "scene"}:
                preferred_entries.append(entry)

        chosen_entries = preferred_entries or fallback_entries
        assets: list[ContextAsset] = []
        seen: set[tuple[str, int | None]] = set()
        for entry in chosen_entries:
            for asset in entry.assets:
                if not asset.is_image:
                    continue
                key = (asset.url, asset.source_message_id)
                if key in seen:
                    continue
                seen.add(key)
                assets.append(asset)
                if len(assets) >= IMAGE_REFERENCE_LIMIT:
                    return assets
        return assets

    def _build_final_prompt(
        self,
        *,
        title: str,
        scene_core: str,
        subject_focus: str,
        location: str,
        must_include: list[str],
        avoid: list[str],
        lighting_mood: str,
        composition: str,
        style_additions: list[str],
        campaign_style_shift: str | None,
        directives: str | None = None,
    ) -> str:
        lines = [
            BASE_DND_STYLE_BLOCK,
            f"Scene title: {title}",
            f"Scene core: {scene_core}",
            f"Subject focus: {subject_focus or 'Not specified'}",
            f"Location: {location or 'Not specified'}",
            f"Lighting and mood: {lighting_mood or 'Use the scene core to infer mood.'}",
            f"Composition: {composition or 'Choose the clearest cinematic composition for the described scene.'}",
        ]
        if campaign_style_shift:
            lines.append(f"Campaign style shift: {campaign_style_shift}")
        if must_include:
            lines.append("Must include: " + "; ".join(must_include))
        if avoid:
            lines.append("Avoid: " + "; ".join(avoid))
        if style_additions:
            lines.append("Scene-specific style additions: " + "; ".join(style_additions))
        if directives:
            lines.append(f"Extra directives: {directives}")
        lines.append(
            "Generate a polished fantasy illustration prompt that follows the house style, preserves the described visual facts, and does not add unrelated modern or sci-fi elements."
        )
        return "\n\n".join(line for line in lines if line)

    def choose_quality_model(self, *, quality_mode: str, reference_assets: list[ContextAsset], subject_focus: str, moment_type: str, directives: str | None = None) -> str:
        normalized = (quality_mode or "auto").lower()
        if normalized == "fast":
            return GEMINI_IMAGE_MODEL
        if normalized == "hq":
            return GEMINI_IMAGE_HQ_MODEL

        complexity_markers = 0
        if len(reference_assets) >= 2:
            complexity_markers += 1
        lowered_focus = subject_focus.lower()
        if any(token in lowered_focus for token in ("several", "mixed", "group")):
            complexity_markers += 1
        if moment_type.lower() in {"combat", "revelation", "ritual", "mystery"}:
            complexity_markers += 1
        if directives and any(token in directives.lower() for token in ("cover", "hero", "poster", "perfectly match", "exactly")):
            complexity_markers += 1
        return GEMINI_IMAGE_HQ_MODEL if complexity_markers >= 2 else GEMINI_IMAGE_MODEL

    def _entries_text(self, packet: CompiledContextPacket | None) -> str | None:
        if packet is None:
            return None
        return packet.text_block

    async def extract_scene_candidates(
        self,
        *,
        objective_summary: str,
        narrative_summary: str,
        context_packet: CompiledContextPacket | None,
        max_scenes_cap: int | None = None,
    ) -> list[SceneCandidate]:
        prompt = build_scene_extraction_prompt(
            objective_summary=objective_summary,
            narrative_summary=narrative_summary,
            context_text=self._entries_text(context_packet),
            campaign_style_shift=self._extract_campaign_style_shift(context_packet),
            max_scenes_cap=max_scenes_cap,
        )
        raw = gemini_client.generate_summary_text(prompt)
        payload = self._extract_json_payload(raw)
        scenes = payload.get("scenes", []) if isinstance(payload, dict) else []
        if not isinstance(scenes, list):
            raise ValueError("Scene extraction did not return a list of scenes.")
        normalized = [self._normalize_scene(scene, index + 1) for index, scene in enumerate(scenes) if isinstance(scene, dict)]
        return normalized

    async def select_final_scenes(
        self,
        candidates: list[SceneCandidate],
        *,
        context_packet: CompiledContextPacket | None,
        max_scenes_cap: int | None = None,
    ) -> tuple[list[SceneCandidate], str | None]:
        if not candidates:
            return [], None
        prompt = build_scene_selection_prompt(
            scene_payload_json=json.dumps({"scenes": [asdict(scene) for scene in candidates]}, ensure_ascii=False, indent=2),
            context_text=self._entries_text(context_packet),
            max_scenes_cap=max_scenes_cap,
        )
        raw = gemini_client.generate_summary_text(prompt)
        payload = self._extract_json_payload(raw)
        selected_ids = payload.get("selected_scene_ids", []) if isinstance(payload, dict) else []
        rationale = payload.get("selection_rationale") if isinstance(payload, dict) else None
        if not isinstance(selected_ids, list):
            selected_ids = []
        wanted = {str(scene_id) for scene_id in selected_ids}
        selected = [scene for scene in candidates if scene.scene_id in wanted]
        if not selected:
            selected = candidates[:1]
        return selected, rationale

    async def build_direct_image_brief(
        self,
        *,
        source_material: str,
        directives: str | None,
        context_packet: CompiledContextPacket | None,
    ) -> DirectImageBrief:
        prompt = build_direct_image_brief_prompt(
            source_material=source_material,
            directives=directives,
            context_text=self._entries_text(context_packet),
            campaign_style_shift=self._extract_campaign_style_shift(context_packet),
        )
        raw = gemini_client.generate_summary_text(prompt)
        payload = self._extract_json_payload(raw)
        if not isinstance(payload, dict):
            raise ValueError("Direct image brief did not return an object.")
        return self._normalize_direct_brief(payload)

    def prepare_scene_image_request(
        self,
        scene: SceneCandidate,
        *,
        context_packet: CompiledContextPacket | None,
        quality_mode: str,
        directives: str | None = None,
        aspect_ratio_override: str | None = None,
    ) -> PreparedImageRequest:
        reference_assets = self._pick_reference_assets(context_packet)
        model_name = self.choose_quality_model(
            quality_mode=quality_mode,
            reference_assets=reference_assets,
            subject_focus=scene.subject_focus,
            moment_type=scene.moment_type,
            directives=directives,
        )
        aspect_ratio = self._normalize_aspect_ratio(aspect_ratio_override or scene.aspect_ratio_suggestion)
        prompt = self._build_final_prompt(
            title=scene.title,
            scene_core=scene.scene_core,
            subject_focus=scene.subject_focus,
            location=scene.location,
            must_include=scene.must_include,
            avoid=scene.avoid,
            lighting_mood=scene.lighting_mood,
            composition=scene.composition,
            style_additions=scene.style_additions,
            campaign_style_shift=self._extract_campaign_style_shift(context_packet),
            directives=directives,
        )
        return PreparedImageRequest(
            title=scene.title,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            reference_assets=reference_assets,
            quality_mode=quality_mode,
            model_name=model_name,
        )

    def prepare_direct_image_request(
        self,
        brief: DirectImageBrief,
        *,
        context_packet: CompiledContextPacket | None,
        quality_mode: str,
        directives: str | None = None,
        aspect_ratio_override: str | None = None,
        reference_assets: list[ContextAsset] | None = None,
    ) -> PreparedImageRequest:
        refs = list(reference_assets or self._pick_reference_assets(context_packet))
        model_name = self.choose_quality_model(
            quality_mode=quality_mode,
            reference_assets=refs,
            subject_focus=brief.subject_focus,
            moment_type="manual",
            directives=directives,
        )
        aspect_ratio = self._normalize_aspect_ratio(aspect_ratio_override or brief.aspect_ratio_suggestion)
        prompt = self._build_final_prompt(
            title=brief.title,
            scene_core=brief.scene_core,
            subject_focus=brief.subject_focus,
            location=brief.location,
            must_include=brief.must_include,
            avoid=brief.avoid,
            lighting_mood=brief.lighting_mood,
            composition=brief.composition,
            style_additions=brief.style_additions,
            campaign_style_shift=self._extract_campaign_style_shift(context_packet),
            directives=directives,
        )
        return PreparedImageRequest(
            title=brief.title,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            reference_assets=refs,
            quality_mode=quality_mode,
            model_name=model_name,
        )


scene_pipeline = ScenePipeline()
