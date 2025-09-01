import asyncio
import json
from typing import Optional

from appwrite.id import ID
from utils import get_logger
from utils.config import (
    APPWRITE_COLLECTION_ID_PEOPLE,
    APPWRITE_DB_ID,
)

from .database import database
from .types import Person

logger = get_logger(__name__)


async def create_person(person: Person) -> Optional[Person]:
    """Create a person in the Appwrite database.

    Args:
        person (Person): Person instance to create in the database

    Returns:
        Optional[Person]: Person instance with ID if successful, None if failed
    """
    try:
        response = await asyncio.to_thread(
            database.create_document,
            database_id=APPWRITE_DB_ID,
            collection_id=APPWRITE_COLLECTION_ID_PEOPLE,
            document_id=ID.unique(),
            data=person.to_dict(),
        )

        logger.info(f"Person created successfully: {response}")

        # Return a new Person instance with the ID from Appwrite
        return Person(
            id=response["$id"],
            name=response["name"],
            discord_id=response["discord_id"],
            eid=response.get("eid"),
            email=response.get("email"),
        )
    except Exception as e:
        logger.error(f"Failed to create person: {e}")
        return None


async def get_person(id: str) -> Optional[Person]:
    try:
        response = await asyncio.to_thread(
            database.get_document,
            database_id=APPWRITE_DB_ID,
            collection_id=APPWRITE_COLLECTION_ID_PEOPLE,
            document_id=id,
        )

        # Map Appwrite response to Person model
        return Person(
            id=response["$id"],
            name=response["name"],
            discord_id=response["discord_id"],
            eid=response.get("eid"),
            email=response.get("email"),
        )
    except Exception as e:
        logger.error(f"Failed to get person: {e}")
        return None


async def update_person(id: str, person: Person) -> bool:
    """Update a person in the Appwrite database.

    Args:
        id (str): Document ID of the person to update
        person (Person): Person instance with updated data

    Returns:
        bool: True if successful, False if failed
    """
    try:
        response = await asyncio.to_thread(
            database.update_document,
            database_id=APPWRITE_DB_ID,
            collection_id=APPWRITE_COLLECTION_ID_PEOPLE,
            document_id=id,
            data=person.to_dict(),
        )
        logger.info(f"Person updated successfully: {response}")
        return True
    except Exception as e:
        logger.error(f"Error updating person: {e}")
        return False


async def export_all():
    try:
        response = await asyncio.to_thread(
            database.list_documents,
            database_id=APPWRITE_DB_ID,
            collection_id=APPWRITE_COLLECTION_ID_PEOPLE,
            # collection_id=APPWRITE_COLLECTION_ID_MEETINGS,
        )

        # Write response to JSON file
        with open("meeting_export.json", "w") as f:
            json.dump(response, f, indent=2)

        logger.info("Successfully exported all people to meeting_export.json")
        return response

    except Exception as e:
        logger.error(f"Error listing people: {e}")
        return []
