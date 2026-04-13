import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TOKEN = _require("TOKEN")
GEMINI_API_KEY = _require("GEMINI_API_KEY")
APPWRITE_ENDPOINT = _require("APPWRITE_ENDPOINT")
APPWRITE_API_KEY = _require("APPWRITE_API_KEY")
APPWRITE_PROJECT_ID = _require("APPWRITE_PROJECT_ID")
APPWRITE_DB_ID = _require("APPWRITE_DB_ID")
APPWRITE_COLLECTION_ID_MEETINGS = _require("APPWRITE_COLLECTION_ID_MEETINGS")
APPWRITE_COLLECTION_ID_PEOPLE = _require("APPWRITE_COLLECTION_ID_PEOPLE")
APPWRITE_BUCKET_ID_MEETINGS = _require("APPWRITE_BUCKET_ID_MEETINGS")
ASSEMBLYAI_API_KEY = _require("ASSEMBLYAI_API_KEY")
LLM_MODEL = "gemini-2.5-flash-lite-preview-06-17"

SUPABASE_URL = _require("SUPABASE_URL")
SUPABASE_KEY = _require("SUPABASE_KEY")

SBI_GUILD_ID = int(_require("SBI_GUILD_ID"))
VERIFICATION_CHANNEL_ID = int(_require("VERIFICATION_CHANNEL_ID"))
GENERAL_MEMBER_ROLE_ID = int(_require("GENERAL_MEMBER_ROLE_ID"))
BOT_ADMIN_IDS = [int(x) for x in os.getenv("BOT_ADMIN_IDS", "").split(",") if x]
