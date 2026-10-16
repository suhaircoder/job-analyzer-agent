"""
cv_tailor.py
------------
Orchestrator that generates a tailored CV for a specific job.

Pipeline:
    profile + jd
        ↓
    matcher      (which experiences/skills to highlight)
        ↓
    writer       (rewrite bullets and summary, prioritize by relevance)
        ↓
    assembled    (final tailored CV text)
        ↓
    validated    (quality_gate)
        ↓
    retry if fail (up to max_attempts)

The orchestrator runs these as a sequence, passing data between them.
"""

import json
import re

from src.ai_agents import _chat, is_available, NO_KEY_MSG


# ================== Step 1: Match ==================
MATCH_PROMPT = """You are a career strategist. Decide which of the candidate's experiences, projects, and skills are MOST relevant for this job.

JOB REQUIREMENTS:
{jd_json}

CANDIDATE PROFILE:
{profile_json}

Return ONLY valid JSON with this schema:

{{
  "top_experiences": [0, 2, 1],       // indices of experience entries, most relevant first
  "top_projects": [0],                // indices of project entries
  "top_skills": ["Python", "PyTorch"],
  "keywords_to_inject": ["LLM", "model deployment"],
  "match_score": 78,                  // 0-100, how well the candidate fits this role
  "reasoning": "brief explanation, 2 sentences max"
}}

RULES:
- Sort by relevance DESCENDING.
- Include only experiences that meaningfully relate to the JD. If fewer than 3 match, include only what fits.
- "keywords_to_inject" = JD keywords the candidate genuinely HAS (evidenced in the profile)
  but hasn't explicitly worded that way. If the candidate does NOT have the skill, do not include it.
- NEVER include skills, tools, or experiences the candidate doesn't actually have.
- match_score reflects honest overlap, not optimism.

JSON:"""


def match_agent(profile: dict, jd: dict) -> tuple[dict, str | None]:
    """Decide what to emphasize from the profile for this JD."""
    if not is_available():
        return {}, NO_KEY_MSG

    prompt = MATCH_PROMPT.format(
        jd_json=json.dumps(jd, ensure_ascii=False, indent=2)[:2500],
        profile_json=json.dumps(profile, ensure_ascii=False, indent=2)[:4000],
    )

    raw = _chat(prompt, temperature=0.2, max_tokens=1200)
    if raw.startswith("⚠️"):
        return {}, raw

    json_str = _extract_json(raw)
    try:
        match = json.loads(json_str)
    except json.JSONDecodeError as e:
        return {}, f"Could not parse matcher output: {e}"

    match.setdefault("top_experiences", [])
    match.setdefault("top_projects", [])
    match.setdefault("top_skills", [])
    match.setdefault("keywords_to_inject", [])
    match.setdefault("match_score", 0)
    match.setdefault("reasoning", "")

    return match, None


# ================== Step 2: Write ==================
WRITE_PROMPT = """You are an expert CV writer. Write a TAILORED CV for the job below.

TARGET JOB:
{jd_json}

CANDIDATE PROFILE:
{profile_json}

MATCH STRATEGY (from previous analysis):
{match_json}

Write the tailored CV in clean, ATS-friendly MARKDOWN with these sections:

# {{Full Name}}
Contact line: email · phone · location · linkedin · github

## Professional Summary
2-3 sentences that position the candidate for THIS specific role.

## Experience
List only the experiences flagged as top_experiences, in the given order.
For each: **Role** at **Company** — Start to End
Then 3-5 bullet points. REWRITE existing bullets to emphasize the JD's language.
Add measurable outcomes where the original CV supports it.

## Skills
Grouped by category (Languages, Frameworks, Tools, etc.).
Highlight must-have skills from the JD.

## Projects
Only the projects flagged as top_projects.

## Education
Standard format.

STRICT RULES:
- NEVER invent companies, dates, degrees, or skills not in the profile.
- NEVER add technologies (tools, frameworks, programming languages, methods) to a bullet
  unless they were explicitly mentioned in the ORIGINAL bullet OR in the project's
  description in the profile. Rephrasing for emphasis is OK; adding new tech is NOT.
- Example of WRONG: original says "built a lip reading system using deep learning" →
  do NOT change to "built a lip reading system leveraging LLMs".
  (That adds "LLMs" which wasn't in the original — a hallucination.)
- Example of RIGHT: original says "built a lip reading system using deep learning" →
  "built a lip reading system using deep learning that achieved 92% accuracy" (still deep learning).
- Do NOT copy-paste the JD back.
- Use the JD's vocabulary ONLY when it accurately describes what the candidate already did.
- Do NOT include sections that would be empty.
- Output ONLY the CV in markdown. No intro, no commentary, no code fences.

TAILORED CV:"""


