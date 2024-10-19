# assistant_interactions.py

import aiohttp
import logging
from datetime import datetime
from config import HEADERS, ASSISTANT_ID, category_threads, category_conversations, client
import asyncio

async def create_or_get_thread(session, user_message, channel_id, category_id):
    """Create a new thread or get the existing one for the conversation."""
    
    # Check if a thread already exists for the category
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
            category_threads[category_id] = thread_id  # Store thread ID for the category
            logging.info(f"New thread created for category {category_id} with thread ID: {thread_id}")
    
    # Optionally store the conversation history in case you want to keep track
    if category_id not in category_conversations:
        category_conversations[category_id] = []
    
    return thread_id

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
    """Wait for the assistant run to complete."""
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

async def get_assistant_response(user_message, channel_id, category_id=None):
    """Main function to interact with the assistant and return the response."""
    try:
        async with aiohttp.ClientSession() as session:
            current_time = datetime.now()
            channel = client.get_channel(channel_id)

            # Log the channel ID for debugging purposes
            logging.info(f"Attempting to fetch channel with ID: {channel_id}")
            
            if channel is None:
                error_message = f"Error: Channel with ID {channel_id} not found."
                logging.error(error_message)
                return error_message  # Return an error message without sending to Discord

            # Determine category ID
            if category_id is None and channel.category_id:
                category_id = channel.category_id

            # Create or get a thread for the conversation
            thread_id = await create_or_get_thread(session, user_message, channel_id, category_id)

            # Log the user message being sent
            logging.info(f"Sending user message to assistant: {user_message[:100]}")

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
        logging.error(f"Error during the assistant interaction: {str(e)}")  # Log the error
        return f"Error during the assistant interaction: {str(e)}"
