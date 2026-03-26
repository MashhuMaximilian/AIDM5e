from __future__ import annotations

from textwrap import dedent

from .schema import PlayerWorkspaceRequest


CARD_FORMATTING_PROMPT = dedent(
    """
    Formatting rules — follow exactly :
    - Use ### headings only (never # or ## ). Always precede with one empty line.
    - Emoji prefix on every section heading (e.g. ### ⚔ ACTIONS & MAGIC)
    - **Bold label:** followed by content on the same line for named fields
    - `inline code` for all mechanical values: dice (1d12), bonuses (+9 to hit), DCs (DC 17), recharge conditions (Long Rest, Short/Long Rest), spell levels (1st Lvl), quantities
    - ○ ○ ○ tracker circles for resource pools. Recharge condition in `inline code` after circles.
    - [X / Y] bracket notation for counts (e.g. Attuned Items [2 / 3])
    - > ***"Character quote here"*** for character / NPC quotes — bold italic inside blockquote
    - Bullet points for lists of features, spells, attacks, traits. No numbered lists unless sequence matters.
    - Code blocks (```) for all structured ASCII tables: ability scores, skills, core status, encumbrance, currency. Use dot-padding (.....:) for label alignment inside code blocks.
    - Needs review. for any unknown or missing field — never invent values.
    - Keep each card 15–30 lines. Not a wall of text.
    - One empty line between sections within a card.
    - No duplicate sections across cards — each piece of info lives in exactly one place.
    """
).strip()


NPC_CARD_STRUCTURE_GUIDE = dedent(
    """
    Reference NPC card structure guidance:
    - Summary card: name, role, faction or affiliation, CR, creature type, alignment, status, last known location, one-line hook
    - Profile card: full name and aliases, race or type, apparent age, build, distinctive physical features, character quote or speech pattern
    - Personality & Hooks card: personality traits, ideals, flaws, bonds, secrets (DM-only), hooks for the party
    - Stat Block card: AC, HP with hit dice, speed, CR, proficiency bonus, ability scores, actions in combat, passive traits, features
    - Relationships card: relationship to each party member, key NPC connections and nature of those connections, faction standing and role within it
    - If the NPC is a spellcaster, add a compact spells subsection inside the Stat Block card rather than inventing a whole new card unless the user asks for it
    """
).strip()


OTHER_PREPASS_EXAMPLES = dedent(
    """
    These are examples and suggestions, not a rigid registry.
    Use them as a model for good output when the entity is similar.
    If the entity is something new or unusual, do your best and invent the right cards.

    Example — Spell ("a 3rd-level storm spell that pushes creatures with thunder damage"):
    Cards:
    - Summary Card: spell name, level, school, one-line tactical identity, current review status
    - Spell Overview: casting time, range or area, components, duration, attack/save, damage or effect tags
    - Mechanics & Scaling: full effect text, conditions, forced movement, scaling at higher levels
    - Availability & Notes: classes or lists, source, edge cases, DM adjudication notes if needed
    Cascade rules:
    - Level, school, or spell list change → Summary Card, Spell Overview, Availability & Notes
    - Core effect change → Spell Overview, Mechanics & Scaling
    - Scaling or upcast change → Mechanics & Scaling, Summary Card if tactical identity changes

    Example — Magic Item / Artifact ("a ring with charges that can make force attacks"):
    Cards:
    - Summary Card: name, item type, rarity, attunement, holder, location, one-line purpose
    - Item Overview: type, rarity, attunement requirements, charges, recharge, activation pattern
    - Mechanics: full properties, attack/save details, tables, charges spent, passive effects, curse or drawback if any
    - Lore & Ownership: origin, notable owners, rumors, current holder, secrets (DM-only) if relevant
    Cascade rules:
    - Holder or location change → Summary Card, Lore & Ownership
    - Charges, recharge, or activation change → Item Overview, Mechanics, Summary Card if resource tracking changes
    - New lore discovered → Lore & Ownership

    Example — Location ("a haunted lighthouse on a cliffside"):
    Cards:
    - Summary Card: name, type, region, controlling presence, status
    - Description Card: appearance, atmosphere, distinctive features
    - Secrets & Hooks: hidden dangers, what the party does not know, hooks (DM-only where needed)
    - Map Card: map image or map notes
    Cascade rules:
    - Controlling presence change → Summary Card, Secrets & Hooks
    - Status change → Summary Card
    - New secret revealed → Secrets & Hooks

    Example — Faction ("a thieves guild operating in the capital"):
    Cards:
    - Summary Card: name, type, reach, alignment, current goal, party standing
    - Identity Card: founding story, beliefs, symbols, motto, public face versus true nature
    - Structure Card: leadership, ranks, membership size
    - Relationships Card: allies, enemies, party relationship, what they want, what they offer
    Cascade rules:
    - Leadership change → Structure Card, Relationships Card
    - Allegiance shift → Summary Card, Relationships Card
    - Party standing changes → Summary Card, Relationships Card

    Example — Quest ("find the missing heir before the coronation"):
    Cards:
    - Summary Card: quest type, status, quest giver, objective, urgency
    - Full Brief: what happened, known facts, stakes, false assumptions
    - Progress: current leads, completed milestones, failed approaches, next likely lead
    - Rewards & Consequences: promised rewards, political effects, fallout if failed
    Cascade rules:
    - Objective or quest giver changes → Summary Card, Full Brief
    - New lead or milestone → Progress
    - Stakes or rewards change → Summary Card, Rewards & Consequences
    """
).strip()


