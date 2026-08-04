import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from config import JWT_SECRET, MONGO_URI, OPENAI_API_KEY, PORT, UPLOAD_DIR
from database import close_db, connect_db
from routers import auth, chat, documents, report, profile

if not MONGO_URI:
    print(
        "MONGO_URI is not set. Please create a .env file in the project root or backend folder with MONGO_URI set to your MongoDB connection string."
    )
if not OPENAI_API_KEY:
    print(
        "OPENAI_API_KEY is not set. The /api/chat endpoint will not work until you add OPENAI_API_KEY to your .env."
    )
if not JWT_SECRET:
    print("JWT_SECRET is not set. Please add JWT_SECRET to your .env file.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(title="Med-AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail} if isinstance(exc.detail, str) else exc.detail,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "Validation error"
    if errors:
        first = errors[0]
        loc = first.get("loc", ())
        err_msg = str(first.get("msg", ""))
        err_type = str(first.get("type", ""))
        if "missing" in err_type or "required" in err_type:
            msg = "Please fill in all fields"
        elif "password" in str(loc) and "at least 6" in err_msg:
            msg = "Password must be at least 6 characters"
        elif "email" in str(loc) and "valid" in err_msg.lower():
            msg = "Invalid email format"
        else:
            msg = err_msg or msg
    return JSONResponse(status_code=400, content={"message": msg})


@app.middleware("http")
async def log_requests(request, call_next):
    print(f"[{datetime.utcnow().isoformat()}Z] {request.method} {request.url.path}")
    return await call_next(request)


# Static files for uploads (serve from backend/uploads as /uploads)
uploads_path = Path(__file__).resolve().parent / "uploads"
uploads_path.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(report.router)
app.include_router(chat.router)
app.include_router(profile.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=PORT,
        reload=True,
    )
