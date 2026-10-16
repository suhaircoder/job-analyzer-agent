"""
jd_analyzer.py
--------------
Turn a raw job description into structured requirements.

Output schema:
    {
        "title": "",
        "company": "",
        "location": "",
        "seniority": "",            # e.g. "mid", "senior", "lead"
        "must_have_skills": [""],   # technologies/methods explicitly required
        "nice_to_have_skills": [""],
        "responsibilities": [""],
        "keywords": [""],           # important terms for ATS matching
        "summary": ""               # 1-2 sentence gist
    }
"""

import json
import re

from src.ai_agents import _chat, is_available, NO_KEY_MSG


EMPTY_JD = {
    "title": "",
    "company": "",
    "location": "",
    "seniority": "",
    "must_have_skills": [],
    "nice_to_have_skills": [],
    "responsibilities": [],
    "keywords": [],
    "summary": "",
}


EXTRACTION_PROMPT = """You are a job description parser. Extract structured data from the job posting below.

Return ONLY valid JSON matching this exact schema. No commentary, no markdown fences.

{{
  "title": "",
  "company": "",
  "location": "",
  "seniority": "",
  "must_have_skills": [""],
  "nice_to_have_skills": [""],
  "responsibilities": [""],
  "keywords": [""],
  "summary": ""
}}

RULES:
- "seniority" should be one of: "intern", "junior", "mid", "senior", "lead", "principal", or "".
- "must_have_skills" = technologies or abilities the posting marks as REQUIRED.
- "nice_to_have_skills" = nice-to-have, bonus, or "a plus" items.
- "responsibilities" = short bullet phrases describing what the role does.
- "keywords" = 15-25 important terms for ATS matching. Include tools, methods, domains.
- "summary" = 1-2 sentences summarizing the role.
- Leave fields empty ("", []) if not present.
- Do NOT invent skills that aren't in the posting.

JOB DESCRIPTION:
{jd_text}

JSON:"""


def _extract_json_block(text: str) -> str:
    """Pull the first JSON object out of the LLM's reply."""
    text = text.strip()

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)

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

    return text[start:]


def _merge_with_schema(data: dict) -> dict:
    """Ensure every expected key exists."""
    result = json.loads(json.dumps(EMPTY_JD))
    for key, default in EMPTY_JD.items():
        if key in data and data[key] not in (None, ""):
            result[key] = data[key]
    return result


def _normalize(jd: dict) -> dict:
    """Fix minor issues in the parsed JD."""
    list_fields = ("must_have_skills", "nice_to_have_skills",
                   "responsibilities", "keywords")
    for field in list_fields:
        value = jd.get(field, [])
        if isinstance(value, str):
            # Sometimes the LLM returns a comma-separated string
            jd[field] = [v.strip() for v in value.split(",") if v.strip()]
        elif not isinstance(value, list):
            jd[field] = []
        else:
            jd[field] = [str(v).strip() for v in value if str(v).strip()]

    for key, value in jd.items():
        if isinstance(value, str):
            jd[key] = value.strip()

    return jd


def analyze_jd(jd_text: str) -> tuple[dict, str | None]:
    """
    Parse raw job description text into structured requirements.

    Returns (jd_dict, error_or_None).
    """
    if not is_available():
        return dict(EMPTY_JD), NO_KEY_MSG

    if not jd_text or not jd_text.strip():
        return dict(EMPTY_JD), "No job description provided."

    prompt = EXTRACTION_PROMPT.format(jd_text=jd_text[:6000])

    try:
        raw = _chat(prompt, temperature=0.1, max_tokens=2000)
    except Exception as e:
        return dict(EMPTY_JD), f"LLM call failed: {e}"

    if raw.startswith("⚠️"):
        return dict(EMPTY_JD), raw

    json_str = _extract_json_block(raw)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return dict(EMPTY_JD), f"Could not parse LLM output as JSON: {e}"

    jd = _normalize(_merge_with_schema(data))

    if not jd.get("title") and not jd.get("must_have_skills"):
        return jd, "Warning: couldn't detect a clear title or required skills."

    return jd, None


def make_slug(jd: dict) -> str:
    """
    Create a short slug from the JD for saving versions.
    Format: "{company}-{title}" or fallback to first keywords.
    """
    company = (jd.get("company") or "").strip()
    title = (jd.get("title") or "").strip()

    if company and title:
        raw = f"{company}-{title}"
    elif title:
        raw = title
    elif company:
        raw = company
    else:
        keywords = jd.get("keywords", [])[:3]
        raw = "-".join(keywords) if keywords else "untitled"

    return raw