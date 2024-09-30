# aidm.py

import discord
import aiohttp
import openai
import os
import asyncio  # Ensure this is included
import logging
from datetime import datetime
import bot_commands  # No circular import here
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from a specific path
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)
# Load the environment variables from the .env file

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Set up Discord bot client
intents = discord.Intents.default()
intents.message_content = True  # Enable reading messages
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

# Get the tokens and API keys from the environment variables
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN') 
openai.api_key =  os.getenv('OPENAI_API_KEY')
ASSISTANT_ID = os.getenv('ASSISTANT_ID')

# Headers for OpenAI API requests
HEADERS = {
    'Authorization': f'Bearer {openai.api_key}',
    'Content-Type': 'application/json',
    'OpenAI-Beta': 'assistants=v2'
}

# Store thread ID and conversation history for each category
category_threads = {}
category_conversations = {}
channel_character_sheets = {}

# Load your prompt from a file
with open('aidm_prompt.txt', 'r') as f:
# with open('/home/m_catalin_ion/aidm5e_discord/aidm_prompt.txt', 'r') as f: # this is useful when uploading to VM bc it has an issue with the one before
    system_prompt = f.read()


@client.event
async def on_ready():
    logging.info(f'Bot has logged in as {client.user}')
    try:
        await tree.sync()
        logging.info("Slash commands have been successfully synced.")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")

async def get_assistant_response(user_message, channel_id, category_id=None):
    try:
        async with aiohttp.ClientSession() as session:
            current_time = datetime.now()

            # Get the channel object from the client to fetch category_id if it's not provided
            channel = client.get_channel(channel_id)
            if channel is None:
                return f"Error: Channel {channel_id} not found."

            # Fetch the category ID from the channel if it's not already provided
            if category_id is None and channel.category_id:
                category_id = channel.category_id

            # Determine if the channel is part of a category
            if category_id:
                # Reuse or create a thread for the category
                if category_id in category_threads:
                    thread_id = category_threads[category_id]
                    print(f"Reusing existing thread for category {category_id}: {thread_id}")
                else:
                    print(f"Creating new thread for category {category_id}")
                    async with session.post("https://api.openai.com/v1/threads", headers=HEADERS, json={
                        "messages": [{"role": "user", "content": user_message}]
                    }) as thread_response:
                        if thread_response.status != 200:
                            return f"Error creating thread: {await thread_response.text()}"
                        thread_data = await thread_response.json()
                        thread_id = thread_data['id']
                        category_threads[category_id] = thread_id  # Store thread ID for the category
                        category_conversations[category_id] = [{"role": "user", "content": user_message, "timestamp": current_time}]
                        print(f"New thread created for category {category_id} with thread ID: {thread_id}")
            else:
                # If no category ID is available, handle channel-specific threads
                if channel_id in category_threads:
                    thread_id = category_threads[channel_id]
                    print(f"Reusing existing thread for channel {channel_id} (no category): {thread_id}")
                else:
                    print(f"Creating new thread for channel {channel_id} (no category)")
                    async with session.post("https://api.openai.com/v1/threads", headers=HEADERS, json={
                        "messages": [{"role": "user", "content": user_message}]
                    }) as thread_response:
                        if thread_response.status != 200:
                            return f"Error creating thread: {await thread_response.text()}"
                        thread_data = await thread_response.json()
                        thread_id = thread_data['id']
                        category_threads[channel_id] = thread_id  # Store thread ID for the channel
                        category_conversations[channel_id] = [{"role": "user", "content": user_message, "timestamp": current_time}]
                        print(f"New thread created for channel {channel_id} (no category) with thread ID: {thread_id}")
            
            # Add the user's message to the conversation history with timestamp
            conversation_key = category_id if category_id else channel_id
            category_conversations[conversation_key].append({"role": "user", "content": user_message, "timestamp": current_time})

            # Send the new user message to the assistant
            async with session.post(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=HEADERS, json={
                "role": "user",
                "content": user_message
            }) as message_response:
                if message_response.status != 200:
                    return f"Error sending user message: {await message_response.text()}"

            # Start a run with the assistant using the ASSISTANT_ID
            async with session.post(f"https://api.openai.com/v1/threads/{thread_id}/runs", headers=HEADERS, json={
                "assistant_id": ASSISTANT_ID
            }) as run_response:
                if run_response.status != 200:
                    return f"Error starting run: {await run_response.text()}"
                run_data = await run_response.json()
                run_id = run_data['id']

            # Poll until the run is complete
            run_status = run_data['status']
            while run_status in ["queued", "in_progress"]:
                await asyncio.sleep(1)
                async with session.get(f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}", headers=HEADERS) as run_status_response:
                    run_data = await run_status_response.json()
                    run_status = run_data['status']

            if run_status == "failed":
                return "Error: Run failed"

            # Fetch the assistant's response
            async with session.get(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=HEADERS) as messages_response:
                if messages_response.status != 200:
                    return f"Error fetching messages: {await messages_response.text()}"
                messages_data = await messages_response.json()

            # Extract the assistant's response
            assistant_response = ""
            for message in messages_data['data']:
                if message['role'] == 'assistant' and 'content' in message:
                    content = message['content']

                    # If content is a list (can contain dicts or strings), handle each item
                    if isinstance(content, list):
                        for segment in content:
                            if isinstance(segment, dict):
                                # Extract 'value' field if it exists within a 'text' dict
                                if 'text' in segment and 'value' in segment['text']:
                                    assistant_response += segment['text']['value']
                            elif isinstance(segment, str):
                                assistant_response += segment
                    else:
                        # Handle cases where content is a plain string
                        assistant_response += str(content)
                    break

            # Append the assistant's response to the conversation history with timestamp
            category_conversations[conversation_key].append({"role": "assistant", "content": assistant_response, "timestamp": datetime.now()})

            return assistant_response

    except Exception as e:
        return f"Error during the assistant interaction: {str(e)}"

# Import command definitions from bot_commands.py and pass required objects
bot_commands.setup_commands(tree, get_assistant_response)


# Run the bot
def run_bot():
    client.run(DISCORD_BOT_TOKEN)

if __name__ == '__main__':
    run_bot()