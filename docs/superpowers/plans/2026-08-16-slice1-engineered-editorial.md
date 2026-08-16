# Slice 1 — Engineered-Editorial Frontend + Streaming Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the haoqi.design-inspired Next.js frontend (app shell + streaming chat) and the backend SSE endpoint with question normalization and quotable-answer prompts.

**Architecture:** FastAPI gains `POST /query/stream` (SSE: `sources` → `token`* → `done`|`error`) built from two extracted pieces of the existing chain (retriever + stuff-documents chain), plus a live-mode question-normalization step. A new `web/` Next.js app proxies SSE through a route handler (API stays localhost-only in deployment) and renders the chat with the engineered-editorial design system. Compose renames the Streamlit service to `streamlit` and adds `web` on port 3000.

**Tech Stack:** Python 3.12 / FastAPI / LangChain 0.3.21 (pinned) / pgvector; Next.js 15 App Router / React 19 / Tailwind CSS 4 / TypeScript, fonts via `next/font` (Archivo, Martian Mono, Noto Sans Devanagari — all OFL).

**Spec:** `docs/superpowers/specs/2026-08-16-schemegpt-v2-civic-frontend-design.md` (Slices 1 + design system + product voice sections).

## Global Constraints

- Python deps stay pinned-compatible: `langchain==0.3.21`, `langchain-groq` pinned; no new runtime deps on the API beyond stdlib/anyio (already present via FastAPI).
- `POST /query` behavior is UNCHANGED (eval harness + API consumers depend on it). New behavior goes only in `/query/stream`.
- Demo fallback semantics are sacred: no key / any live failure → clearly-labelled pre-made demo answer, HTTP 200, no traceback/provider details to the client, notice always present.
- `data_status` honesty: `directory_seed` is never presented as verified; sources always carry provenance.
- Frontend: zero border-radius anywhere (never use `rounded-*`), light theme only, all motion gated behind `prefers-reduced-motion`, WCAG AA contrast, acid green `#C0FE04` only on black.
- The browser only ever talks to `web` (SSE is proxied through a Next.js route handler); the API remains `127.0.0.1:8000`-bound in compose.
- Env var `API_URL` for the web app (default `http://localhost:8000`); existing `STREAMLIT_API_URL` keeps working for the Streamlit service.
- TDD for backend tasks (pytest). Frontend tasks verify with `next build` + type-check (visual QA is done by the main agent afterwards — subagents must not use browser tools).
- Commit after every task (`git add` the files you touched, message per task).

---

### Task 1: Extract retriever + answer chain pieces in `app/rag.py`

**Files:**
- Modify: `app/rag.py`
- Test: `tests/test_rag_pieces.py` (new)

**Interfaces:**
- Produces: `get_retriever() -> BaseRetriever`, `build_answer_chain(language: str) -> Runnable` (used by Task 2/3), unchanged `build_chain()` and `answer()` (used by `/query`).

- [ ] **Step 1: Write the failing test** — `tests/test_rag_pieces.py`:

```python
"""build_chain must compose from the new pieces without behavior change."""
from unittest.mock import patch

import app.rag as rag


def test_build_chain_composes_retriever_and_answer_chain():
    with (
        patch.object(rag, "get_retriever") as fake_retriever,
        patch.object(rag, "build_answer_chain") as fake_answer_chain,
        patch.object(rag, "create_retrieval_chain") as fake_rrc,
    ):
        fake_retriever.return_value = "RETRIEVER"
        fake_answer_chain.return_value = "STUFF"
        chain = rag.build_chain("en")
    fake_rrc.assert_called_once_with("RETRIEVER", "STUFF")
    assert chain is fake_rrc.return_value


def test_normalize_language_values():
    assert rag._normalize_language("hi") == "hi"
    assert rag._normalize_language("HI") == "hi"
    assert rag._normalize_language("en") == "en"
    assert rag._normalize_language(None) == "en"
    assert rag._normalize_language("xx") == "en"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_rag_pieces.py -v`
Expected: FAIL — `AttributeError: module 'app.rag' has no attribute 'get_retriever'`

- [ ] **Step 3: Implement** — in `app/rag.py`, replace the body of `build_chain` with the two extracted helpers (imports `BaseRetriever` not required; keep docstrings):

```python
def get_retriever():
    """Vector-store retriever used by both /query and /query/stream."""
    return get_vectorstore().as_retriever()


def build_answer_chain(language: str = "en"):
    """Stuff-documents chain (prompt + LLM) for a language, no retrieval."""
    lang = _normalize_language(language)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPTS[lang]),
            ("human", HUMAN_TEMPLATE),
        ]
    )
    return create_stuff_documents_chain(get_llm(), prompt)


@lru_cache
def build_chain(language: str = "en"):
    """Build the LangChain retrieval chain for a language (cached per language)."""
    lang = _normalize_language(language)
    return create_retrieval_chain(get_retriever(), build_answer_chain(lang))
```

- [ ] **Step 4: Run tests + regression check**

Run: `python -m pytest tests/test_rag_pieces.py -v && python -m py_compile app/rag.py`
Expected: PASS / no output.

