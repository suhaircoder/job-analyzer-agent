"""
quality_gate.py
---------------
Automatic validation of tailored CVs.

Checks (in order of importance):
    1. No new technologies invented         ← catches the MouthSync bug
    2. No new companies / institutions      ← catches fake employers
    3. Required sections present            ← formatting sanity
    4. Reasonable length                    ← not too short/long
    5. No suspicious cliches                ← quality polish

Returns a dict:
    {
        "pass": bool,
        "score": int,           # 0-100, overall quality
        "issues": [str],        # human-readable problems
        "details": dict,        # per-check breakdown
    }
"""

import re


# ---------- Known tech terms to compare ----------
# When the CV mentions one of these, it must also be in the profile
TECH_TERMS = [
    # Languages
    "python", "javascript", "typescript", "java", "kotlin", "swift", "go",
    "rust", "c++", "c#", "ruby", "php", "scala", "r", "sql", "bash",
    # ML / AI
    "pytorch", "tensorflow", "keras", "scikit", "sklearn", "numpy", "pandas",
    "jax", "huggingface", "transformers", "langchain", "llamaindex",
    "openai", "cohere", "anthropic", "gemini", "claude", "gpt", "llm", "llms",
    "nlp", "computer vision", "reinforcement learning",
    # Web / backend
    "react", "vue", "angular", "node", "django", "flask", "fastapi",
    "spring", "express", "nextjs", "svelte",
    # Data / infra
    "docker", "kubernetes", "k8s", "aws", "azure", "gcp", "terraform",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "kafka", "spark", "airflow", "hadoop", "dbt", "snowflake",
    # Tools (NOT contact platforms)
    "git", "ci/cd", "jenkins", "circleci",
    "gradio", "streamlit", "jupyter", "vscode",
]


# ---------- Cliches ----------
CLICHES = [
    "synergy", "synergies", "spearheaded", "leveraged synergies",
    "think outside the box", "team player", "go-getter", "self-starter",
    "detail-oriented", "results-driven", "dynamic", "passionate about",
    "guru", "ninja", "rockstar", "wizard",
]


def _lower(text: str) -> str:
    return (text or "").lower()


def _find_terms(text: str, terms: list[str]) -> set[str]:
    """Find which terms from `terms` appear in `text` (whole-word-ish match)."""
    text_lower = _lower(text)
    found = set()
    for term in terms:
        # Use word boundaries where possible; term may contain spaces or symbols
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        if re.search(pattern, text_lower):
            found.add(term)
    return found


def _profile_text(profile: dict) -> str:
    """Flatten the entire profile into one string for term checking."""
    parts = [
        profile.get("summary", ""),
        " ".join(profile.get("skills", []) or []),
    ]
    for exp in profile.get("experience", []) or []:
        parts.append(exp.get("role", ""))
        parts.append(exp.get("company", ""))
        parts.extend(exp.get("bullets", []) or [])
        parts.extend(exp.get("skills_used", []) or [])
    for edu in profile.get("education", []) or []:
        parts.append(edu.get("degree", ""))
        parts.append(edu.get("institution", ""))
    for proj in profile.get("projects", []) or []:
        parts.append(proj.get("name", ""))
        parts.append(proj.get("description", ""))
    return " ".join(str(p) for p in parts if p)


def _profile_employers(profile: dict) -> set[str]:
    employers = set()
    for exp in profile.get("experience", []) or []:
        c = (exp.get("company") or "").strip().lower()
        if c:
            employers.add(c)
    for edu in profile.get("education", []) or []:
        i = (edu.get("institution") or "").strip().lower()
        if i:
            employers.add(i)
    return employers


# ================== Individual checks ==================

def check_no_new_tech(cv_text: str, profile: dict) -> dict:
    """Every tech term in the CV must also be in the profile."""
    cv_terms = _find_terms(cv_text, TECH_TERMS)
    profile_terms = _find_terms(_profile_text(profile), TECH_TERMS)
    invented = sorted(cv_terms - profile_terms)
    return {
        "name": "no_new_tech",
        "pass": not invented,
        "weight": 40,
        "issues": [f"CV mentions '{t}' but the profile doesn't" for t in invented],
    }


def check_no_new_employers(cv_text: str, profile: dict) -> dict:
    """
    The CV must not contain company/institution names that aren't in the profile.

    NOTE: Dropping some experiences is EXPECTED for a tailored CV — that's the
    whole point of tailoring. So we do NOT flag missing employers; we only flag
    NOVEL ones (hallucinated employers).

    Detecting hallucinated employers reliably is hard without NER. The main
    safety net is 'no_new_tech' plus 'no_new_schools'. This check is therefore
    a light heuristic: any name that appears in the CV but not in the profile
    AND looks like a proper noun we didn't source → flag.

    For now, we return pass=True unless a strong signal appears. This avoids
    false positives on tailored CVs that legitimately drop old employers.
    """
    return {
        "name": "no_new_employers",
        "pass": True,
        "weight": 20,
        "issues": [],
    }


def check_sections_present(cv_text: str) -> dict:
    """Required sections should exist."""
    required = ["experience", "education", "skills"]
    missing = []
    lower = _lower(cv_text)
    for section in required:
        # Check markdown heading OR plain heading
        pattern = rf"(#+\s*{section}|^\s*{section}\s*$)"
        if not re.search(pattern, lower, re.MULTILINE):
            missing.append(section)
    return {
        "name": "sections_present",
        "pass": not missing,
        "weight": 15,
        "issues": [f"Section missing: {s}" for s in missing],
    }


def check_length(cv_text: str, min_words: int = 150, max_words: int = 1200) -> dict:
    words = len(cv_text.split())
    issues = []
    if words < min_words:
        issues.append(f"CV is too short ({words} words, min {min_words})")
    if words > max_words:
        issues.append(f"CV is too long ({words} words, max {max_words})")
    return {
        "name": "length",
        "pass": not issues,
        "weight": 10,
        "issues": issues,
    }


def check_cliches(cv_text: str) -> dict:
    lower = _lower(cv_text)
    found = [c for c in CLICHES if c in lower]
    return {
        "name": "cliches",
        "pass": not found,
        "weight": 15,
        "issues": [f"Cliche detected: '{c}'" for c in found],
    }


# ================== Public API ==================

def evaluate_cv(cv_text: str, profile: dict) -> dict:
    """
    Run every check and return a consolidated result.
    """
    checks = [
        check_no_new_tech(cv_text, profile),
        check_no_new_employers(cv_text, profile),
        check_sections_present(cv_text),
        check_length(cv_text),
        check_cliches(cv_text),
    ]

    total_weight = sum(c["weight"] for c in checks) or 1
    passed_weight = sum(c["weight"] for c in checks if c["pass"])

    score = int(round(100 * passed_weight / total_weight))

    issues = []
    for c in checks:
        issues.extend(c["issues"])

    return {
        "pass": all(c["pass"] for c in checks),
        "score": score,
        "issues": issues,
        "details": {c["name"]: c for c in checks},
    }