def writer_agent(profile: dict, jd: dict, match: dict, critique: str = None) -> tuple[str, str | None]:
    """Write the tailored CV markdown. Optionally incorporates prior critique."""
    if not is_available():
        return "", NO_KEY_MSG

    base_prompt = WRITE_PROMPT.format(
        jd_json=json.dumps(jd, ensure_ascii=False, indent=2)[:2500],
        profile_json=json.dumps(profile, ensure_ascii=False, indent=2)[:4000],
        match_json=json.dumps(match, ensure_ascii=False, indent=2)[:1500],
    )

    if critique:
        prompt = base_prompt + f"""

FEEDBACK FROM PREVIOUS ATTEMPT (fix all of these):
{critique}

REWRITTEN CV:"""
    else:
        prompt = base_prompt

    raw = _chat(prompt, temperature=0.3, max_tokens=2500)
    if raw.startswith("⚠️"):
        return "", raw

    # Strip stray code fences
    raw = re.sub(r"^```(?:markdown|md)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    if len(raw) < 200:
        return raw, "Warning: generated CV is suspiciously short."

    return raw, None


# ================== Helpers ==================
def _extract_json(text: str) -> str:
    """Pull the first JSON object out of an LLM reply."""
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


# ================== The Orchestrator ==================
def tailor_cv(profile: dict, jd: dict, progress_cb=None, max_attempts: int = 3) -> dict:
    """
    Full agentic pipeline: profile + jd → tailored CV (validated).

    Pipeline:
        1. Match    — decide what to emphasize
        2. Write    — produce the tailored CV
        3. Validate — quality gate
        4. If fail → retry with feedback (up to max_attempts)
        5. Return the best result

    Returns:
        {
            "ok": bool,
            "cv_markdown": str,
            "match": dict,
            "quality": dict,
            "attempts": int,
            "errors": [str],
        }
    """
    from src.quality_gate import evaluate_cv

    errors = []

    # ---- Step 1: Match (once) ----
    if progress_cb:
        progress_cb("Matching profile to job...")
    match, err = match_agent(profile, jd)
    if err:
        errors.append(f"match: {err}")

    # ---- Loop: Write → Validate → Retry ----
    best_cv = ""
    best_quality = {"pass": False, "score": 0, "issues": ["No attempt yet"]}
    attempt = 0

    critique = None  # feedback for the next attempt

    for attempt in range(1, max_attempts + 1):
        if progress_cb:
            progress_cb(f"Writing tailored CV (attempt {attempt}/{max_attempts})...")

        cv_markdown, err = writer_agent(profile, jd, match, critique=critique)
        if err:
            errors.append(f"write (attempt {attempt}): {err}")

        if not cv_markdown or cv_markdown.startswith("⚠️"):
            best_cv = cv_markdown or best_cv
            continue

        if progress_cb:
            progress_cb(f"Validating output (attempt {attempt})...")
        quality = evaluate_cv(cv_markdown, profile)

        # Track the best so far (highest score)
        if quality["score"] > best_quality.get("score", 0):
            best_cv = cv_markdown
            best_quality = quality

        if quality["pass"]:
            return {
                "ok": True,
                "cv_markdown": cv_markdown,
                "match": match,
                "quality": quality,
                "attempts": attempt,
                "errors": errors,
            }

        # Prepare feedback for the next attempt
        critique = (
            "The previous version FAILED the quality gate. You MUST fix these issues:\n"
            + "\n".join(f"- {i}" for i in quality["issues"])
            + """

CRITICAL RULES to pass the gate:
1. Do NOT mention any technology, tool, or framework that is not in the ORIGINAL
   profile or project descriptions. If unsure, leave it out.
2. Reword the summary in the JD's language ONLY using words the candidate already has
   evidence for.
3. Each experience bullet must be 15-25 words and contain a measurable outcome.
4. Include ALL of: Summary, Experience, Skills, Education sections.
5. Aim for 350-600 words total.

DO NOT add technologies that aren't in the profile. This is the #1 reason for failures."""
        )

    # All attempts failed — return the best we got, flagged as not-ok
    return {
        "ok": False,
        "cv_markdown": best_cv,
        "match": match,
        "quality": best_quality,
        "attempts": attempt,
        "errors": errors + [f"Quality gate did not pass after {max_attempts} attempts."],
    }