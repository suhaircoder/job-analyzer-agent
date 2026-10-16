"""
profile_parser.py
-----------------
Turn raw CV text into a structured profile (dict matching the schema).

The LLM does the heavy lifting of extracting structured fields from
unstructured text. Then we validate and normalize the output before
returning it, so downstream code can rely on the shape.
"""

import json
import re

from src.ai_agents import _chat, is_available, NO_KEY_MSG
from src.storage import EMPTY_PROFILE


# ---------- The extraction prompt ----------
EXTRACTION_PROMPT = """You are a CV parsing engine. Extract structured data from the CV below.

Return ONLY valid JSON matching this exact schema. No commentary, no markdown fences.

{{
  "name": "",
  "email": "",
  "phone": "",
  "location": "",
  "linkedin": "",
  "github": "",
  "summary": "",
  "experience": [
    {{
      "company": "",
      "role": "",
      "start": "",
      "end": "",
      "bullets": [""],
      "skills_used": [""]
    }}
  ],
  "education": [
    {{
      "institution": "",
      "degree": "",
      "year": ""
    }}
  ],
  "skills": [""],
  "projects": [
    {{
      "name": "",
      "description": ""
    }}
  ]
}}

RULES:
- Leave fields as "" or [] if the information isn't in the CV.
- NEVER invent information. If a field isn't present, leave it empty.
- Keep bullets close to the original wording.
- Dates: use "YYYY-MM" if available, otherwise "YYYY", otherwise "".
- "end" should be "present" if the role is current.
- IMPORTANT: For "skills", scan the ENTIRE CV — bullets, projects, summary, and
  any explicit skills section. Include every technology mentioned anywhere.
  Examples to look for: Python, PyTorch, TensorFlow, Git, Docker, Linux, SQL,
  LLMs, NLP, Computer Vision, Machine Learning, Deep Learning, Data Analysis.
  Do NOT require a labeled "Skills" section for a skill to count.
- For "experience[].skills_used", list every technology mentioned in that
  role's bullets.
CV TEXT:
{cv_text}

JSON:"""


# ---------- Parsing ----------
def _extract_json_block(text: str) -> str:
    """
    LLMs sometimes wrap JSON in ```json ... ``` fences or add prose.
    This pulls out the first {...} block.
    """
    text = text.strip()

    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    # Otherwise, find the first balanced { ... } block
    start = text.find("{")
    if start == -1:
        return text

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return text[start:]  # unbalanced; return what we have


def _merge_with_schema(data: dict) -> dict:
    """
    Ensure the returned dict has every key from EMPTY_PROFILE.
    Missing keys get the default value.
    """
    result = json.loads(json.dumps(EMPTY_PROFILE))  # deep copy

    for key, default in EMPTY_PROFILE.items():
        if key in data and data[key] not in (None, ""):
            result[key] = data[key]

    return result


def _normalize(profile: dict) -> dict:
    """Clean up obvious issues in the parsed profile."""
    # Ensure all list fields are actually lists
    for field in ("experience", "education", "skills", "projects"):
        if not isinstance(profile.get(field), list):
            profile[field] = []

    # Ensure each experience entry has the expected keys
    for exp in profile["experience"]:
        if not isinstance(exp, dict):
            continue
        exp.setdefault("company", "")
        exp.setdefault("role", "")
        exp.setdefault("start", "")
        exp.setdefault("end", "")
        exp.setdefault("bullets", [])
        exp.setdefault("skills_used", [])
        if not isinstance(exp["bullets"], list):
            exp["bullets"] = [str(exp["bullets"])]
        if not isinstance(exp["skills_used"], list):
            exp["skills_used"] = []

    # Trim whitespace from all top-level string fields
    for key, value in profile.items():
        if isinstance(value, str):
            profile[key] = value.strip()

    return profile


# ---------- Public API ----------
def parse_profile(cv_text: str) -> tuple[dict, str | None]:
    """
    Parse raw CV text into a structured profile.

    Returns:
        (profile_dict, error_message_or_None)

    On success:
        profile_dict = structured profile
        error = None

    On failure:
        profile_dict = empty profile
        error = human-readable error string
    """
    if not is_available():
        return dict(EMPTY_PROFILE), NO_KEY_MSG

    if not cv_text or not cv_text.strip():
        return dict(EMPTY_PROFILE), "No CV text provided."

    prompt = EXTRACTION_PROMPT.format(cv_text=cv_text[:6000])

    try:
        raw = _chat(prompt, temperature=0.1, max_tokens=2500)
    except Exception as e:
        return dict(EMPTY_PROFILE), f"LLM call failed: {e}"

    if raw.startswith("⚠️"):
        return dict(EMPTY_PROFILE), raw

    # Pull out the JSON block
    json_str = _extract_json_block(raw)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return dict(EMPTY_PROFILE), f"Could not parse LLM output as JSON: {e}"

    # Ensure correct shape
    profile = _merge_with_schema(data)
    profile = _normalize(profile)

    if not profile.get("name"):
        return profile, "Warning: couldn't detect a name in the CV."

    return profile, None