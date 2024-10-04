# aidm.py

import discord
import aiohttp
import openai
import os
import asyncio
import logging
from datetime import datetime
import bot_commands
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Set up Discord bot client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

# Get tokens and API keys
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN') 
openai.api_key = os.getenv('OPENAI_API_KEY')
ASSISTANT_ID = os.getenv('ASSISTANT_ID')

# Headers for OpenAI API requests
HEADERS = {
    'Authorization': f'Bearer {openai.api_key}',
    'Content-Type': 'application/json',
    'OpenAI-Beta': 'assistants=v2'
}

# Store thread ID and conversation history
category_threads = {}
category_conversations = {}
channel_character_sheets = {}

file_path = Path(__file__).parent.resolve() / 'aidm_prompt.txt'
try:
    with open(file_path, 'r') as f:
        system_prompt = f.read()
except FileNotFoundError:
    raise FileNotFoundError(f"Could not find the file: {file_path}")

@client.event
async def on_ready():
    logging.info(f'Bot has logged in as {client.user}')
    try:
        await tree.sync()
        logging.info("Slash commands have been successfully synced.")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")

async def create_or_get_thread(session, user_message, channel_id, category_id):
    # Check if a thread already exists for the category or channel
    if category_id in category_threads:
        thread_id = category_threads[category_id]
        logging.info(f"Reusing existing thread for category {category_id}: {thread_id}")
    else:
        logging.info(f"Creating new thread for category {category_id}")
        async with session.post("https://api.openai.com/v1/threads", headers=HEADERS, json={
            "messages": [{"role": "user", "content": user_message}]
        }) as thread_response:
            if thread_response.status != 200:
                raise Exception(f"Error creating thread: {await thread_response.text()}")
            thread_data = await thread_response.json()
            thread_id = thread_data['id']
            category_threads[category_id] = thread_id
            logging.info(f"New thread created for category {category_id} with thread ID: {thread_id}")
    return thread_id

async def send_user_message(session, thread_id, user_message):
    async with session.post(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=HEADERS, json={
        "role": "user",
        "content": user_message
    }) as message_response:
        if message_response.status != 200:
            raise Exception(f"Error sending user message: {await message_response.text()}")

async def start_run(session, thread_id):
    async with session.post(f"https://api.openai.com/v1/threads/{thread_id}/runs", headers=HEADERS, json={
        "assistant_id": ASSISTANT_ID
    }) as run_response:
        if run_response.status != 200:
            raise Exception(f"Error starting run: {await run_response.text()}")
        return await run_response.json()

async def wait_for_run_completion(session, thread_id, run_id):
    while True:
        await asyncio.sleep(1)
        async with session.get(f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}", headers=HEADERS) as run_status_response:
            run_data = await run_status_response.json()
            run_status = run_data['status']
            if run_status == "failed":
                raise Exception("Error: Run failed")
            if run_status not in ["queued", "in_progress"]:
                return run_data

async def fetch_assistant_response(session, thread_id):
    async with session.get(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=HEADERS) as messages_response:
        if messages_response.status != 200:
            raise Exception(f"Error fetching messages: {await messages_response.text()}")
        return await messages_response.json()

def extract_assistant_response(messages_data):
    assistant_response = ""
    for message in messages_data['data']:
        if message['role'] == 'assistant' and 'content' in message:
            content = message['content']
            if isinstance(content, list):
                for segment in content:
                    if isinstance(segment, dict):
                        if 'text' in segment and 'value' in segment['text']:
                            assistant_response += segment['text']['value']
                    elif isinstance(segment, str):
                        assistant_response += segment
            else:
                assistant_response += str(content)
            break
    return assistant_response

async def get_assistant_response(user_message, channel_id, category_id=None):
    try:
        async with aiohttp.ClientSession() as session:
            current_time = datetime.now()
            channel = client.get_channel(channel_id)
            if channel is None:
                return f"Error: Channel {channel_id} not found."

            # Determine category ID
            if category_id is None and channel.category_id:
                category_id = channel.category_id

            # Create or get a thread for the conversation
            thread_id = await create_or_get_thread(session, user_message, channel_id, category_id)

            # Add the user's message to the conversation history
            conversation_key = category_id if category_id else channel_id
            if conversation_key not in category_conversations:
                category_conversations[conversation_key] = []
            category_conversations[conversation_key].append({"role": "user", "content": user_message, "timestamp": current_time})

            # Send user message to the assistant
            await send_user_message(session, thread_id, user_message)

            # Start a run and wait for it to complete
            run_data = await start_run(session, thread_id)
            run_id = run_data['id']
            await wait_for_run_completion(session, thread_id, run_id)

            # Fetch and extract the assistant's response
            messages_data = await fetch_assistant_response(session, thread_id)
            assistant_response = extract_assistant_response(messages_data)

            # Append the assistant's response to the conversation history
            category_conversations[conversation_key].append({"role": "assistant", "content": assistant_response, "timestamp": datetime.now()})

            return assistant_response

    except Exception as e:
        return f"Error during the assistant interaction: {str(e)}"

# Import command definitions from bot_commands.py
bot_commands.setup_commands(tree, get_assistant_response)

# Run the bot
def run_bot():
    client.run(DISCORD_BOT_TOKEN)

if __name__ == '__main__':
    run_bot()
