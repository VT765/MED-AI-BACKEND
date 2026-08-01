import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI, MONGO_URI_LOCAL, DEBUG

client: AsyncIOMotorClient | None = None
db = None


async def connect_db():
    global client, db
    if not MONGO_URI:
        raise RuntimeError(
            "MONGO_URI is not set. Please create a .env file with MONGO_URI set to your MongoDB connection string."
        )

    # Try primary URI first
    try:
        client = AsyncIOMotorClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            tlsAllowInvalidCertificates=DEBUG,
            serverSelectionTimeoutMS=5000,
        )
        # Motor is lazy — force a real connection check
        await client.admin.command("ping")
        print("✅ MongoDB connected (primary URI)")
    except Exception as e:
        print(f"⚠️ Primary MongoDB connection failed: {e}")
        client = None
        if MONGO_URI_LOCAL:
            try:
                print("🔧 Attempting fallback to local MongoDB...")
                client = AsyncIOMotorClient(
                    MONGO_URI_LOCAL,
                    tlsAllowInvalidCertificates=True,
                    serverSelectionTimeoutMS=5000,
                )
                await client.admin.command("ping")
                print("✅ MongoDB connected (local fallback)")
            except Exception as e2:
                raise RuntimeError(
                    f"Failed to connect to both primary and local MongoDB.\n"
                    f"  Primary error: {e}\n"
                    f"  Local error: {e2}"
                )
        else:
            raise RuntimeError(
                f"Failed to connect to MongoDB: {e}\n"
                f"Tip: set MONGO_URI_LOCAL in .env for a local fallback."
            )

    db = client.get_default_database("medai")

    # Auto-expire guest chat sessions after 24 hours of inactivity
    try:
        await db.guest_chat_sessions.create_index(
            "updated_at", expireAfterSeconds=86400
        )
    except Exception:
        pass  # Index may already exist


async def close_db():
    global client
    if client:
        client.close()
        client = None


def get_db():
    if db is None:
        raise RuntimeError("Database not connected")
    return db
