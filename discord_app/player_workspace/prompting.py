from __future__ import annotations

from textwrap import dedent

from .schema import PlayerWorkspaceRequest


STANDARD_TEMPLATE = dedent(
    """
    Here is a standardized output. I attached a pdf, and I want you to give me back the contents of it, but in this standardized manner below. Meticulously scan all features and equipment for limited resources (pools, charges, or daily uses) and list them in the Resources block. Ensure all numerical bonuses from magic items or feats are fully calculated into the final AC, attack rolls, and saving throw modifiers.
    ---

    ## ⚔️ MARTIAL TEMPLATE (STANDARD)

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

    ## ⚔️ CLASS FEATURES & TRAITS

    **🌌 Racial Traits**
    * **[Trait 1]:** [Effect]
    * **[Trait 2]:** [Effect]
    * **[Trait 3]:** [Effect]

    **🥋 [Class] Features (Lvl [X])**
    * **[Feature Name]:** Description with `[Numerical Values]` in backticks.

    **👊 [Subclass] Features**
    * **[Feature Name]:** Description with `[Numerical Values]` in backticks.

    **📜 Feats**
    * **[Feat Name]:** Concise mechanical summary. Even if it is referenced somewhere else, we still need to list feats here.

    **🛠️ Proficiencies**
    > **Trained Capabilities**
    * **Tools:** [List]
    * **Languages:** [List]

    **🔋 Resource Tracking**
    * Include all visible trackable pools, spell slots, charges, uses/rest, uses/day, item charges, feature counters, and similar per-character resources when present.
    * Use visible tracker circles in this section only, like `○ ○ ○` or `○`, followed by the original recharge note in inline code.
    * Format examples:
      * `**Wild Shape:** ○ ○ `(Short Rest)``
      * `**Star Map (Guiding Bolt/Augury):** ○ ○ ○ ○ `(4/Long Rest)``
      * `**Armband Charges:** `1+1d4 Charges (Regained at Sunset)``
    * Keep `RESOURCES & POOLS` content out of the core-status code block. Put all pool-style information here instead.

    **✨ Spell Slots**
    * **Cantrips:** Unlimited
    * **Lvl 1:** ○ ○ ○ ○
    * **Lvl 2:** ○ ○ ○
    * Only include levels that actually exist on the sheet.

    ### 🔗 REFERENCE LINKS
    * **Race:** [Exact canonical URL if known]
    * **Class:** [Exact canonical URL if known]
    * **Subclass:** [Exact canonical URL if known]
    * **Feats:** [Exact canonical URL if known]
    * **Spells:** [Exact canonical URL if known]
    * **Items:** [Exact canonical URL if known]
    * Omit this section entirely if you do not have at least one exact trusted URL.

    ## 🎒 INVENTORY & ATTUNEMENT

    **💎 Attuned Items `[X / 3]`**
    1. `[Item 1]`
    2. `[Item 2]`

    **⚔️ Notable Gear**
    * **[Item]:** Brief mechanical note.

    ```
    [🎒 ENCUMBRANCE — LIFTING AND CARRYING ]
    -----------------------------------------
    WEIGHT CARRIED: [#] lb
    PUSH/DRAG/LIFT: [#] lb
    CARRY CAPACITY: [#] lb
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

    ---

    ## ✨ SPELLCASTER TEMPLATE (STANDARD)

    *The Spellcaster template follows the same Profile, Stats, and Skills blocks as the Martial template but replaces the Actions and Class Features focus with Magic.*

    ### ⚔️ ACTIONS & MAGIC
    > **Spellcasting Ability:** [Ability] (DC `[#]` | `+[#]` to hit)

    - **[Weapon/Cantrip]:** `+[#] to hit` | `[Dice] + [#]` [Type]

    ## ⚔️ CLASS FEATURES & MAGIC

    **🌿 [Class/Subclass] Features**
    * **[Feature]:** `[Usage/Day]` or `[Effect Name]`.

    **✨ Spellbook / Known Spells**
    * **Cantrips:** *[Name], [Name]*
    * **Lvl 1:** *[Name], [Name]*
    * **Lvl 2:** *[Name], [Name]*
    ... [Up to Lvl 9] ...

    **✨ Spell Slots**
    * **Cantrips:** Unlimited
    * **Lvl 1:** ○ ○ ○ ○
    * **Lvl 2:** ○ ○ ○
    * Only include levels that actually exist on the sheet.
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
        "- Use only `##` and `###` headings.",
        "- Put one empty line before every heading.",
        "- Keep code blocks exactly as code blocks.",
        "- Do not invent values when the sheet is silent; use `Needs review.` or `Unknown` instead.",
        "- Keep the output readable and breathable.",
        "- Do not generate generic search links.",
        "- Capture visible resource pools, charges, uses/rest, uses/day, spell slots, item charges, and feature counters when they appear on the sheet.",
        "- Keep `CORE STATUS` separate from `🔋 Resource Tracking`; do not duplicate pool-style information inside the core-status code block.",
        "- Put spell-slot counts in the dedicated `✨ Spell Slots` section, and keep spell names only in `✨ Spellbook / Known Spells`.",
        "- Do not duplicate the same table or section content in multiple places. Keep each piece of information in its intended section only.",
        "- Keep `ACTIONS IN COMBAT` or `ACTIONS & MAGIC` as a readable multiline section with bullets; do not collapse it into one paragraph.",
        "- Keep the `PASSIVE PERCEPTION` / `PASSIVE INSIGHT` lines and the legend under `SKILLS & SENSES` when available.",
        "- For file imports, do not leave Ability Scores, Saving Throws, Skills, or Actions as `Unknown` if they are visible anywhere on the sheet.",
        f"- Primary source label: {source_label}.",
        f"- Suggested player name: {player_name}.",
        REFERENCE_SOURCE_HINTS,
        "STANDARDIZED OUTPUT:",
        STANDARD_TEMPLATE,
    ]

    if note_block:
        prompt_parts.extend(["USER NOTES:", note_block])
    if source_note_block:
        prompt_parts.extend(["ADDITIONAL SOURCE NOTES:", source_note_block])

    return prompt_parts


def build_import_prompt(request: PlayerWorkspaceRequest) -> str:
    prompt_parts = _base_prompt_parts(request)
    prompt_parts.insert(
        1,
        "This is a file-backed import. Read the attached source material carefully and extract the sheet as faithfully as possible. "
        "Prefer explicit values from the file over inference. If page 1 visibly contains abilities, modifiers, saving throws, skills, "
        "passives, attacks, hit dice, class resources, or other combat values, copy them directly instead of leaving them unknown.",
    )
    return "\n\n".join(part.strip() for part in prompt_parts if part and part.strip())


def build_import_repair_prompt(
    request: PlayerWorkspaceRequest,
    *,
    missing_sections: list[str],
    current_markdown: str,
) -> str:
    missing_list = ", ".join(missing_sections) or "missing sections"
    source_label = request.source.source_label or ("attached file(s)" if request.source.file_paths else "notes")
    prompt_parts = [
        f"You are repairing an incomplete Dungeons & Dragons character-sheet extraction for {request.character_name or 'an unnamed character'}.",
        "Read the attached source material again and repair only the missing or incomplete sections.",
        f"Sections to repair: {missing_list}.",
        "Rules:",
        "- Return only the requested sections, using the exact standardized headings and code-block formats from the template.",
        "- Do not repeat sections that are already complete.",
        "- If page 1 visibly contains ability scores, modifiers, saving throws, skills, passives, attacks, hit dice, or class resources, copy them directly instead of writing `Unknown`.",
        "- If the sheet shows charges, uses/rest, uses/day, item charges, feature counters, or other resource pools, copy them directly into the standardized output.",
        "- Keep actions readable and multiline with bullet points instead of collapsing them into a paragraph.",
        "- Keep passive lines and legend under `SKILLS & SENSES` when they are visible.",
        "- Do not invent values when the sheet is silent.",
        f"- Primary source label: {source_label}.",
        REFERENCE_SOURCE_HINTS,
        "CURRENT EXTRACTION:",
        current_markdown.strip(),
        "STANDARDIZED OUTPUT:",
        STANDARD_TEMPLATE,
    ]
    if request.source.note:
        prompt_parts.extend(["USER NOTES:", request.source.note.strip()])
    if request.source.source_text:
        prompt_parts.extend(["ADDITIONAL SOURCE NOTES:", request.source.source_text.strip()])
    return "\n\n".join(part.strip() for part in prompt_parts if part and part.strip())


def build_idea_prompt(request: PlayerWorkspaceRequest) -> str:
    prompt_parts = _base_prompt_parts(request)
    prompt_parts.insert(
        1,
        "This is a concept-first draft. Use the notes and any attached references to build a clean character draft. "
        "Do not invent mechanics that are not supported; mark unknowns clearly.",
    )
    return "\n\n".join(part.strip() for part in prompt_parts if part and part.strip())


def build_player_prompt(request: PlayerWorkspaceRequest) -> str:
    return build_import_prompt(request) if request.mode == "import" else build_idea_prompt(request)
