import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend folder, then project root
_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env")
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET")
PORT = int(os.getenv("PORT", "3000"))

UPLOAD_DIR = _backend_dir / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:8001")

# Optional local MongoDB URI for development fallback
MONGO_URI_LOCAL = os.getenv("MONGO_URI_LOCAL")

# DEBUG flag to allow insecure TLS for local development (use with caution)
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
