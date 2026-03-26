import logging
import mimetypes
from pathlib import Path
from urllib.parse import quote

import requests

from config import DISCORD_GUILD_ID, SUPABASE_SERVICE_KEY, SUPABASE_STORAGE_BUCKET, SUPABASE_URL


logger = logging.getLogger(__name__)


def _storage_headers(content_type: str) -> dict[str, str]:
    if not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_KEY is not configured.")
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "x-upsert": "true",
        "Content-Type": content_type,
    }


def _bucket_endpoint() -> str:
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured.")
    return f"{SUPABASE_URL.rstrip('/')}/storage/v1/bucket"


def _object_endpoint(bucket_name: str, object_path: str) -> str:
    return f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket_name}/{quote(object_path, safe='/')}"


def ensure_storage_bucket(bucket_name: str = SUPABASE_STORAGE_BUCKET) -> None:
    response = requests.get(
        f"{_bucket_endpoint()}/{bucket_name}",
        headers=_storage_headers("application/json"),
        timeout=30,
    )
    if response.status_code == 200:
        return
    if response.status_code not in {400, 404}:
        response.raise_for_status()

    create_response = requests.post(
        _bucket_endpoint(),
        headers=_storage_headers("application/json"),
        json={"id": bucket_name, "name": bucket_name, "public": False},
        timeout=30,
    )
    if create_response.status_code not in {200, 201, 409}:
        create_response.raise_for_status()


def upload_session_artifacts_for_guild(
    *,
    guild_id: int,
    audio_files: list[Path],
    transcript_path: Path,
    manifest_path: Path,
    bucket_name: str = SUPABASE_STORAGE_BUCKET,
) -> list[str]:
    if not DISCORD_GUILD_ID or str(guild_id) != str(DISCORD_GUILD_ID):
        logger.info(
            "Skipping Supabase storage upload for guild %s because it does not match configured DISCORD_GUILD_ID.",
            guild_id,
        )
        return []
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.info("Skipping Supabase storage upload because storage credentials are incomplete.")
        return []

    ensure_storage_bucket(bucket_name)

    uploaded_paths: list[str] = []
    base_prefix = f"guild_{guild_id}/sessions"
    files_to_upload = [path for path in [*audio_files, transcript_path, manifest_path] if path.exists()]

    for path in files_to_upload:
        object_path = f"{base_prefix}/{path.name}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        response = requests.post(
            _object_endpoint(bucket_name, object_path),
            headers=_storage_headers(content_type),
            data=path.read_bytes(),
            timeout=120,
        )
        if response.status_code not in {200, 201}:
            response.raise_for_status()
        uploaded_paths.append(object_path)

    return uploaded_paths