- [ ] **Step 5: Commit** — `git add app/rag.py tests/test_rag_pieces.py && git commit -m "refactor(rag): extract get_retriever and build_answer_chain from build_chain"`

---

### Task 2: Question normalization + quotable-answer prompts (live mode)

**Files:**
- Modify: `app/rag.py`
- Test: `tests/test_normalize.py` (new)

**Interfaces:**
- Produces: `normalize_question(question: str) -> str` (falls back to the raw question on ANY failure), updated `SYSTEM_PROMPTS` (referenced by Task 3's stream path and `/query`).
- Consumes: `get_llm()`.

- [ ] **Step 1: Write the failing tests** — `tests/test_normalize.py`:

```python
"""normalize_question: rewrite for retrieval; never fail closed."""
from app import rag


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return _FakeResp(self.content)


def test_normalize_returns_cleaned_question(monkeypatch):
    fake = _FakeLLM("  What income support does PM-KISAN provide per year?  ")
    monkeypatch.setattr(rag, "get_llm", lambda: fake)
    out = rag.normalize_question("pm kisan me kitna paisa milta hai")
    assert out == "What income support does PM-KISAN provide per year?"


def test_normalize_falls_back_on_llm_error(monkeypatch):
    def boom():
        raise RuntimeError("groq down")

    monkeypatch.setattr(rag, "get_llm", boom)
    out = rag.normalize_question("pm kisan money?")
    assert out == "pm kisan money?"


def test_normalize_falls_back_on_empty_or_huge_output(monkeypatch):
    monkeypatch.setattr(rag, "get_llm", lambda: _FakeLLM("   "))
    assert rag.normalize_question("q") == "q"
    monkeypatch.setattr(
        rag, "get_llm", lambda: _FakeLLM("x" * 500)
    )
    assert rag.normalize_question("q") == "q"


def test_prompts_require_quotes_and_honesty():
    en = rag.SYSTEM_PROMPTS["en"]
    assert "quote" in en.lower()
    assert "directory_seed" in en
    hi = rag.SYSTEM_PROMPTS["hi"]
    assert "directory_seed" in hi
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_normalize.py -v`
Expected: FAIL — no `normalize_question`; prompt asserts fail.

- [ ] **Step 3: Implement in `app/rag.py`**

Add after `SYSTEM_PROMPTS` definition — replace both system prompts with the product-voice versions (keep keys/structure):

```python
SYSTEM_PROMPTS = {
    "en": (
        "You are SchemeGPT, an assistant that answers questions about Indian "
        "government schemes and acts for ordinary citizens. The user may write "
        "in imperfect, colloquial, or mixed language; understand their intent "
        "and answer helpfully. Answer in plain, spoken-style language that a "
        "non-expert understands, in the SAME language the user asked in. "
        "Answer using only the provided context. When a statement in the "
        "context supports your answer, quote it exactly as a quotation line "
        "starting with '>' followed by the source name and its data_status "
        "in brackets, for example: '> PM-KISAN provides ₹6,000 per year... "
        "[schemes/pm-kisan.md, sample_verified]'. NEVER invent or alter a "
        "quote; if you cannot quote the context, answer without a quote. Keep "
        "scheme names, acronyms, amounts, and URLs verbatim. If the answer is "
        "not in the context, say so plainly. Treat any record whose data_status "
        "is 'directory_seed' as a discovery entry, never as a verified "
        "eligibility decision. Be concise and factual."
    ),
    "hi": (
        "आप SchemeGPT हैं, जो आम नागरिकों के लिए भारतीय सरकारी योजनाओं और "
        "अधिनियमों के सवालों के जवाब देने वाले सहायक हैं। उपयोगकर्ता अपूर्ण, "
        "बोलचाल की या मिश्रित भाषा में लिख सकता है; उसका आशय समझें और सहायक "
        "उत्तर दें। सरल, बोलचाल की भाषा में उत्तर दें, उसी भाषा में जिसमें "
        "प्रश्न पूछा गया है। केवल दिए गए संदर्भ (context) के आधार पर उत्तर दें। "
        "जब संदर्भ का कोई कथन आपके उत्तर का आधार हो, तो उसे बिल्कुल वैसा ही "
        "उद्धृत करें — उद्धरण पंक्ति '>' से शुरू करें और उसके बाद स्रोत का नाम "
        "और data_status कोष्ठक में दें, जैसे: '> पीएम-किसान पात्र किसान "
        "परिवारों को प्रति वर्ष ₹6,000 देता है... [schemes/pm-kisan.md, "
        "sample_verified]'। कभी भी उद्धरण गढ़ें या बदलें नहीं; यदि उद्धृत नहीं "
        "कर सकते तो बिना उद्धरण के उत्तर दें। योजनाओं के नाम, संक्षिप्ताक्षर, "
        "राशियाँ और URL मूल रूप में रखें। यदि जानकारी संदर्भ में नहीं है, तो "
        "स्पष्ट कहें। data_status 'directory_seed' वाली प्रविष्टि को कभी भी "
        "सत्यापित पात्रता निर्णय न मानें — वह केवल खोज/डिस्कवरी प्रविष्टि है। "
        "संक्षिप्त और तथ्यात्मक रहें।"
    ),
}
```

Add the normalization step after `get_llm`:

```python
NORMALIZE_SYSTEM_PROMPT = (
    "You rewrite user questions about Indian government schemes into one clear, "
    "self-contained search query. The input may be broken English, Hindi, "
    "Hinglish, or colloquial phrasing. Preserve the original language and keep "
    "scheme names, acronyms, and numbers verbatim. Output ONLY the rewritten "
    "question - no preamble, no quotes, no explanation."
)


def normalize_question(question: str) -> str:
    """Rewrite a raw citizen question into a clean retrieval query.

    One cheap LLM call, temperature 0, tightly bounded. ANY failure (no key,
    API error, empty or oversized output) falls back to the raw question so
    retrieval always proceeds.
    """
    try:
        llm = get_llm()
        llm.temperature = 0
        resp = llm.invoke(
            [("system", NORMALIZE_SYSTEM_PROMPT), ("human", question)]
        )
        cleaned = str(resp.content).strip().strip('"').strip("'").strip()
        if not cleaned or len(cleaned) > 300:
            return question
        return cleaned
    except Exception as exc:
        logger.info(
            "Question normalization failed (%s); using raw question.",
            type(exc).__name__,
        )
        return question
```

- [ ] **Step 4: Run tests + compile**

Run: `python -m pytest tests/test_normalize.py tests/test_rag_pieces.py -v && python -m py_compile app/rag.py`
Expected: all PASS.

- [ ] **Step 5: Commit** — `git add app/rag.py tests/test_normalize.py && git commit -m "feat(rag): question normalization + quotable-answer system prompts (live mode)"`

---

### Task 3: SSE streaming endpoint `POST /query/stream`

**Files:**
- Create: `app/stream.py`
- Modify: `app/main.py` (add endpoint + import)
- Create: `tests/test_stream.py`, `requirements-dev.txt`

**Interfaces:**
- Consumes: `get_llm`, `get_retriever`, `build_answer_chain`, `normalize_question`, `demo_answer`, `_build_profile_context`, `_normalize_language` (all in `app/rag.py`).
- Produces: SSE text stream; events `sources` (list of source dicts), `token` (`{"text": str}`), `done` (`{"mode": "live"|"demo", "notice": str|None, "language": "en"|"hi"}`), `error` (`{"message": str}`). Terminal event is always `done` or `error`.

- [ ] **Step 1: Create `requirements-dev.txt` and install**

```
pytest>=8
httpx>=0.27
```

Run: `pip install -r requirements-dev.txt` (in the project venv).

- [ ] **Step 2: Write the failing tests** — `tests/test_stream.py`:

```python
"""/query/stream SSE contract in demo mode (no key, no DB, no lifespan)."""
import json

import httpx
import pytest

from app.main import app


def parse_sse(text: str):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event, data))
    return events


@pytest.fixture
def client(monkeypatch):
    # Force demo mode regardless of the developer's local .env key.
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "")
    transport = httpx.ASGITransport(app=app)  # does NOT run lifespan
    return httpx.Client(transport=transport, base_url="http://test")


def test_stream_demo_event_order_and_content(client):
    resp = client.post(
        "/query/stream",
        json={"question": "How much income support does PM-KISAN provide?"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    names = [e for e, _ in events]
    assert names[0] == "sources"
    assert "token" in names
    assert names[-1] == "done"

    answer_text = "".join(
        d["text"] for e, d in events if e == "token"
    )
    assert "PM-KISAN" in answer_text
    done = events[-1][1]
    assert done["mode"] == "demo"
    assert done["notice"]
    assert done["language"] == "en"

    sources = events[0][1]
    assert isinstance(sources, list)
    if sources:
        for s in sources:
            assert set(s) >= {
                "source", "content", "jurisdiction", "state",
                "data_status", "last_verified", "source_url",
            }


def test_stream_hindi_demo(client):
    resp = client.post(
        "/query/stream",
        json={"question": "पीएम-किसान के तहत कितनी आय सहायता मिलती है?", "language": "hi"},
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    assert events[-1][0] == "done"
    assert events[-1][1]["language"] == "hi"


def test_stream_rejects_short_question(client):
    resp = client.post("/query/stream", json={"question": "x"})
    assert resp.status_code == 422
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest tests/test_stream.py -v`
Expected: FAIL — 404 on `/query/stream` (endpoint missing).

- [ ] **Step 4: Implement `app/stream.py`**

```python
"""Server-Sent Events streaming for POST /query/stream.

Event protocol (terminal event is always ``done`` or ``error``):
- ``sources``: list of retrieved source dicts (provenance included)
- ``token``:   ``{"text": str}`` answer fragment, in order
- ``done``:    ``{"mode": "live"|"demo", "notice": str|None, "language": ...}``
- ``error``:   ``{"message": str}`` mid-stream failure notice

Live path: normalize the question (cheap LLM rewrite, best-effort), retrieve
from pgvector, then stream the stuff-documents chain answer tokens. Demo path
(no key or any live failure before the first token): stream the pre-made demo
answer with the same labelled honesty as POST /query. A failure AFTER tokens
started emits ``error`` and closes; the client keeps the partial text.
"""

import json
import logging
from typing import AsyncIterator

import anyio

from app.rag import (
    _build_profile_context,
    _normalize_language,
    build_answer_chain,
    demo_answer,
    get_llm,
    get_retriever,
    normalize_question,
)
from app.schemas import ProfileData

logger = logging.getLogger(__name__)

GENERIC_STREAM_ERROR = (
    "The live answer stream failed partway. This partial answer may be "
    "incomplete — please ask again."
)
GENERIC_STREAM_ERROR_HI = (
    "लाइव उत्तर स्ट्रीम बीच में विफल हो गया। यह आंशिक उत्तर अपूर्ण हो सकता है — "
    "कृपया दोबारा पूछें।"
)


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _source_dict(doc) -> dict:
    return {
        "source": doc.metadata.get("source", ""),
        "content": doc.page_content,
        "jurisdiction": doc.metadata.get("jurisdiction"),
        "state": doc.metadata.get("state"),
        "data_status": doc.metadata.get("data_status"),
        "last_verified": doc.metadata.get("last_verified"),
        "source_url": doc.metadata.get("source_url"),
    }


async def stream_answer(
    question: str,
    language: str = "en",
    profile: ProfileData | None = None,
) -> AsyncIterator[str]:
    lang = _normalize_language(language)
    profile_context = _build_profile_context(profile, lang)
    tokens_sent = False
    try:
        # Fail fast (no key -> ValueError) before touching the DB.
        get_llm()
        normalized = await anyio.to_thread.run_sync(
            normalize_question, question
        )
        docs = await anyio.to_thread.run_sync(
            lambda: get_retriever().invoke(normalized)
        )
        yield _sse("sources", [_source_dict(doc) for doc in docs])
        chain = build_answer_chain(lang)
        async for chunk in chain.astream(
            {
                "context": docs,
                "input": question,
                "profile_context": profile_context,
            }
        ):
            text = chunk if isinstance(chunk, str) else str(chunk)
            if not text:
                continue
            tokens_sent = True
            yield _sse("token", {"text": text})
        yield _sse("done", {"mode": "live", "notice": None, "language": lang})
    except Exception as exc:
        if tokens_sent:
            logger.error(
                "Live stream failed mid-answer (%s).", type(exc).__name__
            )
            yield _sse(
                "error",
                {
                    "message": (
                        GENERIC_STREAM_ERROR_HI
                        if lang == "hi"
                        else GENERIC_STREAM_ERROR
                    )
                },
            )
            return
        logger.error(
            "Live stream failed before answer (%s); streaming demo answer.",
            type(exc).__name__,
        )
        demo = demo_answer(question, lang)
        yield _sse("sources", demo["sources"])
        for word in demo["answer"].split(" "):
            yield _sse("token", {"text": word + " "})
        yield _sse(
            "done",
            {"mode": "demo", "notice": demo["notice"], "language": lang},
        )
```

- [ ] **Step 5: Add the endpoint in `app/main.py`**

Add imports (top, with the other app imports):

```python
from fastapi.responses import StreamingResponse

from app.stream import stream_answer
```

Add endpoint after `/query`:

```python
@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    """Streamed variant of /query over Server-Sent Events.

    Same request schema and bounds; events: sources -> token* -> done|error.
    Demo fallback semantics are identical to /query: labelled, HTTP 200,
    never a traceback.
    """
    return StreamingResponse(
        stream_answer(req.question, req.language, req.profile),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 6: Run tests + compile**

Run: `python -m pytest tests/ -v && python -m py_compile app/*.py`
Expected: all PASS.

- [ ] **Step 7: Commit** — `git add app/stream.py app/main.py tests/test_stream.py requirements-dev.txt && git commit -m "feat(api): SSE /query/stream with sources/token/done/error protocol and demo fallback"`

---

### Task 4: Next.js scaffold + design tokens (`web/`)

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/next.config.ts`, `web/postcss.config.mjs`, `web/next-env.d.ts`, `web/.gitignore`, `web/app/globals.css`, `web/app/layout.tsx` (minimal placeholder page in this task)

**Interfaces:**
- Produces: runnable Next app (`npm run build`, `npm run dev`), CSS tokens (`--color-paper`, `--color-ink`, `--color-verified`, `--color-seed`, `--color-seed-bright`, `--color-signal`, `--color-live`, `--color-linkblue`, `--font-sans`, `--font-mono`), font CSS vars (`--font-archivo`, `--font-martian`, `--font-devanagari`), keyframes `caret-blink` and `letter-in`.

- [ ] **Step 1: Verify Node toolchain**

Run: `node -v && npm -v`
Expected: Node >= 20. If missing, STOP and report — do not attempt to install Node.

- [ ] **Step 2: Create config files**

`web/package.json`:

```json
{
  "name": "schemegpt-web",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "^15.3.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.1.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "tailwindcss": "^4.1.0",
    "typescript": "^5.7.0"
  }
}
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`web/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

`web/postcss.config.mjs`:

```javascript
const config = {
  plugins: ["@tailwindcss/postcss"],
};

export default config;
```

`web/.gitignore`:

```
node_modules/
.next/
out/
*.tsbuildinfo
next-env.d.ts
```

- [ ] **Step 3: Fonts + tokens** — `web/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Archivo, Martian_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
});
const martian = Martian_Mono({
  subsets: ["latin"],
  variable: "--font-martian",
});
const devanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  variable: "--font-devanagari",
});

export const metadata: Metadata = {
  title: "SchemeGPT — Indian schemes, answered honestly",
  description:
    "Ask questions about Indian government schemes in any language. Answers quote the exact policy statements they rely on.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${archivo.variable} ${martian.variable} ${devanagari.variable} bg-paper text-ink font-sans antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
```

`web/app/globals.css`:

```css
@import "tailwindcss";

@theme {
  /* Engineered-editorial palette (from haoqi.design, adapted) */
  --color-paper: #fbfaf4;
  --color-paper-dim: #efede7;
  --color-ink: #000000;
  --color-verified: #00784a;
  --color-seed: #8a6a00;
  --color-seed-bright: #ebc669;
  --color-signal: #c0434c;
  --color-live: #c0fe04;
  --color-linkblue: #0077bc;

  --font-sans: var(--font-archivo), var(--font-devanagari), sans-serif;
  --font-mono: var(--font-martian), var(--font-devanagari), monospace;
}

