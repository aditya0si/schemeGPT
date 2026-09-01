# EXECUTE NOW — write files immediately, no planning phase

Polish the README of `C:/Users/oliad/Desktop/schemeGPT/` (case-insensitive lookup) for GitHub.

## What to do
1. Open `schemeGPT/README.md` and KEEP its existing structure (badges, table of contents, architecture, etc.).
2. ADD a **1-paragraph tagline** at the very top (3 sentences max).
3. ADD a **Demo GIF / screenshot placeholder** after the tagline.
4. ADD a **Why SchemeGPT** section — 2-3 sentences on the problem (Indian government schemes are fragmented across 30+ portals, eligibility criteria overlap, language barriers).
5. ADD a **Quick numbers** row — 5-6 bullet stats: "~3,200 scheme docs", "RRF hybrid retrieval", "RAGAS 4-metric gate", "FastAPI + Next.js 15", "Bilingual EN/HI", "Quote-verified answers".
6. SHARPEN the **Features** section — 6-8 bullets, each a single sharp sentence, no marketing fluff.
7. ADD a **Comparison vs naive RAG** table — naive RAG vs SchemeGPT across 4 metrics.
8. ADD a **Sample query & answer** section — one realistic user query, the system response (with cited quotes), and a JSON trace of the agent loop.
9. ADD a **Deployment** section — Docker Compose one-liner, env vars table, ports.
10. ADD a **Roadmap** — 4-6 checkboxes.
11. ADD **License** footer.

## Constraints
- README target: 400-550 lines
- Tone: engineer-to-engineer, NOT marketing copy.
- No "revolutionary", "game-changing", "powerful", "robust", "cutting-edge"
- Do NOT modify code, Dockerfiles, or pyproject.toml.
- Do NOT change existing badges.

## Acceptance
- README renders correctly on GitHub
- Length between 400-550 lines
- Output ends with: "README OK: X lines"