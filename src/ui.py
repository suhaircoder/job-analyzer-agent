"""
ui.py
-----
Beautiful Gradio interface for the Job Analyzer Agent.

Layout:
    Header        — gradient hero with title
    Tab 1         — Analyze CV (upload + report)
    Tab 2         — Improve CV (critique + rewrite)
    Tab 3         — Job Match (JD input + results)
"""

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


# ================== Custom CSS ==================
CUSTOM_CSS = """
/* ----- Global font & background ----- */
.gradio-container {
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif !important;
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%) !important;
    max-width: 1200px !important;
    margin: auto !important;
}

/* ----- Hero header ----- */
#hero {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
    color: white;
    padding: 32px 40px;
    border-radius: 20px;
    margin-bottom: 24px;
    box-shadow: 0 12px 32px rgba(99, 102, 241, 0.25);
}
#hero h1 {
    margin: 0 0 8px 0;
    font-size: 34px;
    font-weight: 800;
    letter-spacing: -0.02em;
}
#hero p {
    margin: 0;
    opacity: 0.92;
    font-size: 16px;
}
#hero .badges {
    margin-top: 16px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
#hero .badge {
    background: rgba(255, 255, 255, 0.18);
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 500;
    backdrop-filter: blur(6px);
}

/* ----- Cards / panels ----- */
.card {
    background: white !important;
    border-radius: 16px !important;
    padding: 20px !important;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06) !important;
    border: 1px solid #e2e8f0 !important;
}

/* ----- Buttons ----- */
button.primary, .primary-btn {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    border: none !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    box-shadow: 0 6px 16px rgba(99, 102, 241, 0.35) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}
button.primary:hover, .primary-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 24px rgba(99, 102, 241, 0.45) !important;
}

button.secondary {
    background: white !important;
    color: #6366f1 !important;
    border: 2px solid #6366f1 !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
}

/* ----- Tabs ----- */
.tab-nav button {
    font-weight: 600 !important;
    font-size: 15px !important;
    border-radius: 12px 12px 0 0 !important;
}

/* ----- Report markdown styling ----- */
.report-markdown h2 {
    color: #0f172a;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 8px;
}
.report-markdown h3 {
    color: #475569;
    margin-top: 20px;
}
.report-markdown code {
    background: #eef2ff;
    color: #4338ca;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
}

/* ----- Textbox / inputs ----- */
textarea, input[type="text"], input[type="password"] {
    border-radius: 10px !important;
    border: 1px solid #cbd5e1 !important;
    font-family: 'Inter', sans-serif !important;
}
textarea:focus, input:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
    outline: none !important;
}

/* ----- Footer ----- */
#footer {
    text-align: center;
    color: #64748b;
    font-size: 13px;
    margin-top: 24px;
    padding: 16px;
}
"""


# ================== Helpers ==================
def _empty_report(msg="Upload a CV and click **🚀 Analyze**."):
    return msg, "", {}


def _score_bar(score: int) -> str:
    filled = score // 5
    return "█" * filled + "░" * (20 - filled)


def _score_color(score: int) -> str:
    if score >= 85:
        return "#10b981"
    if score >= 70:
        return "#84cc16"
    if score >= 50:
        return "#f59e0b"
    return "#f43f5e"


def _render_report(score, badge, ats, ats_issues, grammar_issues, missing_sections, feedback):
    color = _score_color(score)
    report = f"""## 📊 CV Analysis Report

<div style="display:flex; align-items:center; gap:20px; margin:12px 0 20px 0;">
  <div style="font-size:52px; font-weight:800; color:{color}; font-family:'JetBrains Mono', monospace;">{score}</div>
  <div>
    <div style="font-size:22px; font-weight:700; color:#0f172a;">{badge}</div>
    <div style="font-size:13px; color:#64748b;">out of 100</div>
  </div>
</div>

`{_score_bar(score)}`

---
"""
    report += f"### 🖥️ ATS-Friendliness — **{ats}/100**\n"
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
    if len(grammar_issues) > 8:
        report += f"*…and {len(grammar_issues) - 8} more.*\n"

    report += f"\n---\n\n### 🤖 Prioritized Suggestions\n{feedback}\n"
    return report


# ================== Tab logic ==================
def analyze_tab(file, ocr_key):
    if file is None:
        return _empty_report("⚠️ Please upload a file first.")
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
    report = _render_report(score, badge, ats, ats_issues, grammar_issues, missing_sections, feedback)

    state = {
        "text": text,
        "grammar_issues": grammar_issues,
        "missing_sections": missing_sections,
        "score": score,
    }
    return report, text, state


def improve_tab(state, job_description):
    if not state or not state.get("text"):
        return "⚠️ Please analyze a CV first (Tab 1).", ""
    text = state["text"]
    grammar_issues = state.get("grammar_issues", [])
    missing_sections = state.get("missing_sections", [])
    critic = critic_agent(text, job_description=job_description)
    rewrite = rewriter_agent(text, grammar_issues, missing_sections, job_description)
    critic_md = f"### 🧐 Recruiter Critique\n\n{critic}\n"
    return critic_md, rewrite


