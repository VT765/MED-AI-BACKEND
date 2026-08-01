# Med-AI Backend

FastAPI backend for Med-AI (auth, chat, documents, report analysis).

## Prerequisites

- Python 3.11+
- MongoDB Atlas (or local MongoDB) — set `MONGO_URI` in `backend/.env`
- [Groq API key](https://console.groq.com/) — set `GROQ_API_KEY` for AI chat and report analysis
- Optional: [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for image report uploads (`brew install tesseract` on macOS)

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # then edit .env with your keys
```

## Run (development)

You need **two processes**: the main API (port 8000) and the LLM microservice (port 8001).

**Option A — helper script (recommended):**

```bash
./scripts/dev.sh
```

**Option B — two terminals (always run from `backend/`):**

```bash
cd backend
source venv/bin/activate

# Terminal 1 — main API
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — LLM service (report analysis)
python -m uvicorn LLM_Model.llm_service:app --host 127.0.0.1 --port 8001 --reload
```

API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

> **Important:** Run uvicorn from the `backend/` directory. Running from the repo root causes `Could not import module "main"` and reload loops over `venv/`.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_URI` | Yes | MongoDB connection string (include database name, e.g. `...mongodb.net/medai`) |
| `JWT_SECRET` | Yes | Secret for signing JWT tokens |
| `GROQ_API_KEY` | Yes | Groq API key for chat and report LLM |
| `PORT` | No | Main API port (default `8000`) |
| `LLM_SERVICE_URL` | No | LLM service URL (default `http://localhost:8001`) |
| `OPENAI_API_KEY` | No | Legacy; chat uses Groq |

See `backend/.env.example`.

## Frontend

Point the Vite app at this API (proxy is preconfigured to `http://127.0.0.1:8000` in `med-ai-v3/frontend-vite/vite.config.ts`).
