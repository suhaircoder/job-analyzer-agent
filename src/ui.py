"""
ui.py
-----
Beautiful Gradio interface for the Job Analyzer Agent.

Tabs:
    1. My Profile      — upload CV, parse, save master profile
    2. Analyze CV      — original analyzer (kept)
    3. Tailor for Job  — paste JD, generate tailored CV
    4. My Library      — browse + download saved versions
"""

import os
import gradio as gr

from src.extractors import extract_text, is_extraction_error
from src.analyzers import (
    check_grammar,
    detect_missing_sections,
    ats_score,
    overall_score,
    grade_badge,
    keyword_match,
)
from src.ai_agents import (
    feedback_agent,
    critic_agent,
    rewriter_agent,
    job_match_agent,
    is_available,
)
from src.storage import (
    load_profile, save_profile, has_profile,
    save_version, load_version, list_versions, delete_version,
)
from src.profile_parser import parse_profile
from src.jd_analyzer import analyze_jd, make_slug
from src.cv_tailor import tailor_cv


# ================== Custom CSS ==================
CUSTOM_CSS = """
.gradio-container {
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif !important;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%) !important;
    max-width: 1200px !important;
    margin: auto !important;
}
#hero {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
    color: white; padding: 32px 40px; border-radius: 20px;
    margin-bottom: 24px;
    box-shadow: 0 12px 32px rgba(99, 102, 241, 0.25);
}
#hero h1 { margin: 0 0 8px 0; font-size: 34px; font-weight: 800; letter-spacing: -0.02em; }
#hero p { margin: 0; opacity: 0.92; font-size: 16px; }
#hero .badges { margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap; }
#hero .badge {
    background: rgba(255,255,255,0.18); padding: 6px 14px;
    border-radius: 999px; font-size: 13px; font-weight: 500;
}
.card {
    background: white !important; border-radius: 16px !important;
    padding: 20px !important;
    box-shadow: 0 4px 16px rgba(15,23,42,0.06) !important;
    border: 1px solid #e2e8f0 !important;
}
button.primary {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    border: none !important; border-radius: 12px !important;
    font-weight: 600 !important;
    box-shadow: 0 6px 16px rgba(99,102,241,0.35) !important;
}
textarea, input[type="text"], input[type="password"] {
    border-radius: 10px !important; border: 1px solid #cbd5e1 !important;
}
.report-markdown code {
    background: #eef2ff; color: #4338ca;
    padding: 2px 6px; border-radius: 4px;
}
"""


# ================== Helpers ==================
def _score_bar(score: int) -> str:
    filled = score // 5
    return "█" * filled + "░" * (20 - filled)


def _score_color(score: int) -> str:
    if score >= 85: return "#10b981"
    if score >= 70: return "#84cc16"
    if score >= 50: return "#f59e0b"
    return "#f43f5e"


def _profile_status_md() -> str:
    if not has_profile():
        return "### ⚠️ No profile saved yet\nUpload your CV above to create your master profile."
    profile = load_profile()
    n_exp = len(profile.get("experience", []))
    n_skills = len(profile.get("skills", []))
    return f"""### ✅ Master Profile Loaded

**{profile.get('name', 'Unknown')}** — {profile.get('email', '')}
- 📄 {n_exp} experience entries
- 🛠️ {n_skills} skills
- Last updated: `{profile.get('updated_at', 'unknown')}`
"""


# ================== Tab 1: My Profile ==================
def profile_tab(file, ocr_key):
    if file is None:
        return "⚠️ Upload a CV first.", ""

    file_path = file.name
    text = extract_text(file_path, ocr_api_key=ocr_key)
    if is_extraction_error(text):
        return f"⚠️ {text}", ""

    profile, error = parse_profile(text)
    if error and not profile.get("name"):
        return f"⚠️ {error}", text

    save_profile(profile)

    import json
    preview = json.dumps(profile, indent=2, ensure_ascii=False)
    status = _profile_status_md()
    if error:
        status += f"\n\n⚠️ {error}"
    return status, preview