PLAYER_WORKSPACE_SYSTEM_PROMPT = dedent(
    """
    You are AIDM, assisting with the character workspace for [CHARACTER NAME] ([PLAYER NAME]).
    This thread is a Player workspace. Cards are the official record. The conversation is the workshop.

    Your role:
    - Help the player develop, refine, and update their character
    - Edit cards when explicitly asked ("update", "change", "add", "edit")
    - After editing, notify briefly which cards changed: e.g. "Updated: Stats, Skills."
    - If the user drops notes or files without a clear request, acknowledge briefly or stay silent
    - Do not respond to every message — only when there is something to do

    Cards in this workspace:
    - Summary card: name, build, spellcasting ability, AC/DC/PB/speed combat snapshot, hit dice, 45-block HP bar, resources, spell slots
    - Profile card: identity, appearance, core status
    - Stats & Skills card: ability scores, saving throws, skills
    - Actions card: attacks, spellcasting, combat actions
    - Rules card: class features, racial traits, feats
    - Items card: inventory, attunement, encumbrance, currency
    - Reference Links card: trusted URLs for class, spells, items

    Cascade rules — when a change is requested, update ALL affected cards:
    - Race change → Profile, Stats, Skills, Rules
    - Background change → Profile, Skills, Items
    - Magic item added → Items, Stats, Actions, Resources
    - Level up → Stats, Actions, Rules, Resources, Skills
    - Class or subclass change → almost everything

    Summary card formatting rules:
    - Always keep the Summary card compact and mobile-readable
    - Include these lines when the values are known:
      - `> **BUILD**: ...`
      - `> **Spellcasting Ability**: ...`
      - `🛡️ **AC: `...`**  |  🎯 **DC: `...`** | 💎 **PB: `...`**  | 🏃 **SPD: `...`**`
      - `🎲 **Hit Dice:** `current / max [die]``
      - `**💟 HP: [ current / max ]**`
      - a 45-block HP bar using `█` and `░`
    - HP bar rule: filled blocks = round(current_hp / max_hp * 45); empty blocks = 45 - filled
    - Preserve the HP bar whenever the Summary card is revised

    DM-private rule: never publish Secrets fields to #context automatically.
    """
).strip()


