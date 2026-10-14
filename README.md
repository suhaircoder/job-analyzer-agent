<div align="center">

# 📄 Job Analyzer Agent

**Upload a CV → analyze it → rewrite it → match it to a job.**

A multi-agent system that scores CVs, checks ATS-friendliness, gives recruiter-level critique, rewrites the CV, and matches it against a job description.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Gradio](https://img.shields.io/badge/Gradio-6.x-FF7C00?logo=gradio&logoColor=white)](https://gradio.app/)
[![Cohere](https://img.shields.io/badge/Cohere-API-39594D?logo=cohere&logoColor=white)](https://cohere.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Features](#-features) · [Demo](#-demo) · [Quick Start](#-quick-start) · [Architecture](#-architecture) · [Roadmap](#-roadmap)

</div>

---

## ✨ Features

- **📊 CV Analysis** — Grammar & spelling, missing sections, ATS-friendliness, weighted overall score
- **🤖 AI Feedback** — Prioritized, actionable suggestions (not generic advice)
- **🧐 Recruiter Critique** — Impact, tone, and storytelling — what a hiring manager actually notices
- **✨ CV Rewriting** — LLM rewrites the CV, fixing every identified issue and adding missing sections
- **🎯 Job Matching** — Paste a job description, see the match %, missing keywords, and tailoring advice
- **📂 Multi-format** — Reads PDF, Word (`.docx`), and images (via OCR)

---

## 🖼 Demo

> Add a screenshot to `assets/screenshot.png` and it will render here.

![Job Analyzer Agent Screenshot](assets/screenshot.png)

---

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/suhaircoder/job-analyzer-agent.git
cd job-analyzer-agent