from __future__ import annotations

from textwrap import dedent

from .schema import PlayerWorkspaceRequest


STANDARD_TEMPLATE = dedent(
    """
    Here is a standardized output. I attached a pdf, and I want you to give me back the contents of it, but in this standardized manner below. Meticulously scan all features and equipment for limited resources (pools, charges, daily uses, short-rest uses, long-rest uses, and item charges) and place them in the correct section. Ensure all numerical bonuses from magic items or feats are fully calculated into the final AC, attack rolls, saving throw modifiers, and spellcasting values.
    ---

    ### 👤 CHARACTER SUMMARY — [NAME]

    `BUILD: Level [Lvl] [Race] [Class] ([Subclass])`

    `Spellcasting Ability: [Ability] (DC [#] | +[#] to hit)`

    **🔋 RESOURCE TRACKING**
    * **[Resource Name]:** ○ ○ ○ `[Recharge]`
    * **[Resource Name]:** `[Note]`

    
    **✨ Spell Slots**
    * **Cantrips:** Unlimited
    * **Lvl 1:** ◯ ◯ ◯ ◯
    * **Lvl 2:** ○ ○ ○
    * Only include levels that actually exist on the sheet.

    ### 👤 CHARACTER PROFILE — [NAME]

    > ***"[Character Quote]"***

    ```
    [ CHARACTER LEVEL, RACE, & CLASS ]
    ----------------------------------------
    LEVEL.....: [Lvl]
    RACE......: [Race]
    CLASS.....: [Class]
    SUBCLASS..: [Subclass]
    XP........: [Value]
    PLAYER....: [Name]
    BACKGROUND: [Background]
    ALIGNMENT.: [Alignment]
    DEITY.....: [Deity]
    ----------------------------------------
    ```

    ```
    BUILD......: Level [Lvl] [Race] [Class] ([Subclass])

    CORE STATUS
    ----------------------
    AC ......... [Value]
    HP ......... [Current]/[Max]
    SPEED ...... [Value]
    INIT ....... [Value]
    PB ......... [Value]
    ```

    ```
    ABILITY SCORES & SAVING THROWS
    +---------+-------+-----+------+
    | ABILITY | SCORE | MOD | SAVE |
    +---------+-------+-----+------+
    | [●] STR |  [#]  | [#] |  [#] |
    | [●] DEX |  [#]  | [#] |  [#] |
    | [●] CON |  [#]  | [#] |  [#] |
    | [●] INT |  [#]  | [#] |  [#] |
    | [●] WIS |  [#]  | [#] |  [#] |
    | [●] CHA |  [#]  | [#] |  [#] |
    +---------+-------+-----+------+
    ● -> Proficient
    ```

    ```
    SKILLS & SENSES
    -------------------------
    [ ] Acrobatics .... [#]
    [ ] Animal Hand ... [#]
    [ ] Arcana ........ [#]
    [ ] Athletics ..... [#]
    [ ] Deception ..... [#]
    [ ] History ....... [#]
    [ ] Insight ....... [#]
    [ ] Intimidation .. [#]
    [ ] Investigation . [#]
    [ ] Medicine ...... [#]
    [ ] Nature ........ [#]
    [ ] Perception .... [#]
    [ ] Performance ... [#]
    [ ] Persuasion .... [#]
    [ ] Religion ...... [#]
    [ ] Sleight Hand .. [#]
    [ ] Stealth ....... [#]
    [ ] Survival ...... [#]
    --------------------------
    PASSIVE PERCEPTION: [#]
    PASSIVE INSIGHT: [#]
    ----------------------------
    Legend:
    [ ] None
    [●] Proficient
    [◎] Expertise
    ```

    ### ⚔️ ACTIONS IN COMBAT

    > **Multiattack:** [Name] makes `[#] attacks per Action`.
    * **[Weapon Name]:** `+[#] to hit` | `[Dice] + [#]` [Damage Type]
    * **[Special Attack]:** `DC [#]` [Save Type] or [Effect]

    ### ⚔️ RULES & FEATURES

    **🌌 Racial Traits**
    * **[Trait]:** [Effect]

    **🥋 [Class] Features (Lvl [X])**
    * **[Feature Name]:** `[Value]` description.

    **👊 [Subclass] Features**
    * **[Feature Name]:** `[Value]` description.

    **📜 Feats**
    * **[Feat Name]:** Concise mechanical summary.

    **🛠️ Proficiencies**
    * **Tools:** [List]
    * **Languages:** [List]

    **✨ Spellbook / Known Spells**
    * **Cantrips:** *[Name]*
    * **Lvl 1:** *[Name]*

    ### 🎒 INVENTORY & ATTUNEMENT

    **💎 Attuned Items `[X / 3]`**
    1. `[Item 1]`

    **⚔️ Notable Gear**
    * **[Item]:** Brief mechanical note.

    ```
    [🎒 ENCUMBRANCE ]
    -----------------------------------------
    WEIGHT CARRIED: [#] lb
    CARRY CAPACITY: [#] lb
    PUSH/DRAG/LIFT: [#] lb
    -----------------------------------------
    ```

    ```
    [💰 CURRENCY ]
    --------------------------------
    COPPER............: [#]
    SILVER............: [#]
    GOLD..............: [#]
    PLATINUM..........: [#]
    ELECTRUM..........: [#]
    --------------------------------
    ```

    ### ✨ SPELLCASTER TEMPLATE (STANDARD)

    *The Spellcaster template follows the same profile, stats, and skills blocks as the martial template but replaces the actions and class-features focus with magic.*

    ### ⚔️ ACTIONS & MAGIC

    > **Spellcasting Ability:** [Ability] (DC `[#]` | `+[#]` to hit)
    * **[Weapon/Cantrip]:** `+[#] to hit` | `[Dice] + [#]` [Type]

    ### ⚔️ CLASS FEATURES & MAGIC

    **🌿 [Class/Subclass] Features**
    * **[Feature]:** `[Usage/Day]` or `[Effect Name]`.

    **📜 Feats**
    * **[Feat Name]:** Concise mechanical summary.

    **✨ Spellbook / Known Spells**
    * **Cantrips:** *[Name], [Name]*
    * **Lvl 1:** *[Name], [Name]*
    * **Lvl 2:** *[Name], [Name]*
    ... [Up to Lvl 9] ...

    ### 🔗 REFERENCE LINKS
    * Include all relevant links about the items, feats, spells, class, subclass, and race present on this character from trusting websites in the community like D&D Beyond, dnd5e.wikidot.com, 5e.tools, 5esrd.com, roll20, or rpgbot.net. 

    **Race / Class / Subclass**
    * [Druid](link)
    * [Subclass or race link](link)

    **Feats**
    * [Feat](link)

    **Spells**
    * [Spell](link)

    **Items**
    * [Item](link)

    **Other**
    * [Background](link)
    """
).strip()


