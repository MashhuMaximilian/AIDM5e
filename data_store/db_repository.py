import logging
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from config import DIRECT_CONNECTION_STRING, DM_ROLE_NAME, SUPABASE_URL
from config import (
    SUPABASE_DB_HOST,
    SUPABASE_DB_NAME,
    SUPABASE_DB_PASSWORD,
    SUPABASE_DB_PORT,
    SUPABASE_DB_SSLMODE,
    SUPABASE_DB_USER,
)


logger = logging.getLogger(__name__)


DEFAULT_MEMORY_NAMES = ("gameplay", "out-of-game", "dm-private", "worldbuilding")
DEFAULT_CHANNEL_SPECS = (
    {"name": "gameplay", "memory": "gameplay", "always_on": False, "is_dm_private": False},
    {"name": "telldm", "memory": "out-of-game", "always_on": True, "is_dm_private": False},
    {"name": "context", "memory": "out-of-game", "always_on": False, "is_dm_private": False},
    {"name": "session-summary", "memory": "gameplay", "always_on": False, "is_dm_private": False},
    {"name": "feedback", "memory": "gameplay", "always_on": False, "is_dm_private": False},
    {"name": "npcs", "memory": "gameplay", "always_on": False, "is_dm_private": False},
    {"name": "worldbuilding", "memory": "worldbuilding", "always_on": False, "is_dm_private": False},
    {"name": "character-sheets", "memory": "out-of-game", "always_on": False, "is_dm_private": False},
    {"name": "lore-and-teasers", "memory": "gameplay", "always_on": False, "is_dm_private": False},
    {"name": "items", "memory": "out-of-game", "always_on": False, "is_dm_private": False},
    {"name": "dm-planning", "memory": "dm-private", "always_on": False, "is_dm_private": True},
)
DEFAULT_VOICE_CHANNEL_SPECS = (
    {"name": "session-voice", "is_dm_private": False},
)


@dataclass
class CampaignContext:
    guild_id: str
    campaign_id: str


@dataclass
class CampaignImageSettings:
    session_image_mode: str = "off"
    session_image_quality: str = "auto"
    session_image_max_scenes: int | None = None
    session_image_include_dm_context: bool = False
    session_image_post_channel_id: int | None = None


def _connect() -> psycopg.Connection:
    if SUPABASE_DB_HOST and SUPABASE_DB_USER and SUPABASE_DB_PASSWORD:
        return psycopg.connect(
            host=SUPABASE_DB_HOST,
            port=SUPABASE_DB_PORT,
            dbname=SUPABASE_DB_NAME,
            user=SUPABASE_DB_USER,
            password=SUPABASE_DB_PASSWORD,
            sslmode=SUPABASE_DB_SSLMODE,
            row_factory=dict_row,
        )

    if not DIRECT_CONNECTION_STRING:
        raise RuntimeError(
            "Configure DIRECT_CONNECTION_STRING or the SUPABASE_DB_* environment variables."
        )
    connection_string = DIRECT_CONNECTION_STRING
    project_ref = None
    if SUPABASE_URL:
        project_ref = SUPABASE_URL.replace("https://", "").replace("http://", "").split(".")[0]

    if (
        project_ref
        and "pooler.supabase.com" in connection_string
        and "://postgres:" in connection_string
        and f"://postgres.{project_ref}:" not in connection_string
    ):
        connection_string = connection_string.replace("://postgres:", f"://postgres.{project_ref}:", 1)

    if ":[" in connection_string and "]@" in connection_string:
        connection_string = connection_string.replace(":[", ":", 1).replace("]@", "@", 1)

    if connection_string.startswith("postgresql://") and "@" in connection_string:
        without_scheme = connection_string.split("://", 1)[1]
        userinfo, host_and_path = without_scheme.rsplit("@", 1)
        user, password = userinfo.split(":", 1)
        host_port, _, db_and_query = host_and_path.partition("/")
        host, _, port = host_port.partition(":")
        dbname, _, query_string = db_and_query.partition("?")

        connect_kwargs = {
            "host": host,
            "port": int(port or 5432),
            "dbname": dbname or "postgres",
            "user": user,
            "password": password,
            "row_factory": dict_row,
        }
        if "sslmode=require" in query_string or "pooler.supabase.com" in host:
            connect_kwargs["sslmode"] = "require"
        return psycopg.connect(**connect_kwargs)

    return psycopg.connect(connection_string, row_factory=dict_row)