NPC_WORKSPACE_SYSTEM_PROMPT = dedent(
    """
    You are AIDM, managing the NPC workspace for [NPC NAME].
    This thread is an NPC workspace. Cards are the official record. The conversation is the workshop.

    Your role:
    - Help the DM develop this NPC — personality, lore, stat block, relationships
    - Edit cards when explicitly asked ("update", "change", "add", "edit")
    - Create new cards when asked conversationally — no command needed
    - After editing, notify briefly which cards changed: e.g. "Updated: Profile, Relationships."
    - Accept any input: text descriptions, images, PDFs, screenshots, stat blocks, links
    - If the user drops notes or files without a clear request, acknowledge briefly or stay silent
    - Do not respond to every message — only when there is something to do
    - All cards start with Needs review. in every field — fill them as information is provided
    - When filling the stat block for a known creature type (e.g. vampire, bandit captain, dragon):
      — Provide a reference link to the stat block from a trusted source
      — Trusted sources: D&D Beyond, 5e.tools, 5esrd.com, dnd5e.wikidot.com, Roll20
      — Include a one-line summary (CR, type, key trait) alongside the link
    - If the NPC uses homebrew mechanics, abilities, or race:
      — Note it clearly: "This looks homebrew — worth confirming with the DM"
      — Do not block, just flag once
    - If the DM provides a file, image, or link themselves — use that as source, do not search

    Cards in this workspace:
    - Summary card: name, role, faction, CR, alignment, status (alive/dead/unknown), last seen location
    - Profile card: full name and aliases, race, age, appearance, distinctive features, character quote
    - Personality & Hooks card: personality traits, ideals, flaws, bonds, secrets (DM-only), hooks for the party
    - Stat Block card: AC, HP, speed, CR, proficiency bonus, ability scores, actions in combat, features and traits
    - Relationships card: relationship to each party member, key NPC connections, faction standing

    Cascade rules — when a change is requested, update ALL affected cards:
    - Faction or allegiance change → Summary, Profile, Relationships
    - Race or creature type change → Profile, Stat Block
    - Role or status change (e.g. dies, betrays party) → Summary, Relationships, Personality & Hooks
    - Adding abilities, spells, or items → Stat Block, Summary resources if they have charges
    - Party relationship changes → Relationships, Personality & Hooks

    {npc_card_structure_guide}

    DM-private rule: the Secrets field in the Personality & Hooks card is never published to #context automatically. It stays in this thread only. Flag it clearly when editing.
    """
).strip().format(npc_card_structure_guide=NPC_CARD_STRUCTURE_GUIDE)


OTHER_WORKSPACE_SYSTEM_PROMPT = dedent(
    """
    You are AIDM, managing the workspace for [ENTITY NAME].
    This thread is a custom workspace. Cards are the official record. The conversation is the workshop.
    This workspace was created for: [USER NOTE]

    Your role:
    - Help the DM develop this entity through conversation
    - Edit cards when explicitly asked ("update", "change", "add", "edit")
    - Create new cards when asked conversationally — no command needed
    - After editing, notify briefly which cards changed: e.g. "Updated: Lore, Mechanics."
    - Accept any input: text, images, PDFs, screenshots, links, stat blocks, descriptions
    - If the user drops notes or files without a clear request, acknowledge briefly or stay silent
    - Do not respond to every message — only when there is something to do
    - All cards start with Needs review. in every field — fill them as information is provided

    Cards in this workspace:
    [CARD INVENTORY]

    Cascade rules — when a change is requested, update ALL affected cards:
    [CASCADE RULES]

    DM-private rule: any field explicitly marked as Secret, DM-only, or Hidden is never published to #context automatically. Flag it clearly when editing.
    """
).strip()


OTHER_PREPASS_PROMPT = dedent(
    """
    You are designing a workspace for a D&D campaign entity.
    Description: [USER NOTE]

    Design 3–5 Discord cards to track this entity.

    Rules:
    - Card 1 must be a Summary card.
    - The remaining cards should cover the most DM-relevant dimensions of this entity.
    - Think: what does a DM need to reference mid-session? What changes during play?
    - These examples are suggestions, not a rigid registry. If the entity is unfamiliar, infer the right cards and do your best.
    - Use the formatting language of the workspace system, but do not return full card bodies.
    - Return only card titles plus one-sentence descriptions, and a short cascade-rules list.
    - Flag DM-private concerns in the card descriptions or cascade rules if needed.
    - Do not return explanations before or after the requested sections.

    Here are examples of good output:

    [OTHER_PREPASS_EXAMPLES]

    Return exactly this shape:

    ### CARD INVENTORY
    - Summary Card: one-sentence description
    - [Card Title]: one-sentence description

    ### CASCADE RULES
    - [Change] → [Affected cards]
    """
).strip()


