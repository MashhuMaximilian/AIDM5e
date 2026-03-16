QUERY_PROMPT_TEMPLATES = {
    "spell": (
        "I have a question about the spell. Besides your answer, send the spell description "
        "with its parameters: casting time, level, components, description, range, duration, "
        "attack/save, damage/effect, and a plain URL where someone can find that spell on one "
        "of these websites: http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, "
        "https://roll20.net/compendium/dnd5e, or https://www.aidedd.org/dnd. "
        "Do not use Markdown masked links. {query}"
    ),
    "checkstatus": (
        "I would like to know the current status of a character, including HP, spell slots, "
        "conditions, and any other relevant information. {query}"
    ),
    "hbw_item": (
        "I have a question about a homebrew item. Provide the item's full description, "
        "properties, and usage as it was detailed by the creator of the item or as it appears "
        "in this campaign. Mention who the item belongs to and any relevant background "
        "information. {query}"
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
        "explanation with rules, examples, references to relevant sources, and plain URLs from "
        "https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. "
        "Do not use Markdown masked links. Here is the question: {query}"
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
        "Do not use Markdown masked links. Question: {query}"
    ),
    "item": (
        "I have a question about an item. Besides your answer, include the item's full "
        "description, properties, and usage, as detailed in the Player's Handbook or Dungeon "
        "Master's Guide. Also provide a plain URL where someone can find more information about "
        "the item on http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, "
        "https://roll20.net/compendium/dnd5e, or https://www.aidedd.org/dnd. "
        "Do not use Markdown masked links. {query}"
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
    return QUERY_PROMPT_TEMPLATES.get(query_type, "{query}").format(query=query)

