import logging

from db_repository import build_thread_data_snapshot


category_threads = {}


def save_thread_data(_new_data=None):
    """Refresh the in-memory compatibility snapshot from Supabase."""
    global category_threads
    category_threads = build_thread_data_snapshot()
    logging.info("Refreshed thread data snapshot from Supabase.")
    return category_threads


def load_thread_data():
    """Load the compatibility snapshot from Supabase."""
    global category_threads
    category_threads = build_thread_data_snapshot()
    return category_threads