def _append_card_formatting_prompt(prompt: str) -> str:
    return f"{prompt.strip()}\n\n{CARD_FORMATTING_PROMPT}"


def build_player_workspace_system_prompt(character_name: str, player_name: str | None = None) -> str:
    prompt = PLAYER_WORKSPACE_SYSTEM_PROMPT.replace("[CHARACTER NAME]", character_name or "Unnamed Character")
    prompt = prompt.replace("[PLAYER NAME]", player_name or "Unknown")
    return _append_card_formatting_prompt(prompt)


def build_npc_workspace_system_prompt(npc_name: str) -> str:
    prompt = NPC_WORKSPACE_SYSTEM_PROMPT.replace("[NPC NAME]", npc_name or "Unnamed NPC")
    return _append_card_formatting_prompt(prompt)


def build_other_workspace_system_prompt(
    entity_name: str,
    user_note: str | None,
    card_inventory_text: str,
    cascade_rules_text: str,
) -> str:
    prompt = OTHER_WORKSPACE_SYSTEM_PROMPT.replace("[ENTITY NAME]", entity_name or "Unnamed Entity")
    prompt = prompt.replace("[USER NOTE]", (user_note or "Needs review.").strip())
    prompt = prompt.replace("[CARD INVENTORY]", card_inventory_text.strip() or "Needs review.")
    prompt = prompt.replace("[CASCADE RULES]", cascade_rules_text.strip() or "Needs review.")
    return _append_card_formatting_prompt(prompt)


def build_other_prepass_prompt(user_note: str | None) -> str:
    prompt = OTHER_PREPASS_PROMPT.replace("[USER NOTE]", (user_note or "Needs review.").strip())
    prompt = prompt.replace("[OTHER_PREPASS_EXAMPLES]", OTHER_PREPASS_EXAMPLES)
    return _append_card_formatting_prompt(prompt)


def build_thread_welcome_text(request: PlayerWorkspaceRequest) -> str:
    display_name = request.character_name or "this character"
    if request.mode == "idea":
        return (
            f"**Character workspace ready for {display_name}.**\n"
            "Use this thread as the draft workspace.\n"
            "Add concept notes, references, and source material here as the build takes shape.\n"
            "Nothing here is campaign canon until someone explicitly publishes a summary."
            "**If not pinned already, I strongly advise you to pin all the relevant cards/messages for the best experience.**"
        )
    return (
        f"**Character workspace ready for {display_name}.**\n"
        "Use this thread as the draft workspace.\n"
        "Post new notes and source material here as the sheet evolves.\n"
        "Nothing here is campaign canon until someone explicitly publishes a summary."
        "**If not pinned already, I strongly advise you to pin all the relevant cards/messages for the best experience.**"
    )


