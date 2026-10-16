"""
storage.py
----------
Persistence layer for the Job Analyzer Agent.

Everything that reads or writes user data goes through this module.

Layout:
    data/
    ├── profile.json                    ← master CV (structured)
    └── versions/
        ├── google-ml-engineer.json     ← tailored CV per job
        └── meta-research.json

All files are UTF-8 encoded JSON.
"""

import json
import os
import re
from datetime import datetime


# ---------- Paths ----------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
VERSIONS_DIR = os.path.join(DATA_DIR, "versions")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")


# ---------- Low-level JSON helpers ----------
def load_json(path: str, default=None):
    """
    Load JSON from `path`.

    Returns `default` if:
    - the file doesn't exist
    - the file is corrupted / not valid JSON
    - the file can't be read
    """
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: str, data) -> None:
    """
    Save `data` as pretty-printed JSON to `path`.
    Creates parent folders automatically.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------- Profile ----------
EMPTY_PROFILE = {
    "name": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin": "",
    "github": "",
    "summary": "",
    "experience": [],
    "education": [],
    "skills": [],
    "projects": [],
    "updated_at": "",
}


def load_profile() -> dict:
    """Load the master profile. Returns an empty profile if none exists."""
    profile = load_json(PROFILE_PATH, default=None)
    if profile is None:
        return dict(EMPTY_PROFILE)
    # Merge with EMPTY_PROFILE so missing keys get defaults
    merged = dict(EMPTY_PROFILE)
    merged.update(profile)
    return merged


def save_profile(profile: dict) -> None:
    """Save the master profile, stamping the update time."""
    profile = dict(profile)  # don't mutate caller's dict
    profile["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    save_json(PROFILE_PATH, profile)


def has_profile() -> bool:
    """True if a master profile has been saved."""
    profile = load_json(PROFILE_PATH, default=None)
    return bool(profile and profile.get("name"))


# ---------- Versioned CVs (tailored per job) ----------
def _slugify(text: str) -> str:
    """Turn any text into a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)      # drop everything except word chars
    text = re.sub(r"[\s_-]+", "-", text)      # spaces → hyphens
    return text.strip("-") or "untitled"


def version_path(slug: str) -> str:
    """Return the full path for a version's JSON file."""
    return os.path.join(VERSIONS_DIR, f"{_slugify(slug)}.json")


def save_version(slug: str, data: dict) -> str:
    """
    Save a tailored CV version.

    Returns the slug that was used (so caller can link to it).
    """
    slug = _slugify(slug)
    data = dict(data)
    data["slug"] = slug
    data["saved_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    save_json(version_path(slug), data)
    return slug


def load_version(slug: str) -> dict | None:
    """Load a version by slug. Returns None if not found."""
    return load_json(version_path(slug), default=None)


def list_versions() -> list[dict]:
    """
    Return metadata for every saved version.

    Sorted newest first.
    """
    if not os.path.isdir(VERSIONS_DIR):
        return []

    versions = []
    for filename in os.listdir(VERSIONS_DIR):
        if not filename.endswith(".json"):
            continue
        slug = filename[:-5]
        data = load_json(os.path.join(VERSIONS_DIR, filename), default={})
        versions.append({
            "slug": slug,
            "job_title": data.get("job_title", ""),
            "company": data.get("company", ""),
            "saved_at": data.get("saved_at", ""),
        })

    versions.sort(key=lambda v: v["saved_at"], reverse=True)
    return versions


def delete_version(slug: str) -> bool:
    """Delete a saved version. Returns True if deleted, False if not found."""
    path = version_path(slug)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True