def ensure_runtime_schema() -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("create extension if not exists pgcrypto")
            cur.execute("drop table if exists memory_messages")
            cur.execute("alter table campaigns add column if not exists session_image_mode text not null default 'off'")
            cur.execute("alter table campaigns add column if not exists session_image_quality text not null default 'auto'")
            cur.execute("alter table campaigns add column if not exists session_image_max_scenes integer")
            cur.execute(
                "alter table campaigns add column if not exists session_image_include_dm_context boolean not null default false"
            )
            cur.execute("alter table campaigns add column if not exists session_image_post_channel_id bigint")
        conn.commit()


def _ensure_guild(cur: psycopg.Cursor, discord_guild_id: int, name: str, dm_role_name: str | None = None) -> str:
    cur.execute(
        """
        insert into guilds (discord_guild_id, name, dm_role_name)
        values (%s, %s, %s)
        on conflict (discord_guild_id)
        do update set
          name = excluded.name,
          dm_role_name = excluded.dm_role_name
        returning id
        """,
        (discord_guild_id, name, dm_role_name or DM_ROLE_NAME),
    )
    return str(cur.fetchone()["id"])


def _ensure_campaign(cur: psycopg.Cursor, guild_id: str, discord_category_id: int, name: str) -> str:
    cur.execute(
        """
        insert into campaigns (guild_id, discord_category_id, name)
        values (%s, %s, %s)
        on conflict (discord_category_id)
        do update set
          guild_id = excluded.guild_id,
          name = excluded.name
        returning id
        """,
        (guild_id, discord_category_id, name),
    )
    return str(cur.fetchone()["id"])


def get_or_create_campaign_context(
    discord_guild_id: int,
    guild_name: str,
    discord_category_id: int,
    category_name: str,
    dm_role_name: str | None = None,
) -> CampaignContext:
    with _connect() as conn:
        with conn.cursor() as cur:
            guild_id = _ensure_guild(cur, discord_guild_id, guild_name, dm_role_name)
            campaign_id = _ensure_campaign(cur, guild_id, discord_category_id, category_name)
        conn.commit()
    return CampaignContext(guild_id=guild_id, campaign_id=campaign_id)


def get_campaign_context_by_category(discord_category_id: int) -> CampaignContext | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select campaigns.id as campaign_id, campaigns.guild_id
                from campaigns
                where campaigns.discord_category_id = %s
                """,
                (discord_category_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return CampaignContext(guild_id=str(row["guild_id"]), campaign_id=str(row["campaign_id"]))


def get_campaign_image_settings(discord_category_id: int) -> CampaignImageSettings:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                  session_image_mode,
                  session_image_quality,
                  session_image_max_scenes,
                  session_image_include_dm_context,
                  session_image_post_channel_id
                from campaigns
                where discord_category_id = %s
                """,
                (discord_category_id,),
            )
            row = cur.fetchone()
    if not row:
        return CampaignImageSettings()
    return CampaignImageSettings(
        session_image_mode=row["session_image_mode"] or "off",
        session_image_quality=row["session_image_quality"] or "auto",
        session_image_max_scenes=row["session_image_max_scenes"],
        session_image_include_dm_context=bool(row["session_image_include_dm_context"]),
        session_image_post_channel_id=int(row["session_image_post_channel_id"]) if row["session_image_post_channel_id"] else None,
    )