/* Zero border-radius is a design rule: enforce globally. */
*,
*::before,
*::after {
  border-radius: 0 !important;
}

::selection {
  background: #000;
  color: #c0fe04;
}

@keyframes caret-blink {
  0%,
  49% {
    opacity: 1;
  }
  50%,
  100% {
    opacity: 0;
  }
}

@keyframes letter-in {
  from {
    opacity: 0;
    transform: translateY(0.35em);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.letter-stagger span {
  display: inline-block;
  opacity: 0;
  animation: letter-in 0.45s cubic-bezier(0.65, 0, 0.35, 1) forwards;
}

.caret::after {
  content: "▮";
  margin-left: 0.15em;
  animation: caret-blink 1s step-end infinite;
}

@media (prefers-reduced-motion: reduce) {
  .letter-stagger span {
    animation: none;
    opacity: 1;
    transform: none;
  }
  .caret::after {
    animation: none;
  }
}
```

Minimal `web/app/page.tsx` for this task (replaced in Task 6):

```tsx
export default function Home() {
  return (
    <main className="min-h-screen p-6">
      <h1 className="font-sans text-6xl font-bold uppercase leading-none">
        SchemeGPT
      </h1>
    </main>
  );
}
```

`web/next-env.d.ts`:

```typescript
/// <reference types="next" />
/// <reference types="next/image-types/global" />
```

- [ ] **Step 4: Install and build**

Run: `cd web && npm install && npm run build`
Expected: install succeeds (fonts download at build), build succeeds with no type errors.

- [ ] **Step 5: Commit** — `git add web/ && git commit -m "feat(web): Next.js scaffold with engineered-editorial design tokens"`

---

### Task 5: App shell — terminal chrome nav + footer + language context

**Files:**
- Create: `web/components/LanguageProvider.tsx`, `web/components/Chrome.tsx`
- Modify: `web/app/layout.tsx` (wrap children with provider + chrome)

**Interfaces:**
- Produces: `useLanguage(): { lang: "en" | "hi"; setLang(l): void }` React context hook; `<Chrome />` renders header nav (`SCHEMEGPT` wordmark, `LANG[EN]`/`LANG[HI]` toggle) and the inverted-black footer. Footer copy: `SCHEMEGPT (C) 2026 · 28.6139 N X 77.2090 E · NOT OFFICIAL ADVICE — VERIFY ON OFFICIAL SOURCES`.

- [ ] **Step 1: Implement `web/components/LanguageProvider.tsx`**

```tsx
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

type Lang = "en" | "hi";

const LanguageContext = createContext<{
  lang: Lang;
  setLang: (l: Lang) => void;
}>({ lang: "en", setLang: () => {} });

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    const stored = window.localStorage.getItem("schemegpt-lang");
    if (stored === "en" || stored === "hi") setLangState(stored);
  }, []);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    window.localStorage.setItem("schemegpt-lang", l);
  }, []);

  return (
    <LanguageContext.Provider value={{ lang, setLang }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
```

- [ ] **Step 2: Implement `web/components/Chrome.tsx`**

```tsx
"use client";

import { useLanguage } from "./LanguageProvider";

function LangSwitch() {
  const { lang, setLang } = useLanguage();
  return (
    <button
      type="button"
      onClick={() => setLang(lang === "en" ? "hi" : "en")}
      className="font-mono text-xs uppercase tracking-wide focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
      aria-label="Toggle language"
    >
      LANG[{lang === "en" ? "EN" : "HI"}] ↻
    </button>
  );
}

export function HeaderChrome() {
  return (
    <header className="flex items-center justify-between border-b border-ink px-4 py-4 lg:px-14">
      <a href="/" className="font-sans text-lg font-extrabold uppercase tracking-tight">
        SchemeGPT
      </a>
      <div className="flex items-center gap-6">
        <span className="hidden font-mono text-xs uppercase sm:inline">
          MODE[—]
        </span>
        <LangSwitch />
      </div>
    </header>
  );
}

export function FooterChrome() {
  return (
    <footer className="bg-ink px-4 py-6 text-paper lg:px-14">
      <p className="font-mono text-[11px] uppercase leading-relaxed">
        SchemeGPT (C) 2026 · 28.6139 N X 77.2090 E · Not official advice —
        verify on official sources
      </p>
    </footer>
  );
}
```

- [ ] **Step 3: Wire into `web/app/layout.tsx`** — body becomes:

```tsx
<body className={`${archivo.variable} ${martian.variable} ${devanagari.variable} bg-paper text-ink font-sans antialiased`}>
  <LanguageProvider>
    <HeaderChrome />
    <main className="min-h-[70vh]">{children}</main>
    <FooterChrome />
  </LanguageProvider>
</body>
```

with `import { FooterChrome, HeaderChrome } from "../components/Chrome";` and `import { LanguageProvider } from "../components/LanguageProvider";` added at top.

- [ ] **Step 4: Build + typecheck**

Run: `cd web && npm run build && npm run typecheck`
Expected: success.

- [ ] **Step 5: Commit** — `git add web/ && git commit -m "feat(web): terminal chrome header/footer and language context"`

---

### Task 6: Chat page — hero, SSE client, sources, mode banners

**Files:**
- Create: `web/app/api/chat/stream/route.ts`, `web/components/StaggeredText.tsx`, `web/components/Chat.tsx`, `web/components/SourceCard.tsx`, `web/components/CoveragePill.tsx`
- Modify: `web/app/page.tsx` (full replacement)

**Interfaces:**
- Consumes: SSE protocol from Task 3 (via the proxy route), `/coverage` JSON (`jurisdiction_count`, `verified_count` if present — read defensively), `useLanguage()`.
- Produces: the home page (`/`) with hero + chat.

- [ ] **Step 1: SSE proxy route** — `web/app/api/chat/stream/route.ts`:

```typescript
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/query/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await req.text(),
      cache: "no-store",
    });
  } catch {
    return new Response(
      JSON.stringify({ error: "The SchemeGPT API is unreachable." }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }
  if (!upstream.ok || !upstream.body) {
    return new Response(
      JSON.stringify({ error: "The SchemeGPT API rejected the request." }),
      { status: upstream.status ?? 502, headers: { "content-type": "application/json" } },
    );
  }
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
    },
  });
}
```

- [ ] **Step 2: `web/components/StaggeredText.tsx`** (per-letter reveal):

```tsx
export function StaggeredText({ text }: { text: string }) {
  const letters = Array.from(text);
  return (
    <span className="letter-stagger" aria-label={text} role="text">
      {letters.map((ch, i) => (
        <span key={i} aria-hidden="true" style={{ animationDelay: `${i * 28}ms` }}>
          {ch === " " ? "\u00A0" : ch}
        </span>
      ))}
    </span>
  );
}
```

- [ ] **Step 3: `web/components/SourceCard.tsx`** (ruled card + honesty stamps):

```tsx
export type Source = {
  source: string;
  content: string;
  jurisdiction?: string | null;
  state?: string | null;
  data_status?: string | null;
  last_verified?: string | null;
  source_url?: string | null;
};