REFERENCE_SOURCE_HINTS = (
    "If you can identify an exact canonical page for a class, subclass, race, feat, spell, or item from a trusted source, "
    "append a short `Reference Links` section with the exact URL. Prefer D&D Beyond, dnd5e.wikidot.com, 5e.tools, 5esrd.com, "
    "or rpgbot.net when you know the exact page. If you are not confident about the exact page, omit the link instead of "
    "inventing a search URL."
)


def _base_prompt_parts(request: PlayerWorkspaceRequest) -> list[str]:
    character_name = request.character_name or "Unnamed Character"
    player_name = request.player_name or "Unknown"
    source_label = request.source.source_label or ("attached file(s)" if request.source.file_paths else "notes")
    note_block = request.source.note.strip() if request.source.note else ""
    source_note_block = request.source.source_text.strip() if request.source.source_text else ""

    prompt_parts = [
        f"You are AIDM, an expert Dungeons & Dragons character-sheet reader and formatter for {character_name}.",
        "Use the standardized template below and preserve the structure as closely as possible.",
        "Rules:",
        "- Use only `###` headings, never `#` or `##` headings.",
        "- Put one empty line before every heading.",
        "- Keep code blocks exactly as code blocks.",
        "- Do not invent values when the sheet is silent; use `Needs review.` or `Unknown` instead.",
        "- Do not generate generic search links.",
        "- Do not duplicate the same table, list, or code block in multiple sections.",
        "- The summary card should contain only: name, build, spellcasting ability when relevant, resource tracking, and spell slots.",
        "- The profile section should contain the quote, identity block, and build + core status code block.",
        "- Keep `CORE STATUS` separate from `🔋 Resource Tracking`.",
        "- Put spell-slot counts only in `✨ Spell Slots`, and spell names only in `✨ Spellbook / Known Spells`.",
        "- In `🔋 Resource Tracking`, use `○` tracker circles and put recharge notes in inline code.",
        "- Preserve visible recharge details exactly when they matter, such as `1+1d4`, `1d3 regained at Dawn`, or `Each bead 1/Long Rest`.",
        "- In `Reference Links`, include exact trusted URLs for class, subclass, race, feats, spells, and items whenever they are identifiable.",
        "- Include all relevant links about the items, feats, spells, class, subclass, and race present on this character from trusted community sources such as D&D Beyond, dnd5e.wikidot.com, 5e.tools, 5esrd.com, Roll20, or rpgbot.net.",
        "- Do not limit links to a single website if better exact links are available elsewhere.",
        "- For spells and items especially, include links for all spells/items actually listed on the character whenever exact trusted URLs are identifiable.",
        "- If a category has no exact trusted links, omit that category rather than inventing or guessing.",
        REFERENCE_SOURCE_HINTS,
    ]

    if request.mode == "idea":
        prompt_parts.extend(
            [
                "This is idea mode.",
                f"Build a draft for player `{player_name}` using the supplied concept material.",
                "Do not pretend a full sheet exists. Keep unknown mechanics as `Needs review.`.",
            ]
        )
    else:
        prompt_parts.extend(
            [
                "This is import mode.",
                f"Read the provided character material from `{source_label}` and convert it into the standardized structure.",
                "Extract from the sheet as faithfully as possible.",
            ]
        )

    if note_block:
        prompt_parts.extend(["Additional note from the user:", note_block])
    if source_note_block:
        prompt_parts.extend(["Source text extracted from the user-provided material:", source_note_block])

    prompt_parts.extend(["Return only the completed formatted character sheet.", "", STANDARD_TEMPLATE])
    return prompt_parts


