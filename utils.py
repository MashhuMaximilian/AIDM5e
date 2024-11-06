from pathlib import Path
import logging
import json
import os


category_threads = {}
# Path to store thread data
thread_data_path = Path(__file__).parent.resolve() / 'threads.json'


def save_thread_data(new_data):
    """Save thread data to a JSON file."""
    global category_threads

    try:
        with open(thread_data_path, 'w') as json_file:
            json.dump(new_data, json_file, indent=4)  # Ensure indentation for readability

        category_threads = new_data
        logging.info("Thread data saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save thread data: {e}")

def load_thread_data():
    """Load thread data from the JSON file."""
    global category_threads  # Ensure we're using the global variable

    if os.path.exists(thread_data_path):
        if os.path.getsize(thread_data_path) == 0:
            logging.error("Thread data file is empty. Initializing an empty dictionary.")
            category_threads = {}
        else:
            with open(thread_data_path, 'r') as f:
                try:
                    category_threads = json.load(f)
                    logging.info(f"Loaded thread data: {str(category_threads)[-100:]}")
                except json.JSONDecodeError as e:
                    logging.error(f"Error loading JSON data: {e}. Initializing empty thread data.")
                    category_threads = {}
    else:
        logging.warning("Thread data file not found. Initializing empty thread data.")
        category_threads = {}

    return category_threads  # Return loaded data

