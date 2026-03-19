"""
Response parser for Med-AI LLM output.
Parses JSON safely, normalizes structure, and handles invalid responses.
"""

import json
import re
from typing import Any


# Expected top-level keys in the structured response
EXPECTED_KEYS = {
    "summary",
    "key_findings",
    "abnormal_values",
    "possible_conditions",
    "recommendations",
}


def _extract_json_from_text(raw: str) -> str | None:
    """
    Extract JSON object from raw text (handles markdown code blocks, trailing text).
    Returns the JSON string or None if not found.
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Remove markdown code block wrappers if present
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_block:
        text = code_block.group(1).strip()

    # Find first { and last } to extract JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None


def _normalize_abnormal_value(obj: Any) -> dict | None:
    """Ensure abnormal_values entry has correct structure."""
    if not isinstance(obj, dict):
        return None
    test_name = obj.get("test_name", obj.get("testName", ""))
    observed_value = obj.get("observed_value", obj.get("observedValue", ""))
    normal_range = obj.get("normal_range", obj.get("normalRange", ""))
    status = (obj.get("status") or "normal").lower()
    if status not in ("high", "low", "normal"):
        status = "normal"
    return {
        "test_name": str(test_name) if test_name else "",
        "observed_value": str(observed_value) if observed_value else "",
        "normal_range": str(normal_range) if normal_range else "",
        "status": status,
    }


def _normalize_response(data: dict) -> dict:
    """Normalize parsed JSON to expected schema with correct types."""
    result: dict[str, Any] = {
        "summary": "",
        "key_findings": [],
        "abnormal_values": [],
        "possible_conditions": [],
        "recommendations": [],
    }

    # Summary - string
    summary = data.get("summary", data.get("Summary", ""))
    result["summary"] = str(summary).strip() if summary else ""

    # key_findings - list of strings
    kf = data.get("key_findings", data.get("keyFindings", data.get("Key Findings", [])))
    if isinstance(kf, list):
        result["key_findings"] = [str(x).strip() for x in kf if x]
    elif isinstance(kf, str) and kf.strip():
        result["key_findings"] = [kf.strip()]

    # abnormal_values - list of objects
    av = data.get("abnormal_values", data.get("abnormalValues", data.get("Abnormal Values", [])))
    if isinstance(av, list):
        for item in av:
            norm = _normalize_abnormal_value(item)
            if norm:
                result["abnormal_values"].append(norm)

    # possible_conditions - list of strings
    pc = data.get("possible_conditions", data.get("possibleConditions", data.get("Possible Conditions", [])))
    if isinstance(pc, list):
        result["possible_conditions"] = [str(x).strip() for x in pc if x]
    elif isinstance(pc, str) and pc.strip():
        result["possible_conditions"] = [pc.strip()]

    # recommendations - list of strings
    rec = data.get("recommendations", data.get("Recommendations", []))
    if isinstance(rec, list):
        result["recommendations"] = [str(x).strip() for x in rec if x]
    elif isinstance(rec, str) and rec.strip():
        result["recommendations"] = [rec.strip()]

    return result


def parse_llm_response(raw_content: str) -> dict | None:
    """
    Parse LLM response into a clean Python dict matching the expected schema.

    - Handles JSON wrapped in markdown code blocks
    - Normalizes field names (snake_case, camelCase)
    - Ensures correct types (lists, strings, abnormal_value objects)
    - Returns None if parsing fails

    Args:
        raw_content: Raw string from LLM (e.g. choices[0].message.content)

    Returns:
        Normalized dict or None if invalid
    """
    json_str = _extract_json_from_text(raw_content)
    if not json_str:
        return None

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    return _normalize_response(data)


def get_retry_prompt() -> str:
    """
    Returns a stricter instruction to append when retrying after parse failure.
    Caller should send this as a follow-up or replace the original instruction.
    """
    return "\n\nIMPORTANT: Your previous response was not valid JSON. Respond again with ONLY a valid JSON object, no other text. Ensure all strings are properly escaped and the structure matches the schema exactly."