def update_campaign_image_settings(
    discord_category_id: int,
    *,
    session_image_mode: str | None = None,
    session_image_quality: str | None = None,
    session_image_max_scenes: int | None = None,
    session_image_include_dm_context: bool | None = None,
    session_image_post_channel_id: int | None = None,
) -> CampaignImageSettings:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update campaigns
                set
                  session_image_mode = coalesce(%s, session_image_mode),
                  session_image_quality = coalesce(%s, session_image_quality),
                  session_image_max_scenes = %s,
                  session_image_include_dm_context = coalesce(%s, session_image_include_dm_context),
                  session_image_post_channel_id = %s
                where discord_category_id = %s
                returning
                  session_image_mode,
                  session_image_quality,
                  session_image_max_scenes,
                  session_image_include_dm_context,
                  session_image_post_channel_id
                """,
                (
                    session_image_mode,
                    session_image_quality,
                    session_image_max_scenes,
                    session_image_include_dm_context,
                    session_image_post_channel_id,
                    discord_category_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return CampaignImageSettings()
    return CampaignImageSettings(
        session_image_mode=row["session_image_mode"] or "off",
        session_image_quality=row["session_image_quality"] or "auto",
        session_image_max_scenes=row["session_image_max_scenes"],
        session_image_include_dm_context=bool(row["session_image_include_dm_context"]),
        session_image_post_channel_id=int(row["session_image_post_channel_id"]) if row["session_image_post_channel_id"] else None,
    )


def ensure_memory(campaign_id: str, memory_name: str, provider: str = "gemini", provider_ref: str | None = None) -> str:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into memories (campaign_id, name, provider, provider_ref)
                values (%s, %s, %s, %s)
                on conflict (campaign_id, name)
                do update set
                  provider = excluded.provider,
                  provider_ref = coalesce(memories.provider_ref, excluded.provider_ref)
                returning id
                """,
                (campaign_id, memory_name, provider, provider_ref),
            )
            memory_id = str(cur.fetchone()["id"])
        conn.commit()
    return memory_id


def get_memory_id_by_name(campaign_id: str, memory_name: str) -> str | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id from memories where campaign_id = %s and name = %s",
                (campaign_id, memory_name),
            )
            row = cur.fetchone()
    return str(row["id"]) if row else None


def get_memory_name(memory_id: str) -> str | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select name from memories where id = %s", (memory_id,))
            row = cur.fetchone()
    return row["name"] if row else None


def set_default_memory(campaign_id: str, memory_id: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update campaigns set default_memory_id = %s where id = %s",
                (memory_id, campaign_id),
            )
        conn.commit()


def ensure_channel(
    campaign_id: str,
    discord_channel_id: int,
    name: str,
    always_on: bool = False,
    is_dm_private: bool = False,
) -> str:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into channels (campaign_id, discord_channel_id, name, always_on, is_dm_private)
                values (%s, %s, %s, %s, %s)
                on conflict (discord_channel_id)
                do update set
                  campaign_id = excluded.campaign_id,
                  name = excluded.name,
                  always_on = excluded.always_on,
                  is_dm_private = excluded.is_dm_private
                returning id
                """,
                (campaign_id, discord_channel_id, name, always_on, is_dm_private),
            )
            channel_id = str(cur.fetchone()["id"])
        conn.commit()
    return channel_id


def ensure_channel_for_category(
    discord_category_id: int,
    discord_channel_id: int,
    name: str,
    always_on: bool = False,
    is_dm_private: bool = False,
) -> str:
    context = get_campaign_context_by_category(discord_category_id)
    if not context:
        raise ValueError(f"Campaign for category {discord_category_id} does not exist.")
    return ensure_channel(context.campaign_id, discord_channel_id, name, always_on, is_dm_private)


def ensure_thread(channel_id: str, discord_thread_id: int, name: str, always_on: bool = False) -> str:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into threads (channel_id, discord_thread_id, name, always_on)
                values (%s, %s, %s, %s)
                on conflict (discord_thread_id)
                do update set
                  channel_id = excluded.channel_id,
                  name = excluded.name,
                  always_on = excluded.always_on
                returning id
                """,
                (channel_id, discord_thread_id, name, always_on),
            )
            thread_id = str(cur.fetchone()["id"])
        conn.commit()
    return thread_id


