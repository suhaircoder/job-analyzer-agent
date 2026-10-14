"""
analyzers.py
------------
Core analysis logic for CVs:
- Grammar / spelling check (LanguageTool)
- Section detection (contact, summary, experience, ...)
- Scoring: overall score, ATS-friendly score, keyword match
- Keyword extraction from a job description

No API keys needed here except none. LanguageTool runs locally.
"""

import re
from typing import Iterable
import language_tool_python


# ---------- Singleton LanguageTool (loaded once, reused everywhere) ----------
_tool = None


def get_tool():
    """Lazy-load LanguageTool once."""
    global _tool
    if _tool is None:
        _tool = language_tool_python.LanguageTool("en-US")
    return _tool


# ---------- Ignore list ----------
IGNORE_WORDS = {
    # Tech / AI terms that trigger false positives
    "ai", "ml", "llm", "llms", "gpt", "nlp", "ocr", "api", "apis", "sdk",
    "pytorch", "tensorflow", "keras", "langchain", "openai", "cohere",
    "gradio", "streamlit", "huggingface", "github", "gitlab", "linkedin",
    "python", "javascript", "typescript", "java", "kotlin", "swift",
    "sql", "nosql", "mongodb", "postgres", "postgresql", "mysql", "redis",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "linux",
    "html", "css", "react", "vue", "angular", "nodejs", "npm", "yarn",
    "cv", "resume", "ats",
    # Common proper nouns
    "russia", "usa", "uk", "eu",
}


# ---------- Standard CV sections ----------
SECTION_KEYWORDS = {
    "contact":    ["email", "@", "phone", "mobile", "linkedin", "github"],
    "summary":    ["summary", "profile", "objective", "about me", "overview"],
    "experience": ["experience", "employment", "work history", "professional background"],
    "education":  ["education", "university", "college", "degree", "bachelor", "master", "phd"],
    "skills":     ["skills", "technologies", "tech stack", "tools", "expertise"],
    "projects":   ["project", "portfolio", "case study"],
    "languages":  ["language", "english", "spanish", "french", "german"],
}


# ================== Grammar ==================
def check_grammar(text: str, max_issues: int = 50) -> list[dict]:
    """
    Run LanguageTool on the text and return filtered issue dicts.

    Filters out:
    - known proper nouns / tech terms
    - vague 'spelling mistake' hits without suggested replacements
    - generic capitalization warnings without suggestions
    """
    if not text.strip():
        return []

    tool = get_tool()
    matches = tool.check(text)
    filtered = []

    for m in matches:
        flagged = text[m.offset:m.offset + m.error_length].lower().strip()

        if flagged in IGNORE_WORDS:
            continue
        if "spelling" in m.message.lower() and not m.replacements:
            continue
        if m.rule_id in ("UPPERCASE_SENTENCE_START", "MORFOLOGIK_RULE_EN_US") and not m.replacements:
            continue

        filtered.append({
            "message": m.message,
            "replacements": m.replacements[:3],
            "context": m.context,
            "word": flagged,
            "offset": m.offset,
        })

        if len(filtered) >= max_issues:
            break

    return filtered


# ================== Sections ==================
def detect_missing_sections(text: str) -> list[str]:
    """Return list of section names that don't appear in the CV."""
    text_lower = text.lower()
    missing = []
    for section, keywords in SECTION_KEYWORDS.items():
        if not any(kw in text_lower for kw in keywords):
            missing.append(section)
    return missing


