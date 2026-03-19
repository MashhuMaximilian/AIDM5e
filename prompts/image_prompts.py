BASE_DND_STYLE_BLOCK = (
    "House visual style: modern heroic realism for tabletop fantasy illustration.\\n"
    "- Painterly digital finish with visible brush texture and believable material surfaces.\\n"
    "- Adventurers look travelled and practical: layered gear, straps, pouches, worn leather, muddied boots, lived-in fabric.\\n"
    "- Magic is luminous and dramatic, with strong high-fantasy lighting and atmospheric glow.\\n"
    "- Anatomy, creature weight, architecture, and props should feel structurally grounded and physically believable.\\n"
    "- Composition should feel cinematic but readable, like a polished fantasy book illustration rather than a film still.\\n"
    "- Avoid plastic rendering, empty costume design, generic AI fantasy mush, or over-cartoonish exaggeration."
)


SCENE_SCHEMA_DESCRIPTION = (
    "Return JSON with this shape only:\\n"
    "{\\n"
    '  "scenes": [\\n'
    "    {\\n"
    '      "scene_id": "scene_01",\\n'
    '      "title": "short title",\\n'
    '      "why_it_matters": "why this moment deserves an image",\\n'
    '      "visual_distinctiveness": "what makes it visually different from other moments",\\n'
    '      "moment_type": "revelation|travel|ritual|combat|character|environment|mystery|aftermath|other",\\n'
    '      "subject_focus": "one character|several characters|creature|environment only|object|room interior|wide landscape|mixed",\\n'
    '      "location": "where the image happens",\\n'
    '      "scene_core": "the main visual beat in 1-3 sentences",\\n'
    '      "must_include": ["list of visual must-haves"],\\n'
    '      "avoid": ["list of things not to imply or invent"],\\n'
    '      "lighting_mood": "short mood and lighting description",\\n'
    '      "composition": "suggested framing",\\n'
    '      "style_additions": ["scene-specific stylistic additions that complement the house style"],\\n'
    '      "priority_reason": "why it should or should not survive final selection",\\n'
    '      "aspect_ratio_suggestion": "1:1|3:4|4:3|9:16|16:9"\\n'
    "    }\\n"
    "  ]\\n"
    "}"
)


SELECTION_SCHEMA_DESCRIPTION = (
    "Return JSON with this shape only:\\n"
    "{\\n"
    '  "selected_scene_ids": ["scene_01", "scene_03"],\\n'
    '  "selection_rationale": "short explanation of why these are the strongest non-redundant scenes"\\n'
    "}"
)


DIRECT_IMAGE_SCHEMA_DESCRIPTION = (
    "Return JSON with this shape only:\\n"
    "{\\n"
    '  "title": "short label",\\n'
    '  "subject_focus": "what is visually central",\\n'
    '  "scene_core": "main visual description",\\n'
    '  "location": "where this image happens",\\n'
    '  "must_include": ["hard visual requirements"],\\n'
    '  "avoid": ["things not to imply or invent"],\\n'
    '  "lighting_mood": "mood and lighting",\\n'
    '  "composition": "framing",\\n'
    '  "style_additions": ["optional scene-specific style tweaks"],\\n'
    '  "aspect_ratio_suggestion": "1:1|3:4|4:3|9:16|16:9"\\n'
    "}"
)



def build_scene_extraction_prompt(
    objective_summary: str,
    narrative_summary: str,
    context_text: str | None = None,
    campaign_style_shift: str | None = None,
    max_scenes_cap: int | None = None,
) -> str:
    scene_count_guidance = (
        f"Do not return more than {max_scenes_cap} scenes.\\n" if max_scenes_cap else ""
    )
    return (
        "You are selecting candidate fantasy illustration scenes from a completed tabletop RPG session.\\n\\n"
        "Your job is to propose only scenes that are both:\\n"
        "- narratively meaningful, and\\n"
        "- visually distinct enough to deserve their own illustration.\\n\\n"
        "Do not force a fixed number of scenes. Some sessions only support a few strong images.\\n"
        "Avoid redundant scenes from the same beat unless they are genuinely different in composition, subject, or mood.\\n"
        "Prefer scenes that would create compelling artwork even for someone who never saw the session.\\n"
        f"{scene_count_guidance}"
        "Use the campaign context to preserve names, spellings, roles, and stable visual facts.\\n"
        "Not every scene needs characters; some can focus on an environment, room, artifact, or ominous location.\\n"
        "If a scene is too vague or too repetitive, leave it out.\\n\\n"
        "Summary sources:\\n"
        f"Objective summary:\\n{objective_summary.strip() or 'None.'}\\n\\n"
        f"Narrative summary:\\n{narrative_summary.strip() or 'None.'}\\n\\n"
        f"Campaign context:\\n{context_text.strip() if context_text else 'None.'}\\n\\n"
        f"Campaign style shift:\\n{campaign_style_shift.strip() if campaign_style_shift else 'None.'}\\n\\n"
        f"{SCENE_SCHEMA_DESCRIPTION}"
    )



def build_scene_selection_prompt(
    scene_payload_json: str,
    context_text: str | None = None,
    max_scenes_cap: int | None = None,
) -> str:
    cap_guidance = (
        f"Never select more than {max_scenes_cap} scenes.\\n" if max_scenes_cap else ""
    )
    return (
        "You are choosing the strongest final illustration scenes from candidate scenes for a tabletop RPG session.\\n\\n"
        "Select only scenes that are:\\n"
        "- visually strong,\\n"
        "- non-redundant,\\n"
        "- emotionally or narratively important, and\\n"
        "- clear enough to illustrate well.\\n\\n"
        "Do not force a fixed number. If only 2 scenes are truly strong, select 2. If more are justified, select more.\\n"
        f"{cap_guidance}"
        "Prefer variety of scale, setting, and focus.\\n"
        "Avoid selecting multiple scenes that would look nearly identical.\\n\\n"
        f"Campaign context:\\n{context_text.strip() if context_text else 'None.'}\\n\\n"
        f"Candidate scenes JSON:\\n{scene_payload_json}\\n\\n"
        f"{SELECTION_SCHEMA_DESCRIPTION}"
    )



def build_direct_image_brief_prompt(
    source_material: str,
    directives: str | None = None,
    context_text: str | None = None,
    campaign_style_shift: str | None = None,
) -> str:
    return (
        "You are turning user-provided tabletop RPG material into a single strong fantasy illustration brief.\\n\\n"
        "Produce one image brief only.\\n"
        "Use the source material as the main truth for what should appear.\\n"
        "Use the campaign context to preserve names, spellings, and stable visual facts.\\n"
        "The result can focus on a character, a group, a location, a creature, or an object depending on what best fits the source.\\n"
        "Do not add unrelated elements.\\n\\n"
        f"Source material:\\n{source_material.strip() or 'None.'}\\n\\n"
        f"Directives:\\n{directives.strip() if directives else 'None.'}\\n\\n"
        f"Campaign context:\\n{context_text.strip() if context_text else 'None.'}\\n\\n"
        f"Campaign style shift:\\n{campaign_style_shift.strip() if campaign_style_shift else 'None.'}\\n\\n"
        f"{DIRECT_IMAGE_SCHEMA_DESCRIPTION}"
    )
