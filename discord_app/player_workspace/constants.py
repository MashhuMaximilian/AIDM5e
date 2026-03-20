import discord


MAX_PLAYER_CARD_MESSAGE_LENGTH = 1900
PLAYER_CARD_HISTORY_LIMIT = 250
EMBED_PLACEHOLDER = "\u200b"

CARD_TITLES = {
    "character_card": "Character Card",
    "sheet_card": "Sheet Card",
    "skills_card": "Skills & Senses",
    "profile_card": "Profile Card",
    "rules_card": "Rules Card",
    "items_card": "Items Card",
    "workspace_card": "Workspace Status",
}

CARD_COLORS = {
    "character_card": discord.Color.blurple(),
    "sheet_card": discord.Color.gold(),
    "skills_card": discord.Color.dark_blue(),
    "profile_card": discord.Color.teal(),
    "rules_card": discord.Color.dark_magenta(),
    "items_card": discord.Color.dark_orange(),
    "workspace_card": discord.Color.dark_grey(),
}

SAVE_LABELS = (
    ("Strength Save", "STR"),
    ("Dexterity Save", "DEX"),
    ("Constitution Save", "CON"),
    ("Intelligence Save", "INT"),
    ("Wisdom Save", "WIS"),
    ("Charisma Save", "CHA"),
)

SKILL_LABELS = (
    "Acrobatics",
    "Animal Handling",
    "Arcana",
    "Athletics",
    "Deception",
    "History",
    "Insight",
    "Intimidation",
    "Investigation",
    "Medicine",
    "Nature",
    "Perception",
    "Performance",
    "Persuasion",
    "Religion",
    "Sleight of Hand",
    "Stealth",
    "Survival",
)

ABILITY_ORDER = ("STR", "DEX", "CON", "INT", "WIS", "CHA")

ABILITY_NAMES = {
    "STR": "Strength",
    "DEX": "Dexterity",
    "CON": "Constitution",
    "INT": "Intelligence",
    "WIS": "Wisdom",
    "CHA": "Charisma",
}

SKILL_TO_ABILITY = {
    "Acrobatics": "DEX",
    "Animal Handling": "WIS",
    "Arcana": "INT",
    "Athletics": "STR",
    "Deception": "CHA",
    "History": "INT",
    "Insight": "WIS",
    "Intimidation": "CHA",
    "Investigation": "INT",
    "Medicine": "WIS",
    "Nature": "INT",
    "Perception": "WIS",
    "Performance": "CHA",
    "Persuasion": "CHA",
    "Religion": "INT",
    "Sleight of Hand": "DEX",
    "Stealth": "DEX",
    "Survival": "WIS",
}

CLASS_HIT_DIE_SIDES = {
    "artificer": 8,
    "barbarian": 12,
    "bard": 8,
    "cleric": 8,
    "druid": 8,
    "fighter": 10,
    "monk": 8,
    "paladin": 10,
    "ranger": 10,
    "rogue": 8,
    "sorcerer": 6,
    "warlock": 8,
    "wizard": 6,
}

BASE_SPEEDS = {
    "wood elf": 35,
    "air genasi": 35,
    "centaur": 40,
    "satyr": 35,
    "tabaxi": 30,
    "halfling": 25,
    "dwarf": 25,
    "gnome": 25,
}

MODE_LABELS = {
    "idea": "Idea",
    "import": "Import",
    "finished": "Refine",
}

STATUS_LABELS = {
    "draft": "Draft",
    "needs_review": "Needs Review",
    "approved": "Approved",
    "published_public": "Published",
    "published_dm": "DM Published",
}

MISSING_PLACEHOLDER = "Needs review."
