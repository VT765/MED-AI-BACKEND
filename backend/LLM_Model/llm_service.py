import os
import sys
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import requests
from dotenv import load_dotenv

# Load environment variables from backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Med-AI LLM Service")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_PORT = 8001


class ReportRequest(BaseModel):
    text: str


@app.get("/")
def health():
    return {"status": "LLM Service running with Groq on port 8001"}


def query_groq(report_text: str):

    prompt = f"""
You are a medical AI assistant.

Analyze the following medical report and provide:

1. Patient summary
2. Diagnosis
3. Abnormal findings
4. Health risk level
5. Recommended medical action

Medical Report:
{report_text}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    try:
        response = requests.post(
            GROQ_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        data = response.json()
        print("Groq response:", data)

        if "choices" not in data:
            return {
                "error": "Groq API returned unexpected response",
                "details": data
            }

        return {
            "analysis": data["choices"][0]["message"]["content"]
        }

    except Exception as e:
        return {
            "error": "LLM request failed",
            "details": str(e)
        }


@app.post("/analyze")
def analyze(req: ReportRequest):

    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY not configured"}

    result = query_groq(req.text)
    return result


if __name__ == "__main__":
    uvicorn.run(
        "llm_service:app",
        host="127.0.0.1",
        port=LLM_PORT,
        reload=True,
    )