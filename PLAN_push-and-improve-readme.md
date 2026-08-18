# PLAN_push-and-improve-readme.md

## SECTION A — GOAL DEFINITION

1. **What is being built or changed?**
   - Comprehensive enhancement of `README.md` for SchemeGPT to include detailed architecture descriptions, feature matrices, tech stack breakdowns, API reference docs, setup instructions, and relevant AI/RAG domain keywords.
   - Safe setup of git remote `origin` pointing to `https://github.com/aditya0si/schemeGPT.git`, security audit of tracked/ignored files (confirming `.env` and secrets are ignored), staging, committing, and pushing the codebase to the remote `main` branch.

2. **What does "done" look like — what is the observable outcome?**
   - `README.md` is updated with exhaustive project documentation, architecture flow, feature overview, evaluation framework details, and target keywords.
   - `.gitignore` verified so no sensitive data (`.env`, secrets, caches) is committed.
   - Remote `origin` configured to `https://github.com/aditya0si/schemeGPT.git`.
   - All local changes committed cleanly and pushed successfully to `main` on GitHub.

3. **What is explicitly out of scope for this task?**
   - Modifying backend core code logic in `app/`, database schemas, or frontend application components (`web/`, `streamlit_app.py`).
   - Setting up cloud server infrastructure, CI/CD deployment pipelines, or third-party DNS.

---

## SECTION B — TECH STACK

- **Languages:** Python 3.11+, TypeScript, SQL, Markdown
- **Backend API & RAG:** FastAPI, Uvicorn, LangChain (`ChatGroq` with `llama-3.3-70b-versatile` & `llama-3.1-8b-instant`), `sentence-transformers` (`all-MiniLM-L6-v2`)
- **Database & Vector Search:** PostgreSQL 16 + `pgvector`, Reciprocal Rank Fusion (pgvector cosine + Postgres Full-Text Search)
- **Frontend Applications:** Next.js 15 (React 19, Tailwind CSS) & Streamlit Chat Interface (`streamlit_app.py`)
- **Evaluation & Tools:** Custom evaluation suite (`eval/run_eval.py`), Docker & Docker Compose, Git

---

## SECTION C — SESSION MODULARIZATION

### Session 1: README Documentation & Keyword Optimization
- **OBJECTIVE:** Upgrade `README.md` with rich documentation covering project scope, architecture, tech stack, key features, setup steps, evaluation suite, and AI/RAG keywords.
- **SCOPE:** `README.md`
- **OUTPUT:** Updated `README.md` containing badges, searchable keywords, detailed component breakdowns, API overview, and setup instructions.
- **CONNECTS TO:** Session 2 depends on the finished README file being present in the repository before staging and pushing.
- **FAILURE SURFACE:** Formatting/syntax errors in Markdown, broken relative links to `docs/` or `eval/`, or omitted key feature descriptions.

---

### Session 2: Security Audit, Git Remote Setup & Repository Push
- **OBJECTIVE:** Verify `.gitignore` to ensure `.env` and secrets remain untracked, add git remote `https://github.com/aditya0si/schemeGPT.git`, commit changes, and push safely to `main`.
- **SCOPE:** Git configuration (`.git/config`), `.gitignore`, git stage/commit/push commands.
- **OUTPUT:** Verified git status and successful push of the repository to `https://github.com/aditya0si/schemeGPT.git`.
- **CONNECTS TO:** Final task completion and verification.
- **FAILURE SURFACE:** Remote authentication failure, branch mismatches, or accidental inclusion of untracked secret files.

---

## SECTION D — PROGRESS CHECKLIST

- [x] Session 1: README Documentation & Keyword Optimization
  - [x] Draft comprehensive architecture & feature sections in `README.md`
  - [x] Add relevant AI Engineering, RAG, & Indian Government Schemes keywords
  - [x] Verify relative links and markdown rendering
- [ ] Session 2: Security Audit, Git Remote Setup & Repository Push
  - [ ] Audit `.gitignore` and ensure no `.env` or sensitive files are staged
  - [ ] Configure git remote `origin` to `https://github.com/aditya0si/schemeGPT.git`
  - [ ] Commit README updates with clear commit message
  - [ ] Push local `main` branch to remote repository cleanly
