from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from supabase import AsyncClient, acreate_client
from utils import get_logger
from utils.config import (
    APPWRITE_API_KEY,
    APPWRITE_ENDPOINT,
    APPWRITE_PROJECT_ID,
    SUPABASE_KEY,
    SUPABASE_URL,
)

client = Client()
client.set_endpoint(APPWRITE_ENDPOINT)
client.set_project(APPWRITE_PROJECT_ID)
client.set_key(APPWRITE_API_KEY)
database = Databases(client)
storage = Storage(client)

logger = get_logger(__name__)


async def create_supabase():
    supabase: AsyncClient = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase


async def create_member(member: dict):
    supabase = await create_supabase()
    try:
        await supabase.table("members").insert(member).execute()
    except Exception as e:
        logger.error(f"Error creating member: {e}")


async def get_member_by_discord_id(discord_id: int):
    supabase = await create_supabase()
    try:
        res = (
            await supabase.table("members")
            .select("*")
            .eq("discord_id", discord_id)
            .execute()
        )

        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error checking member: {e}")