# ================== Tab 2: Analyze CV ==================
def analyze_tab(file, ocr_key):
    if file is None:
        return "⚠️ Please upload a file first.", "", {}

    file_path = file.name
    text = extract_text(file_path, ocr_api_key=ocr_key)
    if is_extraction_error(text):
        return f"### ⚠️ {text}", "", {}

    grammar_issues = check_grammar(text)
    missing_sections = detect_missing_sections(text)
    ats, ats_issues = ats_score(text)
    score = overall_score(grammar_issues, missing_sections, ats, text)
    badge = grade_badge(score)
    feedback = feedback_agent(text, grammar_issues, missing_sections, ats_issues)

    color = _score_color(score)
    report = f"""## 📊 CV Analysis Report

<div style="display:flex;align-items:center;gap:20px;margin:12px 0 20px 0;">
<div style="font-size:52px;font-weight:800;color:{color};">{score}</div>
<div><div style="font-size:22px;font-weight:700;">{badge}</div>
<div style="font-size:13px;color:#64748b;">out of 100</div></div></div>

`{_score_bar(score)}`

---

### 🖥️ ATS-Friendliness — **{ats}/100**
"""
    if ats_issues:
        for issue in ats_issues:
            report += f"- ⚠️ {issue}\n"
    else:
        report += "- ✅ No ATS blockers detected\n"

    report += "\n### 📑 Sections\n"
    if missing_sections:
        for s in missing_sections:
            report += f"- ❌ **{s.title()}** — missing\n"
    else:
        report += "- ✅ All standard sections present\n"

    report += f"\n### 🔤 Grammar & Spelling — **{len(grammar_issues)} issues**\n"
    for i, err in enumerate(grammar_issues[:8], 1):
        sugg = ", ".join(err["replacements"]) if err["replacements"] else "—"
        report += f"**{i}.** {err['message']}  \n   💡 *{sugg}*\n\n"

    report += f"\n---\n\n### 🤖 Prioritized Suggestions\n{feedback}\n"

    state = {"text": text, "grammar_issues": grammar_issues,
             "missing_sections": missing_sections, "score": score}
    return report, text, state


# ================== Tab 3: Tailor for Job ==================
def tailor_tab(jd_text):
    if not has_profile():
        return "⚠️ Please create your master profile in **Tab 1** first.", None, ""

    if not jd_text or not jd_text.strip():
        return "⚠️ Paste a job description first.", None, ""

    profile = load_profile()

    # Progress tracking
    progress_lines = []

    def progress_cb(msg):
        progress_lines.append(msg)
        print(f"[tailor] {msg}")

    # Analyze JD
    jd, jd_error = analyze_jd(jd_text)
    if jd_error and not jd.get("title"):
        return f"⚠️ Could not analyze JD: {jd_error}", None, ""

    # Run the pipeline
    result = tailor_cv(profile, jd, progress_cb=progress_cb)

    if not result.get("cv_markdown"):
        return "⚠️ Failed to generate CV. Check terminal for details.", None, ""

    # Save as a version
    slug_base = make_slug(jd)
    save_version(slug_base, {
        "job_title": jd.get("title", ""),
        "company": jd.get("company", ""),
        "jd": jd,
        "cv_markdown": result["cv_markdown"],
        "match": result.get("match", {}),
        "quality": result.get("quality", {}),
    })

    # Build report
    quality = result.get("quality", {})
    match_info = result.get("match", {})

    status_icon = "✅" if result.get("ok") else "⚠️"
    report = f"""## {status_icon} Tailored CV Generated

**For:** {jd.get('title', 'Unknown role')} at **{jd.get('company', 'Unknown company')}**

| Metric | Value |
|---|---|
| Match score | **{match_info.get('match_score', '?')}%** |
| Quality score | **{quality.get('score', '?')}/100** |
| Attempts | {result.get('attempts', '?')} |
| Saved as | `{slug_base}` |

**Reasoning:** {match_info.get('reasoning', '—')}

---

*Progress:*
{chr(10).join('• ' + p for p in progress_lines)}
"""

    if quality.get("issues"):
        report += f"\n\n### ⚠️ Quality Gate Issues ({len(quality['issues'])})\n"
        for issue in quality["issues"]:
            report += f"- ❌ {issue}\n"
        report += "\n*The retry loop tried 3 times but couldn't fix these. Please review manually.*\n"

    return report, result["cv_markdown"], slug_base


# ================== Tab 4: My Library ==================
def refresh_library():
    versions = list_versions()
    if not versions:
        return "### 📭 No saved versions yet\nGenerate a tailored CV in **Tab 3** to create your first one."

    md = f"### 📚 {len(versions)} Saved Versions\n\n"
    for v in versions:
        title = v.get("job_title") or "Untitled"
        company = v.get("company") or "—"
        saved = v.get("saved_at", "")
        md += f"- **{title}** at *{company}* — `{v['slug']}` (saved {saved[:10]})\n"
    return md


def load_specific_version(slug):
    if not slug or not slug.strip():
        return "Enter a slug to load."
    version = load_version(slug.strip())
    if not version:
        return f"❌ No version found with slug `{slug}`"
    return version.get("cv_markdown", "No CV content saved.")


def delete_specific_version(slug):
    if not slug or not slug.strip():
        return "Enter a slug to delete.", refresh_library()
    if delete_version(slug.strip()):
        return f"✅ Deleted `{slug}`", refresh_library()
    return f"❌ No version found with slug `{slug}`", refresh_library()


