"""
ai_agents.py
------------
Multi-agent system powered by Cohere.

Agents:
    1. FeedbackAgent  — reads the CV + analysis, produces prioritized suggestions
    2. CriticAgent    — finds weaknesses the analysis missed (tone, impact, specificity)
    3. RewriterAgent  — rewrites the CV applying all feedback
    4. JobMatchAgent  — compares the CV against a job description and suggests tailoring

Each agent is a focused function with a clear prompt. This "separation of concerns"
is what makes the system an actual agent pipeline rather than one giant LLM call.
"""

import os
import cohere


# ---------- Cohere client (lazy, safe to import without a key) ----------
_client = None


def get_client():
    """Return a Cohere client, or None if no API key is configured."""
    global _client
    if _client is None:
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            return None
        _client = cohere.Client(api_key)
    return _client


def is_available() -> bool:
    """Check if Cohere is configured."""
    return get_client() is not None


NO_KEY_MSG = (
    "⚠️ Cohere API key required. Add `COHERE_API_KEY=...` to your `.env` file "
    "and restart the app. Get a free key at https://dashboard.cohere.com/api-keys"
)


# ================== Model config ==================
# Cohere's current command models. If one is deprecated, swap here.
CHAT_MODEL = "command-r-plus-08-2024"


def _chat(prompt: str, temperature: float = 0.3, max_tokens: int = 1500) -> str:
    """Thin wrapper around cohere.chat()."""
    client = get_client()
    if client is None:
        return NO_KEY_MSG
    try:
        response = client.chat(
            model=CHAT_MODEL,
            message=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.text.strip()
    except Exception as e:
        return f"⚠️ Cohere error: {e}"


# ================== Agent 1: Feedback ==================
def feedback_agent(
    cv_text: str,
    grammar_issues: list[dict],
    missing_sections: list[str],
    ats_issues: list[str],
) -> str:
    """
    Produce prioritized, actionable feedback on the CV.
    Combines all analysis signals into a clean set of recommendations.
    """
    if not is_available():
        return NO_KEY_MSG

    grammar_lines = "\n".join(f"- {g['message']}" for g in grammar_issues[:10]) or "(none)"
    missing = ", ".join(missing_sections) or "(none)"
    ats = "\n".join(f"- {i}" for i in ats_issues) or "(none)"

    prompt = f"""You are a senior career coach reviewing a CV.

Below is factual analysis of the CV. Write a short, prioritized set of
improvement suggestions. Be specific — no generic advice.

SPELLING/GRAMMAR ISSUES:
{grammar_lines}

MISSING SECTIONS:
{missing}

ATS (applicant tracking system) PROBLEMS:
{ats}

CV EXCERPT:
{cv_text[:2000]}

RULES:
- 5 to 7 bullet points max
- Each bullet: one specific, actionable change
- Order by impact (most important first)
- No intro line, no summary at the end
- Plain text only, do not use markdown headers
"""
    return _chat(prompt, temperature=0.3, max_tokens=700)


# ================== Agent 2: Critic ==================
def critic_agent(cv_text: str, job_description: str = "") -> str:
    """
    Independent critic that reviews the CV on dimensions the rule-based
    analyzer can't see: impact, specificity, tone, storytelling.
    """
    if not is_available():
        return NO_KEY_MSG

    jd_block = ""
    if job_description.strip():
        jd_block = f"""
The candidate is targeting this job — factor this in:
\"\"\"
{job_description[:1200]}
\"\"\"
"""

    prompt = f"""You are a hiring manager at a top company. Critique this CV harshly
but constructively. Focus on what a human recruiter would notice — not typos.

{ jd_block}
CV:
{cv_text[:3000]}

Return 4 to 5 bullets covering:
- Impact: are achievements quantified? (numbers, %, scale)
- Specificity: too vague or appropriately concrete?
- Tone: confident, humble, generic, buzzword-heavy?
- Story: does the CV tell a coherent career narrative?
- Fit: alignment with the target role (if provided)

Each bullet: label ("Impact:" etc.) + 1-2 sentences. No preamble.
"""
    return _chat(prompt, temperature=0.4, max_tokens=600)


# ================== Agent 3: Rewriter ==================
def rewriter_agent(
    cv_text: str,
    grammar_issues: list[dict],
    missing_sections: list[str],
    job_description: str = "",
) -> str:
    """
    Rewrite the CV applying every identified issue and, if provided,
    tailoring it toward a target job description.
    """
    if not is_available():
        return NO_KEY_MSG

    issues_summary = "\n".join(
        f"- {g['message']} → try: {', '.join(g['replacements']) or 'rewrite'}"
        for g in grammar_issues[:15]
    ) or "(none)"

    missing_summary = ", ".join(missing_sections) if missing_sections else "(none)"

    jd_block = ""
    if job_description.strip():
        jd_block = f"""
TARGET JOB DESCRIPTION (tailor the CV toward this):
\"\"\"
{job_description[:1500]}
\"\"\"
"""

    prompt = f"""You are an expert CV writer. Rewrite the CV below.

ISSUES TO FIX:
{issues_summary}

MISSING SECTIONS TO ADD (use [ADD YOUR ...] placeholders when info is unknown):
{missing_summary}

{jd_block}

STRICT RULES:
- Keep all factual information UNCHANGED (names, dates, companies, schools)
- Fix every grammar and spelling issue
- Rewrite bullets as achievement statements: action verb + scope + measurable result
- Add the missing sections with clearly-marked placeholders
- Keep formatting ATS-friendly: no tables, no columns, no graphics, no emojis
- Use standard headings: Summary, Experience, Education, Skills, Projects
- Output ONLY the rewritten CV. No commentary, no markdown code fences, no intro.

ORIGINAL CV:
{cv_text[:4500]}

REWRITTEN CV:
"""
    return _chat(prompt, temperature=0.4, max_tokens=2500)


# ================== Agent 4: Job Match Advisor ==================
def job_match_agent(
    cv_text: str,
    job_description: str,
    missing_keywords: list[str],
) -> str:
    """
    Given the CV, a job description, and the missing keywords,
    advise how to close the gap — what to add, rephrase, or emphasize.
    """
    if not is_available():
        return NO_KEY_MSG

    if not job_description.strip():
        return "Paste a job description above to get tailoring advice."

    missing_text = ", ".join(missing_keywords[:20]) or "(none)"

    prompt = f"""You are a career strategist helping a candidate tailor their CV
to a specific job.

JOB DESCRIPTION:
\"\"\"
{job_description[:1500]}
\"\"\"

KEYWORDS THE CV IS MISSING:
{missing_text}

CV:
{cv_text[:2500]}

Give 4-6 bullets advising how to close the gap. Cover:
- Which missing keywords to work into which sections (only if genuinely relevant —
  never advise lying or keyword-stuffing)
- What experience to rephrase or expand to match the role
- What to de-emphasize (irrelevant to this role)
- One honest gap: what the candidate may need to actually learn or build

Be direct. No preamble.
"""
    return _chat(prompt, temperature=0.4, max_tokens=700)