def job_match_tab(state, job_description):
    if not state or not state.get("text"):
        return "⚠️ Please analyze a CV first (Tab 1)."
    if not job_description.strip():
        return "⚠️ Paste a job description to compare."
    text = state["text"]
    result = keyword_match(text, job_description, top_n=30)
    score, matched, missing = result["score"], result["matched"], result["missing"]
    color = _score_color(score)
    report = f"""## 🎯 Job Match Report

<div style="display:flex; align-items:center; gap:20px; margin:12px 0 20px 0;">
  <div style="font-size:52px; font-weight:800; color:{color}; font-family:'JetBrains Mono', monospace;">{score}%</div>
  <div style="font-size:16px; color:#64748b;">keyword match</div>
</div>

`{_score_bar(score)}`

---

### ✅ Matched Keywords — {len(matched)}
{", ".join(f"`{k}`" for k in matched) or "—"}

### ❌ Missing Keywords — {len(missing)}
{", ".join(f"`{k}`" for k in missing) or "—"}

---

### 💡 Tailoring Advice
{job_match_agent(text, job_description, missing)}
"""
    return report


# ================== Build UI ==================
def build_ui():
    with gr.Blocks(title="Job Analyzer Agent", css=CUSTOM_CSS) as demo:
        # ---- Hero header ----
        gr.HTML(
            """
            <div id="hero">
              <h1>📄 Job Analyzer Agent</h1>
              <p>Upload your CV → analyze it → rewrite it → match it to a job.</p>
              <div class="badges">
                <span class="badge">🤖 Multi-agent pipeline</span>
                <span class="badge">⚡ Cohere · LanguageTool · OCR.Space</span>
                <span class="badge">🆓 100% free APIs</span>
              </div>
            </div>
            """
        )

        state = gr.State({})

        with gr.Tabs():
            # ---------------- TAB 1 ----------------
            with gr.Tab("📊 Analyze CV"):
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="card"):
                        gr.Markdown("### 📤 Upload")
                        file_input = gr.File(
                            label="PDF · Word · Image",
                            file_types=[".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"],
                        )
                        ocr_key_input = gr.Textbox(
                            label="OCR.Space key (only for images)",
                            type="password",
                            placeholder="Paste your key for image CVs",
                        )
                        analyze_btn = gr.Button("🚀 Analyze CV", variant="primary", size="lg")

                    with gr.Column(scale=2, elem_classes="card"):
                        report_output = gr.Markdown(
                            value="*Upload a CV and click **🚀 Analyze** to see your report.*",
                            elem_classes="report-markdown",
                        )

                with gr.Accordion("📃 Extracted Text (raw)", open=False):
                    text_output = gr.Textbox(label="", lines=12, buttons=["copy"])

                analyze_btn.click(
                    fn=analyze_tab,
                    inputs=[file_input, ocr_key_input],
                    outputs=[report_output, text_output, state],
                )

            # ---------------- TAB 2 ----------------
            with gr.Tab("✨ Improve CV"):
                with gr.Column(elem_classes="card"):
                    gr.Markdown("### 🎯 Target Job (optional)\nPaste a job description to tailor the rewrite toward it.")
                    jd_improve = gr.Textbox(
                        label="",
                        lines=5,
                        placeholder="Paste the job posting here…",
                    )
                    improve_btn = gr.Button("✨ Generate Improved CV", variant="primary", size="lg")

                with gr.Row():
                    with gr.Column(elem_classes="card"):
                        critic_output = gr.Markdown(
                            "### 🧐 Recruiter Critique\n\n*Click Generate to see what a hiring manager would say.*"
                        )
                    with gr.Column(elem_classes="card"):
                        improved_output = gr.Textbox(
                            label="📝 Rewritten CV",
                            lines=25,
                            buttons=["copy"],
                            placeholder="Your improved CV will appear here…",
                        )

                improve_btn.click(
                    fn=improve_tab,
                    inputs=[state, jd_improve],
                    outputs=[critic_output, improved_output],
                )

            # ---------------- TAB 3 ----------------
            with gr.Tab("🎯 Job Match"):
                with gr.Column(elem_classes="card"):
                    gr.Markdown("### 🔍 Compare your CV to a job posting\nSee the match % and what keywords you're missing.")
                    jd_match = gr.Textbox(
                        label="Job description",
                        lines=8,
                        placeholder="Paste the job posting here…",
                    )
                    match_btn = gr.Button("🎯 Match CV to Job", variant="primary", size="lg")

                match_output = gr.Markdown(
                    value="*Upload + analyze a CV in Tab 1 first, then run a match here.*",
                    elem_classes="report-markdown",
                )

                match_btn.click(
                    fn=job_match_tab,
                    inputs=[state, jd_match],
                    outputs=[match_output],
                )

        # ---- Footer ----
        status = "✅ Cohere connected" if is_available() else "⚠️ Cohere key not set"
        gr.HTML(
            f"""
            <div id="footer">
              <b>{status}</b> · Built with Gradio 6 · 
              <a href="https://github.com" target="_blank">View on GitHub</a>
            </div>
            """
        )

    return demo


def launch_ui(share: bool = False):
    demo = build_ui()
    demo.launch(share=share, theme=gr.themes.Soft())
    return demo