def build_player_import_prompt(request: PlayerWorkspaceRequest) -> str:
    return "\n\n".join(_base_prompt_parts(request)).strip()


def build_player_repair_prompt(request: PlayerWorkspaceRequest, raw_markdown: str, missing_sections: list[str]) -> str:
    missing = ", ".join(missing_sections) if missing_sections else "the missing required sections"
    parts = _base_prompt_parts(request)
    parts.extend(
        [
            "",
            "The previous draft was incomplete.",
            f"Repair only these missing or incomplete sections: {missing}.",
            "Return the full corrected sheet in the same standardized format, not just a diff.",
            "",
            "Previous draft:",
            raw_markdown.strip(),
        ]
    )
    return "\n\n".join(parts).strip()


def build_player_reference_links_prompt(request: PlayerWorkspaceRequest, raw_markdown: str) -> str:
    parts = _base_prompt_parts(request)
    parts.extend(
        [
            "",
            "Your only task is to backfill the `### 🔗 REFERENCE LINKS` section.",
            "Do not regenerate the whole character sheet.",
            "Return only the completed `### 🔗 REFERENCE LINKS` section.",
            "Requirements:",
            "- Include all relevant exact trusted links you can confidently identify for class, subclass, race, feats, spells, items, and other character-specific references.",
            "- For spells, include links for all spells that appear in the character's spellbook / known spells whenever exact links are identifiable.",
            "- For items, include links for all named items that appear in the character's inventory / attunement whenever exact links are identifiable.",
            "- Use the exact categorized structure from the template: `Race / Class / Subclass`, `Feats`, `Spells`, `Items`, `Other`.",
            "- Omit a category only if you cannot confidently identify any exact trusted links for it.",
            "- Use markdown links in the form `* [Label](https://example.com)`.",
            "",
            "Existing draft for context:",
            raw_markdown.strip(),
        ]
    )
    return "\n\n".join(parts).strip()


def build_import_prompt(request: PlayerWorkspaceRequest) -> str:
    return build_player_import_prompt(request)


def build_player_prompt(request: PlayerWorkspaceRequest) -> str:
    return build_player_import_prompt(request)


def build_import_repair_prompt(
    request: PlayerWorkspaceRequest,
    *,
    missing_sections: list[str],
    current_markdown: str,
) -> str:
    return build_player_repair_prompt(request, current_markdown, missing_sections)


def build_import_reference_links_prompt(
    request: PlayerWorkspaceRequest,
    *,
    current_markdown: str,
) -> str:
    return build_player_reference_links_prompt(request, current_markdown)


def build_idea_prompt(request: PlayerWorkspaceRequest) -> str:
    return build_player_import_prompt(request)