def ensure_thread_for_channel(
    discord_channel_id: int,
    discord_thread_id: int,
    name: str,
    always_on: bool = False,
) -> str:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from channels where discord_channel_id = %s", (discord_channel_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Channel {discord_channel_id} is not registered in the database.")
    return ensure_thread(str(row["id"]), discord_thread_id, name, always_on)


def assign_memory_to_channel(discord_channel_id: int, memory_id: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from channels where discord_channel_id = %s", (discord_channel_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Channel {discord_channel_id} is not registered in the database.")
            cur.execute(
                """
                insert into channel_memory_assignments (channel_id, memory_id)
                values (%s, %s)
                on conflict (channel_id)
                do update set memory_id = excluded.memory_id
                """,
                (row["id"], memory_id),
            )
        conn.commit()


def assign_memory_to_thread(discord_thread_id: int, memory_id: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from threads where discord_thread_id = %s", (discord_thread_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Thread {discord_thread_id} is not registered in the database.")
            cur.execute(
                """
                insert into thread_memory_assignments (thread_id, memory_id)
                values (%s, %s)
                on conflict (thread_id)
                do update set memory_id = excluded.memory_id
                """,
                (row["id"], memory_id),
            )
        conn.commit()


def set_channel_always_on(discord_channel_id: int, always_on: bool) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update channels set always_on = %s where discord_channel_id = %s",
                (always_on, discord_channel_id),
            )
        conn.commit()


def set_thread_always_on(discord_thread_id: int, always_on: bool) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update threads set always_on = %s where discord_thread_id = %s",
                (always_on, discord_thread_id),
            )
        conn.commit()


def get_default_memory_id(discord_category_id: int) -> str | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select campaigns.default_memory_id
                from campaigns
                where campaigns.discord_category_id = %s
                """,
                (discord_category_id,),
            )
            row = cur.fetchone()
    return str(row["default_memory_id"]) if row and row["default_memory_id"] else None


def get_assigned_memory_id(discord_channel_id: int, discord_category_id: int, discord_thread_id: int | None = None) -> str | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            if discord_thread_id:
                cur.execute(
                    """
                    select tma.memory_id
                    from threads t
                    join thread_memory_assignments tma on tma.thread_id = t.id
                    where t.discord_thread_id = %s
                    """,
                    (discord_thread_id,),
                )
                row = cur.fetchone()
                if row:
                    return str(row["memory_id"])

            cur.execute(
                """
                select cma.memory_id
                from channels c
                join channel_memory_assignments cma on cma.channel_id = c.id
                where c.discord_channel_id = %s
                """,
                (discord_channel_id,),
            )
            row = cur.fetchone()
            if row:
                return str(row["memory_id"])

            cur.execute(
                """
                select default_memory_id
                from campaigns
                where discord_category_id = %s
                """,
                (discord_category_id,),
            )
            row = cur.fetchone()
    return str(row["default_memory_id"]) if row and row["default_memory_id"] else None


def is_always_on(discord_channel_id: int, discord_thread_id: int | None = None) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            if discord_thread_id:
                cur.execute(
                    "select always_on from threads where discord_thread_id = %s",
                    (discord_thread_id,),
                )
                row = cur.fetchone()
                if row and row["always_on"]:
                    return True

            cur.execute(
                "select always_on from channels where discord_channel_id = %s",
                (discord_channel_id,),
            )
            row = cur.fetchone()
    return bool(row and row["always_on"])


def delete_memory(memory_name_or_id: str, discord_category_id: int) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select memories.id, memories.name, campaigns.default_memory_id
                from memories
                join campaigns on campaigns.id = memories.campaign_id
                where campaigns.discord_category_id = %s
                  and (memories.name = %s or memories.id::text = %s)
                """,
                (discord_category_id, memory_name_or_id, memory_name_or_id),
            )
            row = cur.fetchone()
            if not row:
                return False
            if row["default_memory_id"] == row["id"]:
                raise ValueError("Cannot delete the campaign's default memory.")

            cur.execute("delete from channel_memory_assignments where memory_id = %s", (row["id"],))
            cur.execute("delete from thread_memory_assignments where memory_id = %s", (row["id"],))
            cur.execute("delete from memories where id = %s", (row["id"],))
        conn.commit()
    return True


