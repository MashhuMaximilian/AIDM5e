# assistant_interactions.py

import aiohttp
import logging
from datetime import datetime
from config import HEADERS, ASSISTANT_ID, category_threads, category_conversations, client
import asyncio
from shared_functions import send_response_in_chunks



async def send_user_message(session, thread_id, user_message):
    """Send user message to the assistant."""
    async with session.post(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=HEADERS, json={
        "role": "user",
        "content": user_message
    }) as message_response:
        if message_response.status != 200:
            raise Exception(f"Error sending user message: {await message_response.text()}")

async def start_run(session, thread_id):
    """Start a run for the conversation."""
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
                logging.error(f"Run failed with details: {run_data}")
                raise Exception(f"Error: Run failed with details: {run_data}")
            if run_status not in ["queued", "in_progress"]:
                return run_data

async def fetch_assistant_response(session, thread_id):
    """Fetch the assistant's response from the thread."""
    async with session.get(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=HEADERS) as messages_response:
        if messages_response.status != 200:
            raise Exception(f"Error fetching messages: {await messages_response.text()}")
        return await messages_response.json()

def extract_assistant_response(messages_data):
    """Extract the assistant's response from the fetched messages."""
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


async def get_assistant_response(user_message, channel_id, category_id=None, thread_id=None, assigned_memory=None, send_message=False):  # Changed default to False
    """Main function to interact with the assistant and return the response."""
    try:
        async with aiohttp.ClientSession() as session:
            channel = client.get_channel(channel_id)

            if channel is None:
                error_message = f"Error: Channel with ID {channel_id} not found."
                logging.error(error_message)
                return error_message

            if not assigned_memory or assigned_memory.startswith("'") or assigned_memory.endswith("'") or assigned_memory.endswith("."):
                error_message = "Assigned memory ID is invalid or empty."
                logging.error(error_message)
                return error_message

            assigned_memory = assigned_memory.strip("'\". ")

            # Start typing indicator while processing
            async with channel.typing():
                await send_user_message(session, assigned_memory, user_message)

                run_data = await start_run(session, assigned_memory)
                run_id = run_data['id']
                await wait_for_run_completion(session, assigned_memory, run_id)

                messages_data = await fetch_assistant_response(session, assigned_memory)
                assistant_response = extract_assistant_response(messages_data)

                if not assistant_response:
                    logging.error("No valid response received from the assistant.")
                    return "No valid response received from the assistant."

                logging.info(f"Assistant responded in memory '{assigned_memory}': {assistant_response[:100]}")
                if send_message:  # Now only sends when explicitly requested
                    await send_response_in_chunks(channel, assistant_response)
                return assistant_response

    except Exception as e:
        logging.error(f"Error during the assistant interaction: {str(e)}")
        return f"Error during the assistant interaction: {str(e)}"