function stampFor(dataStatus: string | null | undefined): {
  label: string;
  className: string;
} {
  if (dataStatus === "sample_verified")
    return { label: "Verified", className: "text-verified" };
  if (dataStatus === "directory_seed")
    return { label: "Directory seed", className: "text-seed" };
  return { label: "Source", className: "text-ink/60" };
}

export function SourceCard({ source }: { source: Source }) {
  const stamp = stampFor(source.data_status);
  const name = source.source.split("/").pop() ?? source.source;
  return (
    <li className="border-t border-ink/25 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[11px] uppercase">{name}</span>
        <span className={`font-mono text-[11px] uppercase ${stamp.className}`}>
          {stamp.label}
          {source.last_verified ? ` · ${source.last_verified}` : ""}
        </span>
      </div>
      {source.source_url ? (
        <a
          href={source.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-[11px] text-linkblue underline"
        >
          official source ↗
        </a>
      ) : null}
    </li>
  );
}
```

- [ ] **Step 4: `web/components/CoveragePill.tsx`** (server-safe):

```tsx
export function CoveragePill({
  jurisdictions,
  verified,
}: {
  jurisdictions: number | null;
  verified: number | null;
}) {
  if (jurisdictions == null) return null;
  return (
    <p className="font-mono text-xs uppercase text-ink/70">
      {jurisdictions} jurisdictions
      {verified != null ? ` · ${verified} verified sample schemes` : ""} ·
      state directories expanding
    </p>
  );
}
```

- [ ] **Step 5: `web/components/Chat.tsx`** (client, SSE parsing):

```tsx
"use client";

import { useRef, useState } from "react";
import { useLanguage } from "./LanguageProvider";
import { SourceCard, type Source } from "./SourceCard";

type Msg = {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  sources?: Source[];
  mode?: "live" | "demo";
  notice?: string | null;
  error?: string;
};

const PLACEHOLDER: Record<"en" | "hi", string> = {
  en: "Ask anything about Indian government schemes…",
  hi: "भारत सरकार की योजनाओं के बारे में कुछ भी पूछें…",
};

export function Chat() {
  const { lang } = useLanguage();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setBusy(true);
    setInput("");
    const controller = new AbortController();
    abortRef.current = controller;
    setMessages((m) => [
      ...m,
      { role: "user", text: question },
      { role: "assistant", text: "", streaming: true, sources: [] },
    ]);

    const patch = (fn: (a: Msg) => Msg) =>
      setMessages((m) => {
        const copy = [...m];
        const last = copy.length - 1;
        copy[last] = fn(copy[last]);
        return copy;
      });

    try {
      const resp = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question, language: lang }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        const detail = await resp
          .json()
          .catch(() => ({ error: "Request failed." }));
        patch((a) => ({
          ...a,
          streaming: false,
          error: detail.error ?? `Request failed (${resp.status}).`,
        }));
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split("\n\n");
        buf = blocks.pop() ?? "";
        for (const block of blocks) {
          let event = "";
          let data: Record<string, unknown> | unknown[] | null = null;
          for (const line of block.split("\n")) {
            if (line.startsWith("event: ")) event = line.slice(7);
            else if (line.startsWith("data: "))
              data = JSON.parse(line.slice(6));
          }
          if (event === "sources")
            patch((a) => ({ ...a, sources: data as Source[] }));
          else if (event === "token")
            patch((a) => ({ ...a, text: a.text + (data as { text: string }).text }));
          else if (event === "done")
            patch((a) => ({
              ...a,
              streaming: false,
              mode: (data as { mode: "live" | "demo" }).mode,
              notice: (data as { notice: string | null }).notice,
            }));
          else if (event === "error")
            patch((a) => ({
              ...a,
              streaming: false,
              error: (data as { message: string }).message,
            }));
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError")
        patch((a) => ({
          ...a,
          streaming: false,
          error: "Could not reach SchemeGPT. Check your connection and retry.",
        }));
      else patch((a) => ({ ...a, streaming: false }));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-16">
      <ul className="space-y-8">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <li key={i} className="border-l-4 border-ink pl-4">
              <p className="whitespace-pre-wrap font-sans text-lg">{m.text}</p>
            </li>
          ) : (
            <li key={i}>
              {m.mode === "demo" ? (
                <div className="bg-ink px-4 py-2 text-paper">
                  <p className="font-mono text-[11px] uppercase">
                    Mode[demo] — pre-made answer, not a live result
                  </p>
                </div>
              ) : null}
              {m.mode === "live" ? (
                <p className="font-mono text-[11px] uppercase text-verified">
                  Mode[live] · Groq RAG
                </p>
              ) : null}
              {m.notice && m.mode !== "demo" ? (
                <p className="font-mono text-[11px] text-ink/60">{m.notice}</p>
              ) : null}
              {m.notice && m.mode === "demo" ? (
                <p className="border-b border-ink/25 pb-2 font-mono text-[11px] text-ink/60">
                  {m.notice}
                </p>
              ) : null}
              <p
                className={`whitespace-pre-wrap py-3 font-sans text-lg leading-relaxed ${
                  m.streaming ? "caret" : ""
                }`}
              >
                {m.text}
              </p>
              {m.error ? (
                <p className="border border-signal px-3 py-2 font-mono text-[11px] uppercase text-signal">
                  {m.error}{" "}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => ask(messages[i - 1]?.text ?? "")}
                  >
                    retry ↻
                  </button>
                </p>
              ) : null}
              {m.sources && m.sources.length > 0 && !m.streaming ? (
                <div className="mt-2 border border-ink/25 px-4 py-2">
                  <p className="pt-1 font-mono text-[11px] uppercase">
                    Sources[{m.sources.length}]
                  </p>
                  <ul>
                    {m.sources.map((s, j) => (
                      <SourceCard key={j} source={s} />
                    ))}
                  </ul>
                </div>
              ) : null}
            </li>
          ),
        )}
      </ul>

      <form
        className="mt-10 flex items-stretch border border-ink"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <span aria-hidden="true" className="grid place-items-center bg-ink px-3 font-mono text-paper">
          &gt;
        </span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={PLACEHOLDER[lang]}
          className="w-full bg-paper px-4 py-4 font-sans text-lg outline-none placeholder:text-ink/40"
          maxLength={2000}
          minLength={2}
          required
          aria-label="Question"
        />
        {busy ? (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="bg-ink px-5 font-mono text-xs uppercase text-paper"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            className="bg-ink px-5 font-mono text-xs uppercase text-paper hover:bg-verified focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            Ask
          </button>
        )}
      </form>
      <p className="mt-3 font-mono text-[11px] uppercase text-ink/50">
        Not official advice — verify on official sources before applying
      </p>
    </div>
  );
}
```

- [ ] **Step 6: `web/app/page.tsx`** (server component: hero + coverage fetch + Chat):

```tsx
import { Chat } from "../components/Chat";
import { CoveragePill } from "../components/CoveragePill";
import { StaggeredText } from "../components/StaggeredText";