# ================== Build UI ==================
def build_ui():
    with gr.Blocks(title="Job Analyzer Agent") as demo:
        gr.HTML("""
        <div id="hero">
          <h1>📄 Job Analyzer Agent</h1>
          <p>Upload once → analyze → tailor a CV per job → save your library.</p>
          <div class="badges">
            <span class="badge">🤖 Multi-agent pipeline</span>
            <span class="badge">⚡ Cohere · LanguageTool · OCR.Space</span>
            <span class="badge">🎯 Job-tailored CVs</span>
            <span class="badge">✅ Quality-gated output</span>
          </div>
        </div>
        """)

        analyze_state = gr.State({})

        with gr.Tabs():
            # ---- Tab 1: My Profile ----
            with gr.Tab("👤 My Profile"):
                with gr.Row():
                    with gr.Column(elem_classes="card"):
                        profile_file = gr.File(
                            label="Upload your master CV",
                            file_types=[".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"],
                        )
                        profile_ocr = gr.Textbox(
                            label="OCR.Space key (only for images)",
                            type="password",
                        )
                        profile_btn = gr.Button("📥 Save as Master Profile", variant="primary", size="lg")
                        profile_status = gr.Markdown(_profile_status_md())

                    with gr.Column(elem_classes="card"):
                        gr.Markdown("### 📋 Parsed Profile (JSON)")
                        profile_preview = gr.Code(
                            label="", language="json", lines=20,
                        )

                profile_btn.click(
                    fn=profile_tab,
                    inputs=[profile_file, profile_ocr],
                    outputs=[profile_status, profile_preview],
                )

            # ---- Tab 2: Analyze CV ----
            with gr.Tab("📊 Analyze CV"):
                with gr.Row():
                    with gr.Column(elem_classes="card"):
                        gr.Markdown("### 📤 Upload")
                        analyze_file = gr.File(
                            label="PDF · Word · Image",
                            file_types=[".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"],
                        )
                        analyze_ocr = gr.Textbox(
                            label="OCR.Space key (only for images)",
                            type="password",
                        )
                        analyze_btn = gr.Button("🚀 Analyze CV", variant="primary", size="lg")

                    with gr.Column(elem_classes="card"):
                        analyze_report = gr.Markdown(
                            "*Upload a CV and click **🚀 Analyze** to see your report.*",
                            elem_classes="report-markdown",
                        )

                with gr.Accordion("📃 Extracted Text", open=False):
                    analyze_text = gr.Textbox(lines=10, buttons=["copy"])

                analyze_btn.click(
                    fn=analyze_tab,
                    inputs=[analyze_file, analyze_ocr],
                    outputs=[analyze_report, analyze_text, analyze_state],
                )

            # ---- Tab 3: Tailor for Job ----
            with gr.Tab("🎯 Tailor for Job"):
                with gr.Column(elem_classes="card"):
                    gr.Markdown("### 📋 Paste Job Description")
                    jd_input = gr.Textbox(
                        label="",
                        lines=8,
                        placeholder="Paste the full job posting here…",
                    )
                    tailor_btn = gr.Button("✨ Generate Tailored CV", variant="primary", size="lg")

                with gr.Row():
                    with gr.Column(elem_classes="card"):
                        tailor_status = gr.Markdown(
                            "*Upload a profile (Tab 1) and paste a JD above.*"
                        )
                    with gr.Column(elem_classes="card"):
                        gr.Markdown("### 📝 Tailored CV")
                        tailor_cv_output = gr.Textbox(
                            label="",
                            lines=25,
                            buttons=["copy"],
                            placeholder="Your tailored CV will appear here…",
                        )

                tailor_slug = gr.Textbox(label="Saved as slug", visible=False)

                tailor_btn.click(
                    fn=tailor_tab,
                    inputs=[jd_input],
                    outputs=[tailor_status, tailor_cv_output, tailor_slug],
                )

            # ---- Tab 4: My Library ----
            with gr.Tab("📚 My Library"):
                with gr.Column(elem_classes="card"):
                    library_md = gr.Markdown(refresh_library())
                    refresh_btn = gr.Button("🔄 Refresh", size="sm")

                with gr.Row():
                    with gr.Column(elem_classes="card"):
                        gr.Markdown("### 🔍 Load a version")
                        load_slug = gr.Textbox(label="Slug", placeholder="e.g. google-ml-engineer")
                        load_btn = gr.Button("Load", variant="secondary")
                        loaded_cv = gr.Textbox(label="CV", lines=20, buttons=["copy"])

                    with gr.Column(elem_classes="card"):
                        gr.Markdown("### 🗑️ Delete a version")
                        del_slug = gr.Textbox(label="Slug")
                        del_btn = gr.Button("Delete", variant="stop")
                        del_msg = gr.Markdown("")

                refresh_btn.click(fn=refresh_library, outputs=[library_md])
                load_btn.click(fn=load_specific_version, inputs=[load_slug], outputs=[loaded_cv])
                del_btn.click(
                    fn=delete_specific_version,
                    inputs=[del_slug],
                    outputs=[del_msg, library_md],
                )

        # ---- Footer ----
        status = "✅ Cohere connected" if is_available() else "⚠️ Cohere key not set"
        gr.HTML(f"""
        <div style="text-align:center;color:#64748b;font-size:13px;padding:16px;">
          <b>{status}</b> · Built with Gradio 6 · 
          <a href="https://github.com/suhaircoder/job-analyzer-agent" target="_blank">View on GitHub</a>
        </div>
        """)

    return demo


def launch_ui(share: bool = False):
    demo = build_ui()
    demo.launch(share=share, theme=gr.themes.Soft(), css=CUSTOM_CSS)
    return demo