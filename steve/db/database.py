from typing import Optional

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

# --- Appwrite (still backs people, meetings, and recording storage) ---
client = Client()
client.set_endpoint(APPWRITE_ENDPOINT)
client.set_project(APPWRITE_PROJECT_ID)
client.set_key(APPWRITE_API_KEY)
database = Databases(client)
storage = Storage(client)

logger = get_logger(__name__)

# Profile role assigned to members who verify through Discord.
# Must be a value of the `profile_role` enum (client | director | member).
DEFAULT_MEMBER_ROLE = "member"


class VerificationError(Exception):
    """A verification could not be completed safely (e.g. an email claim that
    would rebind or escalate an existing account). The message is safe to show
    to the end user."""

# Cached Supabase client. The bot writes to `profiles` (RLS-protected), so
# SUPABASE_KEY MUST be the service-role key to bypass RLS.
_supabase: Optional[AsyncClient] = None


async def get_supabase() -> AsyncClient:
    """Return a lazily-created, process-wide Supabase client."""
    global _supabase
    if _supabase is None:
        _supabase = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


async def get_member_by_discord_id(discord_id: int) -> Optional[dict]:
    """Return the `profiles` row linked to this Discord user, or None.

    Used as the "is this user already verified?" check.
    """
    supabase = await get_supabase()
    try:
        res = (
            await supabase.table("profiles")
            .select("*")
            .eq("discord_id", discord_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error checking profile by discord_id: {e}")
        raise


async def get_profile_by_email(email: str) -> Optional[dict]:
    """Return an existing `profiles` row matching this email, or None."""
    supabase = await get_supabase()
    try:
        res = (
            await supabase.table("profiles")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error checking profile by email: {e}")
        raise


async def verify_member(
    *, name: str, eid: str, email: str, discord_id: int, trusted: bool = False
) -> Optional[dict]:
    """Link or create a member profile for a verifying Discord user.

    - If a profile already exists for this email (e.g. a real member account
      created through the website), attach the Discord identity to it and fill
      in any missing eid/name.
    - Otherwise, insert a standalone member profile that is not tied to an
      auth.users account (`uid` is left NULL).

    Security: on the self-serve verification path the `email` is supplied by an
    untrusted Discord user, so it cannot be used to claim an arbitrary account.
    When ``trusted`` is False we refuse to:
      * rebind a profile that is already linked to a *different* Discord account, or
      * link an unverified email claim onto a non-``member`` (elevated) profile.
    The admin command (gated on Discord ``administrator``) passes ``trusted=True``.

    Returns the resulting profile row, or None on failure.
    Raises VerificationError when a link is refused for safety reasons.
    """
    supabase = await get_supabase()
    existing = await get_profile_by_email(email)

    if existing:
        if not trusted:
            existing_discord = existing.get("discord_id")
            if existing_discord and existing_discord != discord_id:
                raise VerificationError(
                    "That email is already linked to another Discord account."
                )
            if existing.get("role") != DEFAULT_MEMBER_ROLE:
                raise VerificationError(
                    "That email belongs to a staff account and must be linked "
                    "by a Director."
                )

        updates: dict = {"discord_id": discord_id}
        if not existing.get("eid"):
            updates["eid"] = eid
        if not existing.get("name"):
            updates["name"] = name

        try:
            res = (
                await supabase.table("profiles")
                .update(updates)
                .eq("id", existing["id"])
                .execute()
            )
        except Exception as e:
            logger.error(f"Error linking member profile: {e}")
            raise
        return res.data[0] if res.data else existing

    try:
        res = (
            await supabase.table("profiles")
            .insert(
                {
                    "uid": None,
                    "name": name,
                    "email": email,
                    "eid": eid,
                    "discord_id": discord_id,
                    "role": DEFAULT_MEMBER_ROLE,
                }
            )
            .execute()
        )
    except Exception as e:
        logger.error(f"Error creating member profile: {e}")
        raise
    return res.data[0] if res.data else None