def delete_thread_record(discord_thread_id: int) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from threads where discord_thread_id = %s", (discord_thread_id,))
        conn.commit()


def delete_channel_record(discord_channel_id: int) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from channels where discord_channel_id = %s", (discord_channel_id,))
        conn.commit()


def get_campaign_runtime_targets(discord_category_id: int) -> dict[str, list[int]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id
                from campaigns
                where discord_category_id = %s
                """,
                (discord_category_id,),
            )
            campaign = cur.fetchone()
            if not campaign:
                return {"channel_ids": [], "thread_ids": []}

            campaign_id = campaign["id"]

            cur.execute(
                """
                select discord_channel_id
                from channels
                where campaign_id = %s
                order by discord_channel_id
                """,
                (campaign_id,),
            )
            channel_rows = cur.fetchall()

            cur.execute(
                """
                select threads.discord_thread_id
                from threads
                join channels on channels.id = threads.channel_id
                where channels.campaign_id = %s
                order by threads.discord_thread_id
                """,
                (campaign_id,),
            )
            thread_rows = cur.fetchall()

    return {
        "channel_ids": [int(row["discord_channel_id"]) for row in channel_rows if row["discord_channel_id"] is not None],
        "thread_ids": [int(row["discord_thread_id"]) for row in thread_rows if row["discord_thread_id"] is not None],
    }


def delete_campaign_record(discord_category_id: int) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, guild_id
                from campaigns
                where discord_category_id = %s
                """,
                (discord_category_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return

            campaign_id = row["id"]
            guild_id = row["guild_id"]

            cur.execute(
                """
                delete from thread_memory_assignments
                where thread_id in (
                  select threads.id
                  from threads
                  join channels on channels.id = threads.channel_id
                  where channels.campaign_id = %s
                )
                """,
                (campaign_id,),
            )
            cur.execute(
                """
                delete from channel_memory_assignments
                where channel_id in (
                  select id
                  from channels
                  where campaign_id = %s
                )
                """,
                (campaign_id,),
            )
            cur.execute(
                """
                delete from threads
                where channel_id in (
                  select id
                  from channels
                  where campaign_id = %s
                )
                """,
                (campaign_id,),
            )
            cur.execute("delete from channels where campaign_id = %s", (campaign_id,))
            cur.execute("delete from memories where campaign_id = %s", (campaign_id,))
            cur.execute("delete from campaigns where id = %s", (campaign_id,))
            cur.execute(
                """
                delete from guilds
                where id = %s
                  and not exists (
                    select 1
                    from campaigns
                    where guild_id = %s
                  )
                """,
                (guild_id, guild_id),
            )
        conn.commit()


def build_thread_data_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                  campaigns.id as campaign_id,
                  campaigns.discord_category_id,
                  campaigns.name,
                  campaigns.default_memory_id,
                  memories.id as memory_id,
                  memories.name as memory_name
                from campaigns
                left join memories on memories.campaign_id = campaigns.id
                order by campaigns.name, memories.name
                """
            )
            campaigns = cur.fetchall()

            cur.execute(
                """
                select
                  channels.id as channel_db_id,
                  channels.campaign_id,
                  channels.discord_channel_id,
                  channels.name,
                  channels.always_on,
                  cma.memory_id as assigned_memory_id,
                  memories.name as assigned_memory_name
                from channels
                left join channel_memory_assignments cma on cma.channel_id = channels.id
                left join memories on memories.id = cma.memory_id
                order by channels.name
                """
            )
            channels = cur.fetchall()

            cur.execute(
                """
                select
                  threads.channel_id,
                  threads.discord_thread_id,
                  threads.name,
                  threads.always_on,
                  tma.memory_id as assigned_memory_id,
                  memories.name as assigned_memory_name
                from threads
                left join thread_memory_assignments tma on tma.thread_id = threads.id
                left join memories on memories.id = tma.memory_id
                order by threads.name
                """
            )
            threads = cur.fetchall()

    channel_map_by_db_id: dict[str, dict[str, Any]] = {}
    campaign_db_to_discord: dict[str, str] = {}
    memory_maps: dict[str, dict[str, str]] = {}

    for row in campaigns:
        campaign_key = str(row["discord_category_id"])
        campaign_db_to_discord[str(row["campaign_id"])] = campaign_key
        campaign_entry = snapshot.setdefault(
            campaign_key,
            {
                "name": row["name"],
                "default_memory": None,
                "memory_threads": {},
                "channels": {},
            },
        )
        if row["memory_id"]:
            memory_id = str(row["memory_id"])
            campaign_entry["memory_threads"][row["memory_name"]] = memory_id
            memory_maps.setdefault(campaign_key, {})[memory_id] = row["memory_name"]
            if row["default_memory_id"] == row["memory_id"]:
                campaign_entry["default_memory"] = row["memory_name"]

    for row in channels:
        campaign_key = campaign_db_to_discord.get(str(row["campaign_id"]))
        if not campaign_key:
            continue
        channel_entry = {
            "name": row["name"],
            "assigned_memory": str(row["assigned_memory_id"]) if row["assigned_memory_id"] else None,
            "memory_name": row["assigned_memory_name"],
            "always_on": row["always_on"],
            "threads": {},
        }
        snapshot[campaign_key]["channels"][str(row["discord_channel_id"])] = channel_entry
        channel_map_by_db_id[str(row["channel_db_id"])] = channel_entry

    for row in threads:
        channel_entry = channel_map_by_db_id.get(str(row["channel_id"]))
        if not channel_entry:
            continue
        channel_entry["threads"][str(row["discord_thread_id"])] = {
            "name": row["name"],
            "assigned_memory": str(row["assigned_memory_id"]) if row["assigned_memory_id"] else None,
            "memory_name": row["assigned_memory_name"],
            "always_on": row["always_on"],
        }

    return snapshot


def list_memory_names(discord_category_id: int) -> list[str]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select memories.name
                from memories
                join campaigns on campaigns.id = memories.campaign_id
                where campaigns.discord_category_id = %s
                order by memories.name
                """,
                (discord_category_id,),
            )
            rows = cur.fetchall()
    return [row["name"] for row in rows]


def fetch_memory_details(discord_category_id: int, discord_channel_id: int, discord_thread_id: int | None = None) -> dict[str, Any] | None:
    snapshot = build_thread_data_snapshot()
    category_data = snapshot.get(str(discord_category_id))
    if not category_data:
        return None
    channel_data = category_data["channels"].get(str(discord_channel_id))
    if not channel_data:
        return None
    if discord_thread_id:
        thread_data = channel_data["threads"].get(str(discord_thread_id))
        if thread_data:
            return {
                "memory_id": thread_data.get("assigned_memory") or channel_data.get("assigned_memory"),
                "memory_name": thread_data.get("memory_name") or channel_data.get("memory_name"),
                "always_on": thread_data.get("always_on", channel_data.get("always_on", False)),
            }
    return {
        "memory_id": channel_data.get("assigned_memory"),
        "memory_name": channel_data.get("memory_name"),
        "always_on": channel_data.get("always_on", False),
    }
