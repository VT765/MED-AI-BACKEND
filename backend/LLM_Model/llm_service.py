import json
import os
import sys
from pathlib import Path

import requests
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

# Add backend to path for utils imports (prompt_builder, response_parser)
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from utils.prompt_builder import build_prompt
from utils.response_parser import get_retry_prompt, parse_llm_response

# Load environment variables from backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Med-AI LLM Service")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_PORT = 8001

# Low temperature for consistent, deterministic JSON output
TEMPERATURE = 0.3


class ReportRequest(BaseModel):
    text: str
    patient_context: str = ""


@app.get("/")
def health():
    return {"status": "LLM Service running with Groq on port 8001"}


def _call_groq(prompt: str) -> dict:
    """Call Groq API with the given prompt. Returns raw API response dict or error dict."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        # llama-3.1-8b-instant was decommissioned on Groq; use an available model.
        "model": "openai/gpt-oss-120b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "max_tokens": 2000,
        "reasoning_effort": "low",
    }
    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        data = response.json()
        # gpt-oss sometimes wraps its output as a bogus tool call → `tool_use_failed`.
        # The real content sits in `failed_generation`; recover it so parsing can proceed.
        err = data.get("error", {}) if isinstance(data, dict) else {}
        if err.get("code") == "tool_use_failed" and err.get("failed_generation"):
            salvaged = _salvage_failed_generation(err["failed_generation"])
            if salvaged:
                return {"content": salvaged}
        if "choices" not in data or not data["choices"]:
            return {"error": "Groq API returned unexpected response", "details": data}
        content = data["choices"][0].get("message", {}).get("content", "")
        return {"content": content}
    except Exception as e:
        return {"error": "LLM request failed", "details": str(e)}


def _salvage_failed_generation(failed_generation) -> str:
    """Recover assistant text from a Groq `failed_generation` payload (phantom tool call)."""
    if not isinstance(failed_generation, str):
        return ""
    try:
        obj = json.loads(failed_generation)
    except json.JSONDecodeError:
        return failed_generation.strip()
    if isinstance(obj, dict):
        args = obj.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = None
        if isinstance(args, dict) and args.get("content"):
            return str(args["content"]).strip()
        if obj.get("content"):
            return str(obj["content"]).strip()
    return ""


def query_groq(ocr_text: str, patient_context: str = "") -> dict:
    """
    Build structured prompt, call LLM, parse JSON response.
    Retries once with stricter instruction if parsing fails.
    Returns either parsed structured analysis or error dict.
    """
    prompt = build_prompt(ocr_text, patient_context)
    result = _call_groq(prompt)

    if "error" in result:
        return result

    content = result.get("content", "")
    parsed = parse_llm_response(content)

    if parsed is not None:
        return {"analysis": parsed}

    # Retry once with stricter instruction
    retry_prompt = prompt + get_retry_prompt()
    retry_result = _call_groq(retry_prompt)
    if "error" in retry_result:
        return retry_result

    retry_content = retry_result.get("content", "")
    retry_parsed = parse_llm_response(retry_content)

    if retry_parsed is not None:
        return {"analysis": retry_parsed}

    # Fallback: return raw content with parse error flag
    return {
        "error": "Could not parse LLM response as valid JSON",
        "raw_content": content[:500] if content else "",
    }


@app.post("/analyze")
def analyze(req: ReportRequest):
    """Analyze medical report text. Returns structured JSON or error."""
    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY not configured"}
    return query_groq(req.text, req.patient_context)


if __name__ == "__main__":
    uvicorn.run(
        "llm_service:app",
        host="127.0.0.1",
        port=LLM_PORT,
        reload=True,
    )