export const dynamic = "force-dynamic";

async function getCoverage(): Promise<{
  jurisdictions: number | null;
  verified: number | null;
}> {
  const api = process.env.API_URL ?? "http://localhost:8000";
  try {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(`${api}/coverage`, {
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(t);
    const data = await res.json();
    return {
      jurisdictions: data.jurisdiction_count ?? null,
      verified:
        data.catalog_totals?.sample_verified ??
        data.sample_verified_count ??
        null,
    };
  } catch {
    return { jurisdictions: null, verified: null };
  }
}

export default async function Home() {
  const { jurisdictions, verified } = await getCoverage();
  return (
    <div>
      <section className="px-4 pb-14 pt-16 lg:px-14 lg:pt-24">
        <p className="mb-6 font-mono text-xs uppercase">
          Design &amp; honesty — for every citizen
        </p>
        <h1 className="max-w-5xl font-sans text-[13vw] font-bold uppercase leading-[1.0] tracking-tight sm:text-7xl lg:text-8xl">
          <StaggeredText text="Ask your government." />
        </h1>
        <p className="mt-8 max-w-2xl font-sans text-xl leading-relaxed lg:text-2xl">
          Plain-language answers about Indian government schemes — in broken
          English, Hindi, or anything in between — quoting the exact policy
          statements they rely on.
        </p>
        <div className="mt-6">
          <CoveragePill jurisdictions={jurisdictions} verified={verified} />
        </div>
      </section>
      <Chat />
    </div>
  );
}
```

- [ ] **Step 7: Build + typecheck**

Run: `cd web && npm run build && npm run typecheck`
Expected: success, no type errors.

- [ ] **Step 8: Commit** — `git add web/ && git commit -m "feat(web): streaming chat page with hero, SSE client, sources, mode banners"`

---

### Task 7: Compose integration (`web` service, rename streamlit)

**Files:**
- Create: `web/Dockerfile`
- Modify: `docker-compose.yml`, `.dockerignore`, `README.md` (Quickstart only)

- [ ] **Step 1: `web/Dockerfile`** (multi-stage, standalone output):

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

(If `web/public/` does not exist, create it with a `.gitkeep`.)

- [ ] **Step 2: `docker-compose.yml`** — rename the existing `web` service to `streamlit` (unchanged config, same port `8501:8501`) and add the new `web` service after it:

```yaml
  streamlit:
    build:
      context: .
      dockerfile: Dockerfile.streamlit
    restart: unless-stopped
    environment:
      STREAMLIT_API_URL: http://api:8000
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "8501:8501"

  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      API_URL: http://api:8000
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "3000:3000"
```

- [ ] **Step 3: `.dockerignore`** — append:

```
web/node_modules
web/.next
```

- [ ] **Step 4: README Quickstart** — after the line about `http://localhost:8501`, add the new UI: `http://localhost:3000` (new engineered-editorial UI; Streamlit remains at 8501 during migration).

- [ ] **Step 5: Verify compose resolves**

Run: `docker compose config --quiet`
Expected: no output, exit 0. (If Docker is unavailable on the machine, run `python -c "import yaml,sys; yaml.safe_load(open('docker-compose.yml'))"` instead and report Docker unavailability.)

- [ ] **Step 6: Commit** — `git add web/Dockerfile docker-compose.yml .dockerignore README.md && git commit -m "feat(deploy): add web compose service (Next.js :3000), rename streamlit service"`

---

### Task 8: Full verification pass

- [ ] **Step 1: Backend** — `python -m pytest tests/ -v` → all pass.
- [ ] **Step 2: Compile + data** — `python -m py_compile app/*.py streamlit_app.py scripts/validate_data.py eval/run_eval.py && python scripts/validate_data.py` → pass.
- [ ] **Step 3: Compose** — `docker compose config --quiet` → pass.
- [ ] **Step 4: Frontend** — `cd web && npm run build && npm run typecheck` → pass.
- [ ] **Step 5: Report** — summarize results; visual QA in a browser is performed by the main agent after this plan completes (subagents must not use browser tools).

---

## Self-Review (completed)

- **Spec coverage:** Slice 1 frontend (shell, design system, chat, streaming, en/hi, coverage pill, demo/labelling, error handling) — Tasks 4–6; SSE endpoint + demo fallback + mid-stream error — Task 3; normalization + quotable answers — Task 2; compose/`API_URL` — Task 7. Slice 2–5 items are intentionally NOT in this plan (per-slice planning).
- **Placeholders:** none; every step has complete code or exact commands.
- **Type consistency:** SSE event names (`sources`/`token`/`done`/`error`) and payload fields match between `app/stream.py`, the proxy route, and `Chat.tsx`. `Source` type fields match `_source_dict`/`_demo_source` output. `get_retriever`/`build_answer_chain` names consistent across Tasks 1–3.
