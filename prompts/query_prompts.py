TELLME_QUERY_TYPES = {"checkstatus", "homebrew", "npc", "inventory", "rollcheck"}
ASKDM_QUERY_TYPES = {
    "spell",
    "game_mechanics",
    "monsters_creatures",
    "world_lore_history",
    "conditions_effects",
    "rules_clarifications",
    "item",
    "race_class",
}

TELLME_PREAMBLE = """You are in support/reference mode.

The user wants practical information related to the campaign, character state, items, spells, NPCs, inventory, status, or likely actions.

Your job:
- Answer the question directly first.
- Then provide the most relevant details.
- When the subject is an official D&D spell, item, feature, or similar rules content, provide the official description or the most relevant official details.
- Always identify the source book when known.
- Always include a plain URL reference when available.
- If the answer depends on campaign-specific information that is missing from memory or context, say that clearly.
- If something appears to be homebrew, campaign-specific, or uncertain, say so explicitly.
- Do not use Markdown masked links.

Preferred output shape:
1. **Short answer**
2. **Details**
3. **Source**
4. **Reference URL**

Rules:
- Prefer official source material when the question is about standard D&D content.
- Do not invent source books or official wording.
- If the exact official source is uncertain, say so.
- If the question is campaign-specific, use active memory/history first.
- Do not drift into long dramatic narration unless the user asked for it.
"""

ASKDM_PREAMBLE = """You are in rules/lore reference mode.

The user wants help with D&D mechanics, monsters, conditions, lore, clarifications, race/class information, item interpretation, or adjudication guidance.

Your job:
- Give a short answer first unless the user explicitly asks for a deep explanation.
- Then explain the relevant rule, lore, or adjudication logic.
- Distinguish clearly between:
  - official rule or source-based answer,
  - common interpretation,
  - homebrew or campaign-dependent variation.
- If there is ambiguity, say so clearly.
- If useful, include plain URLs only.
- Do not use Markdown masked links.

Preferred output shape:
1. **Short answer**
2. **Explanation**
3. **Caveat or ambiguity**
4. **Source note**
5. **Reference URL(s)**

Rules:
- Be concise by default.
- Do not pretend to know campaign facts that are not present in memory/history.
- Do not invent a source.
- Do not over-roleplay when the user asked for a factual answer.
- Prefer truthfulness and precision over sounding complete.
"""

QUERY_PROMPT_TEMPLATES = {
    "spell": (
        "I have a question about the spell. Besides your answer, send the spell description "
        "with its parameters: casting time, level, components, description, range, duration, "
        "attack/save, damage/effect, the official source book if known, and a plain URL where "
        "someone can find that spell on one of these websites: http://dnd5e.wikidot.com/, "
        "https://www.dndbeyond.com/, https://roll20.net/compendium/dnd5e, or "
        "https://www.aidedd.org/dnd. {query}"
    ),
    "checkstatus": (
        "I would like to know the current status of a character, including HP, spell slots, "
        "conditions, and any other relevant information. {query}"
    ),
    "homebrew": (
        "I have a question about homebrew campaign content. It may involve an item, feature, "
        "spell, NPC trait, or other custom material. Provide the full relevant description and "
        "usage as it exists in this campaign, mention who or what it belongs to when relevant, "
        "and include any background context that matters. {query}"
    ),
    "npc": (
        "I have a question about an NPC. Provide all known information about this NPC, "
        "including their background, motivations, and recent interactions with the party. {query}"
    ),
    "inventory": (
        "I have a question about the inventory of a character. Provide a detailed list of items "
        "currently in the specified character's inventory, including any magical properties or "
        "special features. If asking about a specific item, confirm its presence and provide "
        "details. {query}"
    ),
    "rollcheck": (
        "I want to test the feasibility of an action or a skill check before deciding to do it "
        "in the game. Provide guidance on what I would need to roll, including the appropriate "
        "skill and any potential outcomes or modifiers to consider. {query}"
    ),
    "game_mechanics": (
        "This is a query about game mechanics and gameplay elements based on official sources "
        "like the Player's Handbook (PHB) or Dungeon Master's Guide (DMG). Provide a detailed "
        "explanation with rules, examples, references to relevant sources, source book names "
        "when known, and plain URLs from "
        "https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. "
        "Here is the question: {query}"
    ),
    "monsters_creatures": (
        "This is a question about monsters or creatures, including those from the Monster Manual "
        "or homebrew. Include abilities, weaknesses, lore, and strategies for handling them in "
        "combat. Provide references to the source and plain URLs to reliable websites such as "
        "http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, "
        "https://roll20.net/compendium/dnd5e, https://forgottenrealms.fandom.com/wiki, or "
        "https://www.aidedd.org/dnd. Do not use Markdown masked links. Question: {query}"
    ),
    "world_lore_history": (
        "This is an inquiry about the lore, history, and cosmology of the game world. Provide a "
        "detailed explanation with relevant background information, official sources, and notable "
        "events or characters. Include 3 plain URLs to reliable websites. Do not use Markdown "
        "masked links. Question: {query}"
    ),
    "conditions_effects": (
        "This is a question about conditions and their effects, such as stunned, poisoned, "
        "grappled, etc. Explain their rules, implications in combat and exploration, and any "
        "interactions with spells or abilities. Reference official sources like the PHB or DMG "
        "and use plain URLs from https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or "
        "https://roll20.net/. Do not use Markdown masked links. Question: {query}"
    ),
    "rules_clarifications": (
        "This is a query about specific rule clarifications. Provide a clear and detailed "
        "explanation based on official sources, and include any applicable errata or optional "
        "rules. Reference the PHB, DMG, or other official sourcebooks and use plain URLs from "
        "https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. "
        "Question: {query}"
    ),
    "item": (
        "I have a question about an item. Besides your answer, include the item's full "
        "description, properties, and usage, as detailed in the Player's Handbook or Dungeon "
        "Master's Guide, and identify the source book if known. Also provide a plain URL where "
        "someone can find more information about the item on http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, "
        "https://roll20.net/compendium/dnd5e, or https://www.aidedd.org/dnd. "
        "{query}"
    ),
    "race_class": (
        "This is a question about a D&D race, class, or subclass, including official content or "
        "homebrew. Provide details on abilities, traits, key features, optimization, lore, "
        "background, and roleplaying suggestions. If possible, compare it with similar races or "
        "classes. Provide references to the source material and plain URLs to reliable websites "
        "such as https://forgottenrealms.fandom.com/wiki, https://www.dndbeyond.com/, "
        "https://rpgbot.net/dnd5, or https://roll20.net/. Do not use Markdown masked links. "
        "Question: {query}"
    ),
}


def construct_query_prompt(query_type: str, query: str) -> str:
    prompt_body = QUERY_PROMPT_TEMPLATES.get(query_type, "{query}").format(query=query)
    if query_type in TELLME_QUERY_TYPES:
        return f"{TELLME_PREAMBLE}\n\nUser request:\n{prompt_body}"
    if query_type in ASKDM_QUERY_TYPES:
        return f"{ASKDM_PREAMBLE}\n\nUser request:\n{prompt_body}"
    return prompt_body
