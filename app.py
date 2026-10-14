"""
app.py
------
Entry point for the Job Analyzer Agent.

All real logic lives in `src/`:
    src/extractors.py  — pull text from PDF / Word / image
    src/analyzers.py   — grammar, sections, ATS, scoring, keyword match
    src/ai_agents.py   — Cohere-powered agents (feedback, critic, rewriter, job match)
    src/ui.py          — Gradio interface

This file only:
    1. Loads environment variables
    2. Validates that everything is importable
    3. Launches the UI
"""

import os
import sys
from dotenv import load_dotenv


def main():
    # ---------- 1. Load .env ----------
    load_dotenv()

    cohere_ok = bool(os.getenv("COHERE_API_KEY"))
    ocr_ok = bool(os.getenv("OCR_SPACE_KEY"))

    print("=" * 55)
    print("  Job Analyzer Agent")
    print("=" * 55)
    print(f"  Cohere API key   : {'✅ loaded' if cohere_ok else '❌ missing'}")
    print(f"  OCR.Space key    : {'✅ loaded' if ocr_ok else '❌ missing'}")
    print("=" * 55)

    if not cohere_ok:
        print("\n⚠️  COHERE_API_KEY is not set.")
        print("   The app will run, but AI features will be disabled.")
        print("   Get a free key: https://dashboard.cohere.com/api-keys")
        print("   Then add: COHERE_API_KEY=your_key_here  →  .env\n")

    # ---------- 2. Import the UI (also validates src/ modules) ----------
    try:
        from src.ui import launch_ui
    except ImportError as e:
        print(f"\n❌ Failed to import src modules: {e}")
        print("   Make sure you are running from the project root and that")
        print("   the `src/` folder exists with the four modules.")
        sys.exit(1)

    # ---------- 3. Launch ----------
    print("\n🚀 Starting Gradio app...")
    print("   Local URL will be shown below. Press Ctrl+C to stop.\n")
    launch_ui(share=False)


if __name__ == "__main__":
    main()