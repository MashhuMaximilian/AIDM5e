# config.py

import logging
import os
from pathlib import Path

import discord
from dotenv import load_dotenv


env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


from prompts.transcription_prompts import DEFAULT_AUDIO_PROMPT


BASE_DIR = Path(__file__).parent.resolve()
AIDM_PROMPT_PATH = BASE_DIR / "prompts" / "system" / "aidm_prompt.txt"
TRANSCRIPT_PATH = BASE_DIR / "transcript.txt"
AUDIO_FILES_PATH = BASE_DIR / "audio_files"


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
DM_ROLE_NAME = os.getenv("DM_ROLE_NAME", "DM")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
GEMINI_TOP_P = float(os.getenv("GEMINI_TOP_P", "0.95"))
GEMINI_TOP_K = int(os.getenv("GEMINI_TOP_K", "40"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
DIRECT_CONNECTION_STRING = os.getenv("DIRECT_CONNECTION_STRING")
SUPABASE_DB_HOST = os.getenv("SUPABASE_DB_HOST")
SUPABASE_DB_PORT = int(os.getenv("SUPABASE_DB_PORT", "5432"))
SUPABASE_DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = os.getenv("SUPABASE_DB_USER")
SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")
SUPABASE_DB_SSLMODE = os.getenv("SUPABASE_DB_SSLMODE", "require")

AUDIO_CHUNK_SECONDS = int(os.getenv("AUDIO_CHUNK_SECONDS", "180"))
AUDIO_PROMPT = os.getenv(
    "AUDIO_PROMPT",
    DEFAULT_AUDIO_PROMPT,
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.voice_states = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


category_threads: dict = {}
category_conversations: dict = {}
channel_character_sheets: dict = {}
