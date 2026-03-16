# aidm.py

import asyncio
import logging

import discord

import bot_commands
import message_handlers
import transcription
from assistant_interactions import get_assistant_response
from config import DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, client, tree
from db_repository import (
    delete_campaign_record,
    delete_channel_record,
    delete_thread_record,
    ensure_runtime_schema,
)
from utils import load_thread_data


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")

recorder = transcription.VoiceRecorder()


@client.event
async def on_ready():
    logging.info("Bot has logged in as %s", client.user)
    await client.change_presence(status=discord.Status.online, activity=discord.Game("Bot is ready"))

    await asyncio.to_thread(ensure_runtime_schema)

    try:
        if DISCORD_GUILD_ID:
            guild_object = discord.Object(id=int(DISCORD_GUILD_ID))
            await tree.sync(guild=guild_object)
            logging.info("Slash commands synced to guild %s.", DISCORD_GUILD_ID)
        else:
            await tree.sync()
            logging.info("Slash commands synced globally.")
    except Exception as exc:
        logging.error("Error syncing commands: %s", exc)

    load_thread_data()
    client.event(message_handlers.on_message)
    logging.info("Bot is ready.")


@client.event
async def on_thread_delete(thread):
    try:
        await asyncio.to_thread(delete_thread_record, thread.id)
        load_thread_data()
        logging.info("Thread %s removed from Supabase snapshot.", thread.id)
    except Exception as exc:
        logging.warning("Failed to delete thread %s from Supabase: %s", thread.id, exc)


@client.event
async def on_guild_channel_delete(channel):
    try:
        if isinstance(channel, discord.CategoryChannel):
            await asyncio.to_thread(delete_campaign_record, channel.id)
        elif isinstance(channel, discord.Thread):
            await asyncio.to_thread(delete_thread_record, channel.id)
        elif isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
            await asyncio.to_thread(delete_channel_record, channel.id)
        load_thread_data()
        logging.info("Channel deletion processed for %s.", channel.id)
    except Exception as exc:
        logging.warning("Failed to process channel deletion for %s: %s", channel.id, exc)


@client.event
async def on_voice_state_update(member, before, after):
    if after.channel and member.id != client.user.id:
        if not any(vc.channel.id == after.channel.id for vc in client.voice_clients):
            try:
                voice_client = await after.channel.connect()
                logging.info("Bot has joined the voice channel: %s", after.channel.name)
                await recorder.capture_audio(voice_client)
            except discord.ClientException:
                logging.info("Already connected to %s", after.channel.name)
    elif before.channel and len(before.channel.members) == 1 and before.channel.members[0].id == client.user.id:
        voice_client = discord.utils.get(client.voice_clients, channel=before.channel)
        if voice_client:
            logging.info("Bot is the last member in the voice channel: %s.", before.channel.name)


bot_commands.setup_commands(tree, get_assistant_response)


def run_bot():
    client.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run_bot()