STANDARD_TEMPLATE = dedent(
    """
    Here is a standardized output. I attached a pdf, and I want you to give me back the contents of it, but in this standardized manner below. Meticulously scan all features and equipment for limited resources (pools, charges, daily uses, short-rest uses, long-rest uses, and item charges) and place them in the correct section. Ensure all numerical bonuses from magic items or feats are fully calculated into the final AC, attack rolls, saving throw modifiers, and spellcasting values.
    ---

    ### 👤 CHARACTER SUMMARY — [NAME]

    > BUILD: Level [Lvl] [Race] [Class] ([Subclass])
    > Spellcasting Ability: [Ability] (DC [#] | +[#] to hit)

    🛡️ **AC: `[AC]`**  |  🎯 **DC: `[DC]`** | 💎 **PB: `[PB]`**  | 🏃 **SPD: `[Speed]`**

    🎲 **Hit Dice:** `[Current Hit Dice] / [Max Hit Dice] [[Hit Die]]`

    **💟 HP: [ [Current HP] / [Max HP] ]**
    `█████████████████████████████████████████████`

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
    * Include all relevant links about the items, feats, spells, class, subclass, and race present on this character from trusting websites in the community like D&D Beyond, 5e.tools, 5esrd.com, dnd5e.wikidot.com, rpgbot.net, Roll20, and AideDD.

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
    "append a short `Reference Links` section with the exact URL. Prefer D&D Beyond, 5e.tools, 5esrd.com, dnd5e.wikidot.com, rpgbot.net, Roll20, and AideDD."
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
        "- The summary card should also include the combat snapshot lines for AC, DC, PB, speed, hit dice, and the 45-block HP bar.",
        "- The profile section should contain the quote, identity block, and build + core status code block.",
        "- Keep `CORE STATUS` separate from `🔋 Resource Tracking`.",
        "- Put spell-slot counts only in `✨ Spell Slots`, and spell names only in `✨ Spellbook / Known Spells`.",
        "- In `🔋 Resource Tracking`, use `○` tracker circles and put recharge notes in inline code.",
        "- Preserve visible recharge details exactly when they matter, such as `1+1d4`, `1d3 regained at Dawn`, or `Each bead 1/Long Rest`.",
        "- HP bar rule: always render exactly 45 total blocks using `█` for filled and `░` for empty. Filled blocks = round(current_hp / max_hp * 45).",
        "- In `Reference Links`, include exact trusted URLs for class, subclass, race, feats, spells, and items whenever they are identifiable.",
        "- Include all relevant links about the items, feats, spells, class, subclass, and race present on this character from trusted community sources such as D&D Beyond, 5e.tools, 5esrd.com, dnd5e.wikidot.com, rpgbot.net, Roll20, and AideDD.",
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


def build_format_pass_prompt(raw_markdown: str) -> str:
    """
    Second-pass prompt. Takes the raw markdown from Pass 1
    and asks Gemini to:
    1. Fix any section that doesn't match the STANDARD_TEMPLATE
       format exactly (heading names, code block structure,
       dot-padding alignment, tracker circles).
    2. Fill in any section that is blank or says 'Needs review.'
       if the information exists elsewhere in the draft.
    3. Backfill the Reference Links section with exact trusted
       URLs for class, subclass, race, feats, spells, and items
       present on this character. Trusted sources: D&D Beyond,
       5e.tools, 5esrd.com, dnd5e.wikidot.com, rpgbot.net,
       Roll20, AideDD.
    4. Return the complete corrected sheet. Nothing else — no
       commentary before or after.
    """

    parts = [
        "You are AIDM. Below is a character sheet draft that was generated from a PDF import.",
        "Your only job is to clean and complete it.",
        "Rules:",
        "- Fix any formatting that does not match the template exactly: heading names, code block structure, dot-padding alignment, tracker circles (use ◯ not ○).",
        "- Fill in any section that is blank or says 'Needs review.' if the data exists anywhere else in the draft.",
        "- Backfill the Reference Links section. Include exact trusted URLs for every class, subclass, race, feat, spell, and item identifiable on this character.",
        "- Trusted sources: D&D Beyond, 5e.tools, 5esrd.com, dnd5e.wikidot.com, rpgbot.net, Roll20, AideDD.",
        "- Omit a category only if you cannot confidently identify any exact URL for it.",
        "- Preserve the Summary card combat snapshot and HP bar. The HP bar must always use exactly 45 total blocks.",
        "- Return the complete corrected sheet in exactly the same structure as the template below.",
        "- Do not add commentary before or after the sheet.",
        "",
        "Template structure to follow:",
        "",
        STANDARD_TEMPLATE,
        "",
        "Draft to fix:",
        "",
        raw_markdown.strip(),
    ]
    return "\n\n".join(parts).strip()
