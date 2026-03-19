"""
Prompt builder for Med-AI report analysis.
Loads script.md, injects OCR text, and appends strict JSON schema.
"""

from pathlib import Path

# Resolve prompts path relative to this module (backend/utils -> backend/prompts)
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "script.md"

# Strict JSON schema for LLM response - order matches script.md
JSON_SCHEMA = """
You MUST return output ONLY in this JSON format:

{
  "summary": "...",
  "key_findings": ["...", "..."],
  "abnormal_values": [
    {
      "test_name": "...",
      "observed_value": "...",
      "normal_range": "...",
      "status": "high | low | normal"
    }
  ],
  "possible_conditions": ["...", "..."],
  "recommendations": ["...", "..."]
}

Rules:
- No extra text before or after JSON
- Do not change keys
- If data unavailable → use empty arrays or "Not available"
"""

STRICT_RULES = """
CRITICAL RULES:
- Output ONLY valid JSON. No markdown, no code blocks, no extra text before or after.
- Do NOT hallucinate. Include only information clearly present in the OCR text.
- Use empty arrays [] for sections with no relevant data (e.g., no abnormal values → "abnormal_values": []).
- For status in abnormal_values, use exactly: "high", "low", or "normal".
"""


def _load_script() -> str:
    """Load script.md content. Returns empty string if file not found."""
    try:
        return _SCRIPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _clean_ocr_text(text: str) -> str:
    """Basic OCR text cleaning - collapse excessive whitespace, trim."""
    if not text or not text.strip():
        return ""
    lines = (line.strip() for line in text.splitlines() if line.strip())
    return "\n".join(lines)


def build_prompt(ocr_text: str) -> str:
    """
    Build the full analysis prompt for the LLM.
    - Loads script.md for response order and guidelines
    - Injects cleaned OCR text
    - Appends strict JSON schema and rules

    Args:
        ocr_text: Raw text extracted from medical report (OCR or PDF)

    Returns:
        Complete prompt string for the LLM
    """
    script = _load_script()
    cleaned = _clean_ocr_text(ocr_text)

    if not cleaned:
        cleaned = "(No readable text was extracted from the report. Please indicate this in your response.)"

    prompt = f"""You are a Med-AI assistant. Analyze the following medical report and respond with structured, patient-friendly insights.

{script}

---

## OCR / Report Text (may contain noise or formatting artifacts)

Clean and interpret the text below. Ignore obvious OCR errors; focus on values, units, and medical terms.

```
{cleaned}
```

---

## Required Output Format

Respond with ONLY a valid JSON object matching this schema. No other text.

{JSON_SCHEMA}

{STRICT_RULES}
"""
    return prompt.strip()
