"""
One-time migration: rename 'name' field to 'username' in users collection.
Run from backend folder: python -m migrations.rename_user_name_to_username
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env")
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("MONGO_URI is not set. Add it to backend/.env or project root .env.")
    raise SystemExit(1)


async def run():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client.get_default_database()
    users = db.users
    result = await users.update_many(
        {"name": {"$exists": True}},
        [
            {"$set": {"username": {"$ifNull": ["$username", "$name"]}}},
            {"$unset": "name"},
        ],
    )
    print(f"Rename complete. Matched: {result.matched_count}, Modified: {result.modified_count}")
    client.close()


if __name__ == "__main__":
    asyncio.run(run())
