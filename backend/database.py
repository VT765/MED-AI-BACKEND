import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI

client: AsyncIOMotorClient | None = None
db = None


async def connect_db():
    global client, db
    if not MONGO_URI:
        raise RuntimeError(
            "MONGO_URI is not set. Please create a .env file with MONGO_URI set to your MongoDB connection string."
        )
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client.get_default_database("medai")
    print("✅ MongoDB connected")


async def close_db():
    global client
    if client:
        client.close()
        client = None


def get_db():
    if db is None:
        raise RuntimeError("Database not connected")
    return db
