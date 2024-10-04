# aidm.py
import logging
import bot_commands
from pathlib import Path
from config import DISCORD_BOT_TOKEN, ASSISTANT_ID, client, tree, HEADERS, category_threads, category_conversations, channel_character_sheets
from message_handlers import on_message, send_response_in_chunks
from assistant_interactions import get_assistant_response


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')


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

# Import command definitions from bot_commands.py
bot_commands.setup_commands(tree, get_assistant_response)

# Run the bot
def run_bot():
    client.run(DISCORD_BOT_TOKEN)

if __name__ == '__main__':
    run_bot()
