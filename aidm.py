# aidm.py

import asyncio
import logging

import discord
try:
    from discord.ext import voice_recv
except Exception:  # pragma: no cover - optional runtime dependency guard
    voice_recv = None

from ai_services.assistant_interactions import get_assistant_response
from config import DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, VOICE_AUTOJOIN_CHANNEL_NAME, client, tree
from data_store.db_repository import (
    delete_campaign_record,
    delete_channel_record,
    delete_thread_record,
    ensure_runtime_schema,
    get_campaign_runtime_targets,
)
from data_store.utils import load_thread_data
from discord_app import bot_commands, message_handlers
from voice.transcription import VoiceRecorder


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")

recorder = VoiceRecorder()


@client.event
async def on_ready():
    logging.info("Bot has logged in as %s", client.user)
    await client.change_presence(status=discord.Status.online, activity=discord.Game("Bot is ready"))

    await asyncio.to_thread(ensure_runtime_schema)

    try:
        if DISCORD_GUILD_ID:
            guild_object = discord.Object(id=int(DISCORD_GUILD_ID))
            if client.application_id:
                await client.http.bulk_upsert_global_commands(client.application_id, [])
                logging.info("Cleared remote global slash commands because guild sync is enabled for development.")
            tree.clear_commands(guild=guild_object)
            tree.copy_global_to(guild=guild_object)
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
            runtime_targets = await asyncio.to_thread(get_campaign_runtime_targets, channel.id)

            for thread_id in runtime_targets["thread_ids"]:
                try:
                    thread = client.get_channel(thread_id)
                    if thread is None:
                        thread = await client.fetch_channel(thread_id)
                    if thread is not None:
                        await thread.delete(reason=f"Parent category '{channel.name}' was deleted.")
                except discord.NotFound:
                    pass
                except Exception as exc:
                    logging.warning("Failed to delete thread %s after category deletion %s: %s", thread_id, channel.id, exc)

            for child_channel_id in runtime_targets["channel_ids"]:
                try:
                    child_channel = client.get_channel(child_channel_id)
                    if child_channel is None:
                        child_channel = await client.fetch_channel(child_channel_id)
                    if child_channel is not None:
                        await child_channel.delete(reason=f"Parent category '{channel.name}' was deleted.")
                except discord.NotFound:
                    pass
                except Exception as exc:
                    logging.warning(
                        "Failed to delete channel %s after category deletion %s: %s",
                        child_channel_id,
                        channel.id,
                        exc,
                    )

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
        if VOICE_AUTOJOIN_CHANNEL_NAME and after.channel.name != VOICE_AUTOJOIN_CHANNEL_NAME:
            logging.info(
                "Ignoring join in voice channel %s because auto-join is restricted to %s.",
                after.channel.name,
                VOICE_AUTOJOIN_CHANNEL_NAME,
            )
            return
        if not any(vc.channel.id == after.channel.id for vc in client.voice_clients):
            try:
                if voice_recv is not None:
                    voice_client = await after.channel.connect(cls=voice_recv.VoiceRecvClient)
                else:
                    voice_client = await after.channel.connect()
                logging.info("Bot has joined the voice channel: %s", after.channel.name)
                await recorder.capture_audio(voice_client)
            except discord.ClientException:
                logging.info("Already connected to %s", after.channel.name)
            except Exception as exc:
                logging.exception("Voice capture failed after joining %s: %s", after.channel.name, exc)
                voice_client = discord.utils.get(client.voice_clients, channel=after.channel)
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect(force=True)
                    logging.info("Disconnected from %s after voice startup failure.", after.channel.name)
    elif before.channel and len(before.channel.members) == 1 and before.channel.members[0].id == client.user.id:
        voice_client = discord.utils.get(client.voice_clients, channel=before.channel)
        if voice_client:
            logging.info("Bot is the last member in the voice channel: %s.", before.channel.name)


bot_commands.setup_commands(tree, get_assistant_response)


def run_bot():
    client.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run_bot()
