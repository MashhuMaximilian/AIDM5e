# config.py

import logging
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv


env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


from prompts.transcription_prompts import DEFAULT_AUDIO_PROMPT


BASE_DIR = Path(__file__).parent.resolve()
AIDM_PROMPT_PATH = BASE_DIR / "prompts" / "system" / "aidm_prompt.txt"
TRANSCRIPT_PATH = BASE_DIR / "transcript.txt"
TRANSCRIPT_MANIFEST_PATH = BASE_DIR / "transcript_manifest.json"
AUDIO_FILES_PATH = BASE_DIR / "audio_files"
VOICE_CONTEXT_DIR = BASE_DIR / "voice_context"


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
DM_ROLE_NAME = os.getenv("DM_ROLE_NAME", "DM")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
GEMINI_TRANSCRIBE_MODEL = os.getenv("GEMINI_TRANSCRIBE_MODEL", GEMINI_CHAT_MODEL)
GEMINI_SUMMARY_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", GEMINI_CHAT_MODEL)
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")
GEMINI_IMAGE_HQ_MODEL = os.getenv("GEMINI_IMAGE_HQ_MODEL", "gemini-3-pro-image-preview")
GEMINI_IMAGE_DEFAULT_ASPECT_RATIO = os.getenv("GEMINI_IMAGE_DEFAULT_ASPECT_RATIO", "4:3")
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

AUDIO_CHUNK_SECONDS = int(os.getenv("AUDIO_CHUNK_SECONDS", "1200"))
AUDIO_SUMMARY_WINDOW_CHUNKS = int(os.getenv("AUDIO_SUMMARY_WINDOW_CHUNKS", "1"))
AUDIO_BITRATE = os.getenv("AUDIO_BITRATE", "128k")
AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "44100"))
AUDIO_CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))
if sys.platform == "darwin":
    _default_ffmpeg_input_format = "avfoundation"
    _default_ffmpeg_input_device = ":0"
elif sys.platform.startswith("linux"):
    _default_ffmpeg_input_format = ""
    _default_ffmpeg_input_device = ""
elif sys.platform == "win32":
    _default_ffmpeg_input_format = ""
    _default_ffmpeg_input_device = ""
else:
    _default_ffmpeg_input_format = ""
    _default_ffmpeg_input_device = ""
FFMPEG_INPUT_FORMAT = os.getenv("FFMPEG_INPUT_FORMAT", _default_ffmpeg_input_format)
FFMPEG_INPUT_DEVICE = os.getenv("FFMPEG_INPUT_DEVICE", _default_ffmpeg_input_device)
AUDIO_PROMPT = os.getenv(
    "AUDIO_PROMPT",
    DEFAULT_AUDIO_PROMPT,
)
KEEP_AUDIO_FILES = os.getenv("KEEP_AUDIO_FILES", "false").lower() == "true"
KEEP_TRANSCRIPT_FILES = os.getenv("KEEP_TRANSCRIPT_FILES", "false").lower() == "true"
VOICE_PUBLIC_CONTEXT_PATH = os.getenv("VOICE_PUBLIC_CONTEXT_PATH", str(VOICE_CONTEXT_DIR / "summary_public.txt"))
VOICE_SESSION_CONTEXT_PATH = os.getenv("VOICE_SESSION_CONTEXT_PATH", str(VOICE_CONTEXT_DIR / "summary_session.txt"))
VOICE_DM_CONTEXT_PATH = os.getenv("VOICE_DM_CONTEXT_PATH", str(VOICE_CONTEXT_DIR / "summary_dm.txt"))
VOICE_INCLUDE_DM_CONTEXT = os.getenv("VOICE_INCLUDE_DM_CONTEXT", "false").lower() == "true"

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