# ================== ATS Score ==================
def ats_score(text: str) -> tuple[int, list[str]]:
    """
    Heuristic ATS (Applicant Tracking System) friendliness check.

    ATS parsers struggle with: tables, columns, images, graphics, unusual fonts.
    We can't check visuals, but we CAN check for common ATS-killers in text.

    Returns (score 0-100, list of issues).
    """
    issues = []
    score = 100

    # Too short
    words = len(text.split())
    if words < 150:
        issues.append("CV is very short — ATS may see it as incomplete")
        score -= 20
    elif words < 300:
        issues.append("CV is on the short side")
        score -= 8

    # Too long (huge red flag for ATS + recruiters)
    if words > 1200:
        issues.append("CV is long — consider trimming to 1–2 pages")
        score -= 10

    # Missing contact info
    if not re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text):
        issues.append("No email address detected")
        score -= 15

    if not re.search(r"(\+?\d[\d\s\-\(\)]{7,}\d)", text):
        issues.append("No phone number detected")
        score -= 10

    # Date patterns — ATS looks for them in experience
    date_patterns = [r"\b(19|20)\d{2}\b", r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b"]
    if not any(re.search(p, text, re.IGNORECASE) for p in date_patterns):
        issues.append("No dates found — experience timeline unclear")
        score -= 10

    # Bullet points — a strong signal of a well-formatted CV
    bullet_lines = sum(1 for line in text.splitlines() if line.strip().startswith(("•", "-", "*", "·")))
    if bullet_lines < 5:
        issues.append("Few or no bullet points — use bullets for achievements")
        score -= 10

    # Overuse of ALL CAPS in body (not headings)
    upper_lines = sum(1 for line in text.splitlines() if line.isupper() and len(line) > 40)
    if upper_lines > 0:
        issues.append("Long lines in ALL CAPS — hurts readability and ATS")
        score -= 5

    return max(0, min(100, score)), issues


# ================== Keyword Match vs Job Description ==================
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "can", "this",
    "that", "these", "those", "i", "you", "we", "they", "he", "she", "it",
    "our", "your", "their", "his", "her", "its", "if", "so", "then", "than",
    "not", "no", "yes", "any", "all", "each", "every", "some", "such",
    "about", "into", "over", "under", "up", "down", "out", "off",
    "we", "us", "our", "you", "your", "yours", "them", "their",
    "we're", "we'll", "you'll", "it's", "that's",
    "years", "year", "experience", "work", "working", "role", "job",
    "team", "company", "candidate", "position", "ability", "strong",
    "excellent", "good", "great", "looking", "seeking", "join", "plus",
}


def extract_keywords(job_description: str, top_n: int = 30) -> list[str]:
    """Extract key skill terms from a job description."""
    # lowercase, keep letters/digits/+/#/.- and spaces
    text = re.sub(r"[^\w\s\+\#\.\-]", " ", job_description.lower())
    words = [w.strip(".-") for w in text.split()]

    # filter
    words = [w for w in words if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]

    # also grab multi-word phrases? keep simple: just frequency of single words
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    # sort by frequency then alphabetical
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_n]]


def keyword_match(cv_text: str, job_description: str, top_n: int = 30) -> dict:
    """
    Compare CV text against a job description.

    Returns:
        {
          "score": int 0-100,
          "matched": [list of keywords found in CV],
          "missing": [list of keywords not in CV],
          "keywords": [all keywords extracted from JD],
        }
    """
    if not job_description.strip():
        return {"score": 0, "matched": [], "missing": [], "keywords": []}

    keywords = extract_keywords(job_description, top_n=top_n)
    cv_lower = cv_text.lower()

    matched = [kw for kw in keywords if kw in cv_lower]
    missing = [kw for kw in keywords if kw not in cv_lower]

    score = int(round(100 * len(matched) / max(1, len(keywords))))
    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "keywords": keywords,
    }


# ================== Overall Score ==================
def overall_score(
    grammar_issues: list[dict],
    missing_sections: list[str],
    ats: int,
    text: str,
) -> int:
    """
    Combine all signals into a single 0-100 score.

    Weights:
        40% ATS-friendliness
        25% section completeness
        20% grammar cleanliness
        15% length appropriateness
    """
    words = len(text.split())

    # --- ATS ---
    ats_component = ats * 0.40

    # --- Sections ---
    total_sections = len(SECTION_KEYWORDS)
    section_component = (1 - len(missing_sections) / total_sections) * 25

    # --- Grammar ---
    # Up to ~15 issues is a full penalty; more than that saturates
    grammar_penalty = min(len(grammar_issues) / 15, 1.0) * 20
    grammar_component = 20 - grammar_penalty

    # --- Length ---
    if 300 <= words <= 900:
        length_component = 15
    elif 200 <= words < 300 or 900 < words <= 1200:
        length_component = 10
    elif words < 200:
        length_component = 5
    else:
        length_component = 5

    total = ats_component + section_component + grammar_component + length_component
    return max(0, min(100, int(round(total))))


def grade_badge(score: int) -> str:
    """Human-readable grade label."""
    if score >= 85:
        return "🟢 Excellent"
    if score >= 70:
        return "🟡 Good"
    if score >= 50:
        return "🟠 Fair"
    return "🔴 Needs Work"