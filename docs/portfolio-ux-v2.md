# SchemeGPT — interaction and visual brief v2

**Status:** proposed brief, not implementation and not a verification verdict.
**Base commit:** `b49c4a490e6850a8492ece7c22ac93169b80f2d9` (`fix/schemegpt-host-gate`) on branch
`feature/schemegpt-ux-brief`, worktree `C:/Users/oliad/Desktop/SchemeGPT.wt/ux-brief`.
**Scope:** the Next.js surface in `web/` only. No application logic, no model, no deploy, no security decision.
**Downstream:** feeds builder card `t_ff557fc5` (accessible UX integration on the reviewed security baseline).
Line numbers are against `b49c4a4`; that card starts from a different SHA, so **re-locate by symbol and route,
not by line** — every change below is stated as a contract and a browser assertion, not as a patch.

---

## 0. How to read this document

| Tag | Meaning |
|---|---|
| `[OBS]` | Read directly in the committed source at `b49c4a4` by me, with file:line. |
| `[SHOT]` | A committed screenshot in `docs/screenshots/` on this branch; dimensions measured by me, content not re-rendered by me. |
| `[E2E]` | An assertion that exists in the committed harness `web/e2e/journey.mjs`, reported passing by the builder on `t_4c2dcb70` (24/24). I did **not** re-run it. |
| `[PROP]` | A proposed v2 change. |
| `[CHECK]` | A browser assertion the integration card must add and pass. |

**What this run did and did not do.**

- Read: every file under `web/app`, `web/components`, `web/lib`, plus `web/e2e/*`, `web/package.json`.
- Computed: WCAG 2.x contrast ratios from the tokens in `web/app/globals.css:4-13` (sRGB relative luminance,
  foreground alpha composited over `--color-paper #fbfaf4`). These are arithmetic, reproducible with the
  one-liner in §12.
- Queried `ui-ux-pro-max` `scripts/search.py` three times (two `--domain ux`, one `--stack nextjs`); only the
  results that actually fit are cited in §5–§6, each with its issue name. Results are recommendations, never
  product truth.
- **No browser was driven in this run.** No page was rendered, no axe run, no device emulation. Mobile and
  accessibility findings below are either source facts `[OBS]`, committed screenshots `[SHOT]`, the builder's
  committed harness `[E2E]`, or explicitly flagged as risks needing `[CHECK]`.
- Nothing was probed against the deployed site, and nothing here says anything about what production serves.
- **Boundary:** the security review `t_8c88d2bf` findings F1–F5 are out of scope. Two of them have *rendering*
  consequences (F2 `source_url` target, F3 malformed `/coverage` payload) and §6.4 specifies the reader-facing
  behaviour only. No allowlist, header, cache or rate-limit decision is taken or implied here.

---

## 1. Audience and journeys

| | **P1 — first-time scheme seeker** | **P2 — judging reader (recruiter / engineer)** |
|---|---|---|
| Device | phone, 375 px, metered data, possibly Hindi | laptop, 1440 px, 5 minutes, diffing claims against evidence |
| Wants | "does this scheme apply to me, what do I get, where do I apply" | "is this real, is it measured, can I reproduce it, what is the catch" |
| Trusts | plain language, a named official portal, a date | a numbered result, the command that produced it, an explicit limitation |
| Fails today at | the answer's citation tokens and the unlabelled provenance of imported sources | the evidence trail's last hop (branch-pinned links, no per-metric anchor) |

### Journey A — seeker, mobile, happy path

| # | Step | Observed at `b49c4a4` | Friction | Proposed v2 |
|---|---|---|---|---|
| A1 | Land on `/` | H1 `Ask your government.`, one-line explainer, coverage pill, sample queries `[OBS page.tsx:55-74, Chat.tsx:435-459]` | The pill states 36 jurisdictions / 6 verified but nowhere says the corpus is a *directory* with a small verified core; a seeker reads "36" as "36 schemes covered" | Pill text keeps counts and adds a one-tap link to `/coverage` labelled **"what's actually indexed →"** |
| A2 | Choose a question | Four sample-query buttons, 1 column ≤sm, 2 columns ≥sm `[OBS Chat.tsx:440]` | Good: removes blank-page paralysis | Keep; add `aria-describedby` pointing at the coverage note so the scope is read before asking |
| A3 | Ask | Input `aria-label="Question"`, max 2000 chars `[OBS Chat.tsx:474-484]` | On submit the input becomes `disabled` while the focused element is lost `[OBS Chat.tsx:481]` | Focus moves to **Stop**; input becomes `readOnly`, not `disabled` (`[CHECK K3]`) |
| A4 | Wait | Streaming pill "Searching policy corpus & generating answer..." with `animate-pulse` dot `[OBS Chat.tsx:246-253]` | Nothing is announced to a screen reader; no expectation of free-tier wake-up until *after* the failure | One `role="status"` message: "Searching the corpus… up to 30 s on a cold free-tier instance" (`[CHECK A1]`) |
| A5 | Read the answer | Single `<p>` with `whitespace-pre-wrap` `[OBS Chat.tsx:294-302]` | Model output arrives with literal `**bold**` and inline `[schemes/pm-kisan.md, sample_verified]` tokens (the assessment observed this on the live payload; the renderer is unchanged here) | Minimal renderer: paragraphs, bold, and citation tokens turned into chips bound to the sources list (`§6.5`, P1) |
| A6 | Check the citations | Quote panel "Verified source quotes [n]" with per-row ✓/✗ `[OBS Chat.tsx:334-382]` | The panel heading can say **Verified** over rows that individually render **✗ Unverified** `[OBS Chat.tsx:338 vs 361-365]` | Heading becomes a count: "Policy quotes [3] · 1 verified" (`[CHECK R3]`) |
| A7 | Check the sources | `SourceCard` labels `sample_verified`, `directory_seed`, `myscheme_import`, `unknown`, plus raw unrecognised `[OBS SourceCard.tsx:21-72]` | Honest, but the honesty text (`ink/45`, 10 px) is the least readable text on the page — **3.31:1** (`§5.6`) | Raise the uncertainty labels to `ink/60` (5.67:1) and keep the same words (`[CHECK R1]`) |
| A8 | Next action | "official source ↗" only when `source_url` exists; otherwise "no per-document source URL stored — portal record, not a citation" `[OBS SourceCard.tsx:99-115]` | For 3 of 4 realistic sources there is no link at all, and no fallback path to the scheme's portal | Add the jurisdiction portal link from `/coverage` data as a clearly-labelled *directory* fallback, never as a citation (`§6.3`) |

### Journey B — judging reader, desktop

| # | Step | Observed | Friction | Proposed v2 |
|---|---|---|---|---|
| B1 | Land | Header nav `Evidence`, `Coverage` — one click each `[OBS Chrome.tsx:29-44]`, `[E2E journey.mjs:210-211]` | The two most valuable pages are visually the smallest text on the page (12 px, `ink` underline) | Promote to 13 px mono with a 24 px minimum hit area and `aria-current` (`[CHECK A6, T2]`) |
| B2 | Open `/evidence` | Four metric cards, both MRR@4 runtimes labelled, "what this page is not", reproduce block `[OBS evidence/page.tsx:19-106]`, `[SHOT evidence-route.png 1440x900]` | Cards are not individually addressable — a recruiter cannot deep-link "the retrieval gate card" | Add `id={metric.id}` anchors: `/evidence#retrieval` etc. (P1) |
| B3 | Follow a metric's evidence link | `EVIDENCE.*` point at `blob/field-ops-and-deployment-kit/...` `[OBS measured.ts:64-75]` | The branch ref is deletable; the portfolio's proof chain depends on an unmerged branch name (`G1`) | Pin to a commit SHA, or to `main` once the branch decision (D1) is made — owner of D1, not this brief |
| B4 | Open `/coverage` | Three labelled states: unconfigured, unavailable (`role="alert"`), report `[OBS coverage/page.tsx:102-241]`, `[SHOT coverage-route.png]` | Status vocabulary forks: the breakdown and per-jurisdiction rows print raw keys (`myscheme_import`, `unknown`) while the chat translates them `[OBS coverage/page.tsx:201-203, 232-235]` | One shared `labelFor(data_status)` used by both surfaces (`[CHECK R2]`) |
| B5 | Try to reproduce | `/evidence` prints four commands `[OBS evidence/page.tsx:48-53]` | No copy control; commands wrap in a `<pre>` at 375 px | Copy-to-clipboard on the block (P1); keep `overflow-x-auto` (already present) |

---

## 2. Route and component inventory (observed)

| Route | File | Render mode | States rendered |
|---|---|---|---|
| `/` | `web/app/page.tsx` | `force-dynamic` (`:5`) | coverage pill (3), offline notice, chat |
| `/evidence` | `web/app/evidence/page.tsx` | static | one state, API-independent (`:4-12`) |
| `/coverage` | `web/app/coverage/page.tsx` | `force-dynamic` (`:3`) | `unconfigured`, `unavailable`, `report` |
| `/coverage` (pending) | `web/app/coverage/loading.tsx` | route-level loading | `role="status" aria-busy="true"` |
| `/api/chat/stream` | `web/app/api/chat/stream/route.ts` | `force-dynamic` | 501 offline, 502 unreachable, upstream passthrough |
| `/api/chat/feedback` | `web/app/api/chat/feedback/route.ts` | — | best-effort, no UI state |
| chrome | `web/components/Chrome.tsx` | client | lang toggle, nav, footer |

Components: `Chat.tsx` (510 lines, owns all conversation state), `SourceCard.tsx` (the status contract),
`MetricsPanel.tsx` (shared by `/` offline state and `/evidence`), `CoveragePill.tsx`, `OfflinePanel.tsx`,
`StaggeredText.tsx` (H1), `LanguageProvider.tsx` (client context + `localStorage`).

**Dead contract found:** `initialApiReachable` is passed by `page.tsx:77`, destructured by `Chat.tsx:77`, and
never read. The chat therefore never reflects the server-detected standby state. Either wire it to the first
answer's placeholder or delete the prop (P1, `[OBS]` by `grep -rn initialApiReachable web/`).

---

## 3. Annotated screens

### 3.1 `/` — desktop 1440 `[SHOT hero.png 1440x900]`

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SchemeGPT          Evidence   Coverage          MODE[—]   LANG[EN] ↻          │ [1][2]
├──────────────────────────────────────────────────────────────────────────────┤
│ DESIGN & HONESTY — FOR EVERY CITIZEN        ● 36 jurisdictions · 6 verified … │ [3][4]
│                                                                              │
│ ASK YOUR GOVERNMENT.                        ← 11.84vw → 7xl → 8xl            │ [5]
│                                                                              │
│ Plain-language answers about Indian government schemes … quoting the exact    │
│ policy statements they rely on.                                              │
│                                                                              │
│ ┌ SAMPLE QUERIES (CLICK TO RUN) ───────────────────────────────────────────┐ │
│ │ [PM-KISAN]                       [Ayushman Bharat]                       │ │ [6]
│ │ How much income support…         Who is covered…                         │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ >  Ask anything about Indian government schemes…              [ ASK → ]  │ │ [7]
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ Not official advice — verify on official sources before applying             │ [8]
├──────────────────────────────────────────────────────────────────────────────┤
│ SchemeGPT (C) 2026 · 28.6139 N X 77.2090 E · Not official advice — verify …   │ [9]
└──────────────────────────────────────────────────────────────────────────────┘
```

1. `MODE[—]` is a hard-coded empty placeholder, hidden below `sm` `[OBS Chrome.tsx:45-47]`. It reads as an
   unfinished control on every desktop visit. `[PROP]` remove it, or drive it from `/ops/status` (P1; the
   status endpoint is release-ops' surface, not this brief's).
2. No skip link, no `aria-current`, and the logo `<a href="/">` has no accessible-name problem but every nav
   item is a full page load `[OBS Chrome.tsx:22-43]`. `[PROP]` skip link → `#main`; `aria-current="page"`.
3. The coverage pill is honest and specific `[OBS CoveragePill.tsx:28-37]`. `[PROP]` keep the numbers, add the
   one-tap "what's actually indexed →" affordance.
4. **Home TTFB risk:** `page.tsx:38` awaits `getCoverage()` before rendering anything, with a 2 s abort and
   `force-dynamic` `[OBS page.tsx:5, 12-34]`. On a suspended free-tier instance the hero waits up to 2 s.
   `ui-ux-pro-max` `nextjs · Rendering · "Use streaming for better UX"` (Applies To nextjs 16.2, severity
   Medium) is the fitting remedy: `[PROP]` move the pill into a `<Suspense>` boundary with a static skeleton pill
   so the shell streams immediately (`[CHECK P1]`).
5. H1 is animated per letter with a staggered reveal `[OBS globals.css:47-67]`; reduced motion is handled for
   exactly this element `[OBS globals.css:75-84]`. Good — keep. `[PROP]` drop the non-standard `role="text"`
   from `StaggeredText.tsx:7` (G13); `aria-label` on a plain `<span>` is enough (`[CHECK A5]`).
6. Sample-query cards: `p-3`, full-width, 1-column at 375 `[OBS Chat.tsx:440-457]` — already ≥44 px tall and
   well spaced. `[PROP]` none.
7. Composer: 2 px border with a 3 px offset shadow, `focus-within:ring-2` `[OBS Chat.tsx:461-467]`. The Ask
   button is only 12 px mono `[OBS Chat.tsx:497-500]`; at 375 it is the primary action and must clear 44 px
   (`[CHECK T3]`).
8. The disclaimer duplicates the footer `[OBS Chat.tsx:504-506]` — keep both; it is cheap honesty at the point
   of action.
9. Footer states "Not official advice — verify on official sources" `[OBS Chrome.tsx:56-61]`. `[PROP]` add the
   deployed build SHA here **only when release-ops lands it** (G18); do not invent it in the UI.

### 3.2 `/` — 375 px `[SHOT narrow-home.png 375x812]`, `[E2E]` overflow 0 px at 375×812

```
┌───────────────────────────┐
│ SchemeGPT  Evidence       │  header wraps, wordmark + nav on row 1,
│ Coverage   LANG[EN] ↻     │  url + language on row 2  [1]
├───────────────────────────┤
│ ● 36 jurisdictions · …    │  pill wraps under the eyebrow [2]
│ ASK YOUR GOVERNMENT.      │  11.84vw ≈ 44 px at 375 [3]
│ Plain-language answers …  │
│ ┌───────────────────────┐ │
│ │ [PM-KISAN]            │ │  sample cards go 1-column [4]
│ └───────────────────────┘ │
│ ┌───────────────────────┐ │
│ │ > Ask anything …      │ │  composer 2px border [5]
│ │              [ ASK → ]│ │
│ └───────────────────────┘ │
└───────────────────────────┘
```

1. Header is `flex-wrap` with a 2-row wrap under ~360 px content width `[OBS Chrome.tsx:21]`. `[E2E]` asserts
   header visible and `>300 px` wide. `[PROP]` verify down to **320 px** (`[CHECK T1]`) — an iPhone SE in Safari
   with a 320 px viewport is a common QA width and nobody has measured it.
2. Pill is `inline-flex` and does not truncate; at 320 px it may wrap to 3 lines. `[PROP]` allow it to wrap
   (fine) but keep the label before the numbers so the claim is read first.
3. `text-[11.84vw]` is 37.9 px at 320 — no overflow risk, but the H1 is the heaviest paint on a phone.
   `[PROP]` none (brand strength).
4. Sample cards are stacked at 375 `[OBS Chat.tsx:440]`. `[PROP]` keep.
5. Composer: no `env(safe-area-inset-bottom)`; iOS Safari's toolbars can overlap the disclaimer. `[PROP]` add
   `pb-[max(1rem,env(safe-area-inset-bottom))]` to the composer wrapper (P1).

### 3.3 Streamed answer state

```
[ user ]  How much income support does PM-KISAN provide?
│
● SEARCHING POLICY CORPUS & GENERATING ANSWER...     ← animate-pulse, unrouted to AT  [1]
LIVE MODE · GROQ RAG                                  ← hard-coded provider badge      [2]
┌ EXECUTION PIPELINE ──────────────────────────────┐  ← appears only if API emits step [3]
│ ⇄ retrieve — 12 chunks                            │
└──────────────────────────────────────────────────┘
PM-KISAN gives each eligible farmer family **₹6,000 per year** …   ← literal markdown   [4]
┌ VERIFIED SOURCE QUOTES [1] ──────────────────────┐
│ ✓ VERIFIED QUOTE | SCHEME: PM KISAN (pm-kisan.md) │  [5]
│ “PM-KISAN provides income support of Rs.6000…”    │
└──────────────────────────────────────────────────┘
┌ RETRIEVED SOURCES [4] ───────────────────────────┐
│ pm-kisan.md                       VERIFIED · 2026-09-20 │
│ afag.md                           IMPORTED · UNVERIFIED │  ← was "Source" pre-b49c4a4
│ namo-shetkari…                    IMPORTED · UNVERIFIED │
│ pm-kusum.md                       IMPORTED · UNVERIFIED │
└──────────────────────────────────────────────────┘
Was this helpful?  ▲ helpful   ▼ not helpful          ← 11px, ~14px tall  [6]
```

1. `[PROP]` one polite live region owns the lifecycle; see §5.2 (`[CHECK A1-A3]`).
2. "Live mode · Groq RAG" hard-codes a provider `[OBS Chat.tsx:264-271]` (G14). `[PROP]` "Live answer · grounded"
   with the provider name removed; provider identity is not a reader-facing claim.
3. The "Execution Pipeline" block `[OBS Chat.tsx:279-292]` is a debugging surface with tool names. It is good
   evidence for P2 and noise for P1. `[PROP]` collapse it behind `<details><summary>How this answer was built</summary>`
   and keep it expanded on `/evidence`, not on `/`.
4. `[PROP]` §6.5.
5. `[PROP]` §6.1–6.3. `Quote.status` is already on the wire and typed `[OBS Chat.tsx:11]` but never rendered —
   the cheapest honest fix in the file.
6. `[PROP]` `min-h-11 inline-flex items-center` on both feedback buttons; the 4-gap spacing already satisfies
   the 8 px separation rule (`[CHECK T2]`).

### 3.4 `/evidence` — desktop `[SHOT evidence-route.png 1440x900]`

Observed: eyebrow, H1 "The numbers, and where they come from.", lead paragraph, 4-card `MetricsPanel`,
"How to reproduce" `<pre>`, "What this page is not" (3 bullets), footer links `[OBS evidence/page.tsx:19-106]`.
This page is the strongest thing in the product: it is static, API-independent, and each card links to the
document that records it.

`[PROP]` three bounded changes only:
1. Per-card anchor ids (`#retrieval`, `#temporal`, `#pii`, `#corpus`) so a résumé/README can deep-link one claim.
2. The "What this page is not" heading is `text-signal` on `bg-paper-dim` = **4.32:1**, below AA for 10 px bold
   (`§5.6`); raise to `ink` and keep the red rule.
3. The reproduce `<pre>` gets a copy button, and the four commands are each on one line at 375 (they already
   scroll horizontally — keep that, do not wrap commands).

### 3.5 `/coverage` — three states `[SHOT coverage-route.png 1440x900]`

Observed `[OBS coverage/page.tsx:102-241]`: `unconfigured` (2 px border, committed-corpus numbers, link to
evidence), `unavailable` (`role="alert"`, reason string from the fetch, Retry link), `report` (3 stat cards,
status breakdown, verbatim `coverage_note` blockquote, per-jurisdiction list 1→2 columns).

`[PROP]`
- Use the shared status vocabulary in both the breakdown and the rows (P0-4). Today the same payload renders
  "Verified" in the chat and `sample_verified` here.
- Give `/coverage` a per-jurisdiction row that links to the chat with a prefilled question, e.g.
  `/?q=<jurisdiction>` — **only** if the homepage can read a query param without a client-side fetch
  (P2; it needs a first-load contract, so not in the bounded slice).
- `unavailable`'s Retry link points at `/coverage` `[OBS coverage/page.tsx:144-150]` — a full reload of a
  force-dynamic page. That is acceptable for a 4 s timeout, but label it "Try again" and keep the reason visible
  after reload (the reason is recomputed, so it is).

### 3.6 Failure, offline, degraded — see §7 for the full matrix

---

## 4. Navigation model v2

Observed: wordmark, `Evidence`, `Coverage`, `MODE[—]`, `LANG[EN]` `[OBS Chrome.tsx:19-52]`. Evidence and
coverage are one click from `/` `[E2E journey.mjs:210-211]`. No skip link, no current-page signal, no
method/about route, no deep links into a specific metric or answer.

**Proposed information architecture (three top-level items, no more):**

```
SKIP LINK (first tab stop) ──► #main
SchemeGPT ─┬─ Ask        →  /
           ├─ Evidence   →  /evidence   (static; per-metric anchors)
           └─ Coverage   →  /coverage   (live; 3 labelled states)
                               LANG[EN|HI] ↻
```

Rules:
1. Exactly one `<nav aria-label="Site">` (already correct, `Chrome.tsx:29`) and `aria-current="page"` on the
   active item.
2. The wordmark is the "Ask" destination; add a visible `Ask` item only if user testing shows the wordmark is
   not understood as home. Do **not** add both.
3. No new route in v2. `/method`, `/about`, `/docs` remain 404s (G5/G6) and belong to a later slice; everything
   a recruiter needs is already on `/evidence` or `/coverage`.
4. Every page ends with the same three footer links: `← ask a question`, `measured evidence →`,
   `what's actually indexed →` (partially present; make it uniform).
5. Deep links to add in the same pass: `/evidence#retrieval` … `#corpus`; `/coverage#jurisdictions`
   (the report section); and per-answer `id="answer-2"` on each assistant turn so a transcript can be linked
   within a session (P1 — no persistence, anchors only).

---

## 5. Interaction and accessibility contract (normative)

### 5.1 Keyboard and focus

| ID | Contract | Current state |
|---|---|---|
| K1 | First Tab stop is a "Skip to content" link, visible on focus, targeting `#main` (`main` gets `id` + `tabIndex={-1}`) | **Missing**; `layout.tsx:36` has `<main>` with no id `[OBS]` |
| K2 | Tab order follows visual order: wordmark → Evidence → Coverage → LANG → sample cards → input → Ask/Stop | Holds by DOM order `[OBS]`; no `aria-current` |
| K3 | On submit, focus moves to the **Stop** control (the input is no longer focusable once `disabled`); Escape on Stop aborts | **Risk**: `disabled={busy}` on the focused input at `Chat.tsx:481` — browsers move focus to `document.body`, so a keyboard user is dropped to the top of the document for the whole stream `[OBS source, needs CHECK K3]` |
| K4 | On completion, failure or abort, focus returns to the question input | Not implemented `[OBS]` |
| K5 | Every interactive element shows a ≥2 px focus indicator; none relies on hover | Largely present via `focus-visible:outline focus-visible:outline-2` across `Chrome.tsx`, `Chat.tsx`, `SourceCard.tsx`, `MetricsPanel.tsx` `[OBS]`. Verify the indicator against `--color-ink` on `--color-paper` (20.08:1) — it passes |
| K6 | `prefers-reduced-motion` removes all non-essential animation (letter stagger, caret blink, `animate-pulse`, colour transitions) | Partial: `globals.css:75-84` covers only `.letter-stagger .letter` and `.caret::after`; `animate-pulse` at `Chat.tsx:248` and five `transition-colors` utilities are **not** covered `[OBS]` |

`ui-ux-pro-max` `ux · Accessibility · "Focusable Error Summary"` (severity High) recommends moving focus to an
error summary on failed submit. **Deliberate deviation:** the chat error is not a form-validation summary — the
transcript is an ongoing region and stealing focus mid-conversation is worse than announcing. Use `role="alert"`
+ return focus to the composer instead, and keep the Retry button in the DOM. Recorded here so nobody "fixes"
it back.

### 5.2 Live regions and announcements

**Observed:** exactly two ARIA live/status surfaces exist in `web/` — `role="status"` on the `/coverage`
loading skeleton `[OBS coverage/loading.tsx:5-6]` and `role="alert"` on the `/coverage` unavailable state
`[OBS coverage/page.tsx:131]`. The home page and the whole chat have none: `grep -rn "aria-live\|role=\"status\""
web` returns those two lines only. (This supersedes the assessment's blanket "none anywhere", which predated
this branch.)

**Contract — one polite region owns the answer lifecycle, and it is the only thing that speaks:**

| Moment | Announced text (one atomic message) |
|---|---|
| submit | "Searching the policy corpus. This can take up to 30 seconds on a cold instance." |
| done | "Answer ready. {n} sources, {v} of {n} verified quotes." |
| failure | "Answer failed. {message} A retry button is available." (via `role="alert"`) |
| abort | "Answer stopped." |

Implementation shape: one visually hidden `<div role="status" aria-live="polite" aria-atomic="true">` whose text
is replaced (never appended) at each transition; `aria-busy={streaming}` on the answer container; `role="alert"`
on the error box at `Chat.tsx:304-332`. Do **not** mark the streaming token text as a live region — 43 token
events would either flood or truncate speech. This is exactly `ui-ux-pro-max` `ux · Accessibility · "Contextual
Live Badge Updates"` (severity High): one atomic status message, not a competing live region per badge.
Coverage pill and mode badges stay `aria-hidden` for their decorative dot and are read as ordinary text.

### 5.3 Language and document metadata

- `web/app/layout.tsx:32` hardcodes `<html lang="en">`; `LanguageProvider.tsx:21-29` persists the choice but
  never touches `document.documentElement.lang` (G11) `[OBS]`.
- Contract: switching to HI sets `documentElement.lang="hi"` and, preferably, `lang="hi"` on the elements whose
  copy is Hindi (sample-query block, placeholder). Switching back restores `"en"`.
- The Hindi surface today is only the placeholder and the sample-query labels `[OBS Chat.tsx:32-74, 438]`; the
  headline, source labels and evidence page stay English. Do **not** claim the product is bilingual — the
  toggle changes the language *of the question*, and the UI says so now only by implication. `[PROP]` add a
  one-line note under the toggle: "Questions can be asked in any language; the interface is English + Hindi."
- Metadata: only `title` and `description` `[OBS layout.tsx:20-24]`; no `openGraph`, no favicon (G6). Out of the
  bounded slice; flagged.

### 5.4 Touch and target size

Rule set: WCAG 2.2 SC 2.5.8 (**24×24 CSS px) is the conformance floor for standalone controls; 44 px is the
comfort target for primary actions on mobile; 8 px minimum separation. Cited from `ui-ux-pro-max`
`ux · Touch · "Touch Target Size"` (Web: use the WCAG rule, not iOS 44pt as if it were web conformance) and
`ux · Touch · "Touch Spacing"` (≥8 px).

| Control | Current | Verdict |
|---|---|---|
| `LANG[EN] ↻` | `font-mono text-xs` with **no padding** `[OBS Chrome.tsx:8-16]` | **Fails 24×24** |
| Nav `Evidence` / `Coverage` | `text-xs` underlined text only `[OBS Chrome.tsx:30-43]` | **Fails 24×24** (height ≈ 15 px) |
| Feedback `▲ helpful` / `▼ not helpful` | `text-[11px]`, `gap-4` `[OBS Chat.tsx:407-424]` | **Fails 24×24**; spacing passes |
| `Retry question ↻` | `px-4 py-1.5` `[OBS Chat.tsx:321-327]` | ≈30 px — passes 24, below 44 |
| `Ask →` / `Stop` | stretch to the 2 px-border composer height `[OBS Chat.tsx:461-501]` | Passes 44 in practice; verify at 375 (`[CHECK T3]`) |
| Inline links inside prose (`← ask a question`, evidence links in sentences) | inline | Exempt (inline-in-text exception); leave |

Fix shape: one utility, e.g. `.tap { min-height: 2.75rem; min-width: 2.75rem; display: inline-flex;
align-items: center; }` applied to LANG, nav items and feedback buttons, with `-mx-2 px-2` so the visual rhythm
does not change. `[CHECK T2]` measures rects, not classes.

### 5.5 Motion

Observed: `letter-in` 0.45 s stagger, `caret-blink` 1 s step-end, `animate-pulse` on the streaming dot, five
`transition-colors` `[OBS globals.css:36-73, Chat.tsx:248, 323, 447, 489, 497]`. Only the first two are
reduced-motion aware.

`[PROP]` extend the media query to a global reset inside `@media (prefers-reduced-motion: reduce)`:
`*, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important;
transition-duration: .01ms !important; scroll-behavior: auto !important; }` — one rule, covers future
components, and leaves the caret as a static glyph (its content is CSS `::after`, so it still renders).
`[CHECK M1]` asserts `document.getAnimations()` has zero `running` entries under emulated reduced motion on
`/` and during a stream.

### 5.6 Contrast (measured, not estimated)

Foregrounds composited over `--color-paper #fbfaf4`; AA normal text needs **4.5:1**, large text **3:1**
(18.66 px bold / 24 px regular).

| Token / usage | Ratio | Verdict |
|---|---|---|
| `ink/45` — "no verification date on record", "no per-document source URL stored" `SourceCard.tsx:94, 111` | **3.31:1** | **FAIL** — and it is exactly the honesty text |
| `ink/50` — "Corpus provenance", filename, "Execution pipeline", "Not official advice", metrics eyebrow `Chat.tsx:281, 370, 390, 505; MetricsPanel.tsx:74` | **3.94:1** | **FAIL** |
| `ink/55` — per-jurisdiction metadata `coverage/page.tsx:232` | 4.73:1 | Pass (thin) |
| `ink/60` — notes, "what this page is not" body `SourceCard.tsx:87` | 5.67:1 | Pass |
| `ink/70` | 8.36:1 | Pass |
| `ink/75` | 10.21:1 | Pass |
| `ink/85` | 14.49:1 | Pass |
| `ink/90` | 16.83:1 | Pass |
| `verified #00784a` | 5.31:1 | Pass |
| `seed #8a6a00` | 4.85:1 | Pass |
| `signal #c0434c` on paper | 4.84:1 | Pass |
| `signal` on `paper-dim #efede7` — "Honest limit" + "What this page is not" headings `MetricsPanel.tsx:105-108; evidence/page.tsx:63-65` | **4.32:1** | **FAIL** at 10 px bold |
| `linkblue #0077bc` | 4.60:1 | Pass (borderline; do not lighten) |
| `live #c0fe04` | 1.15:1 | Decorative dot only (`aria-hidden`), never text |

`[PROP]` two token-level fixes, both mechanical: raise the uncertainty labels from `ink/45` → `ink/60`, and use
`ink` (or `signal` on `paper`) for the two red-on-dim headings. `ui-ux-pro-max` priority table puts Accessibility
at priority 1 with 4.5:1 as a must-have, consistent with the numbers above.

### 5.7 Responsive and zoom

`[E2E]` the committed harness asserts header visible, header width > 300 px and horizontal overflow 0 px at
375×812, plus a visible focus ring on the nav after Tab. That is the only measured responsive evidence that
exists, and it is builder-reported, not mine.

`[PROP]` add: **320 px** (iPhone SE / small Android) as a second width; 200 % text zoom (set
`document.documentElement.style.fontSize = "32px"` and assert no clipping of the H1 or the composer); and a
long-token probe (a 90-character source filename through the stub) to prove `SourceCard` wraps rather than
overflowing. `[CHECK T1, T3, T4]`.

---

## 6. Trust: source and uncertainty labelling

### 6.1 The label contract as it exists at `b49c4a4`

`SourceCard.tsx:21-51` maps four statuses, each with a distinct reader-facing label and an explanatory note:

| `data_status` | Label | Note shown |
|---|---|---|
| `sample_verified` | **Verified** | none |
| `directory_seed` | **Directory seed** | discovery/coverage entry, eligibility not individually verified |
| `myscheme_import` | **Imported · unverified** | automated MyScheme import, no human review |
| `unknown` (or absent) | **Provenance unlabelled** | nothing about provenance is known or implied |
| anything else | **Unrecognised status · `<raw>`** | shown raw rather than guessed |

Plus two absence statements: `no verification date on record` and `no per-document source URL stored — portal
record, not a citation` `[OBS SourceCard.tsx:91-115]`. This is the right design and should not be redesigned.

The mapping is actually guarded by `tests/test_web_portfolio_surface.py:84`
(`test_every_backend_status_has_a_distinct_reader_facing_label`) and `:105`
(`test_source_card_never_falls_back_to_a_neutral_label`), and the harness asserts each label in a real DOM
`[E2E journey.mjs:239-273]`. **Dangling reference found:** the component comment at `SourceCard.tsx:18` names
`tests/test_web_source_labels.py`, which does not exist (`git ls-files | grep test_web` → measured_guard,
portfolio_surface only). `evidence/page.tsx:9` makes the same mistake with `tests/test_web_routes.py`; its real
guard is `test_web_portfolio_surface.py:135` (`test_evidence_route_does_not_depend_on_the_api`). Correct both
comments in the pass that touches these files — a trust surface should not cite a guard that is not there.

### 6.2 Three defects to fix in v2

1. **"Verified" means two different things.** Record-level `sample_verified` renders **Verified**; a quote is
   "verified" when its text was found in the cited chunk (`q.verified`) — a string match, not a human review.
   Both wear the word `Verified` in the same panel pair `[OBS Chat.tsx:338, 357-359; SourceCard.tsx:26]`.
   `[PROP]` rename the quote badge to **"Matched to source text"** and reserve **Verified** for the record
   status. One extra word removes the most expensive ambiguity in the product.
2. **The quote heading over-claims.** "Verified source quotes [N]" is a container label over rows that can each
   render **✗ Unverified** `[OBS Chat.tsx:338 vs 361-365]`. `[PROP]` "Policy quotes [N] · V verified", and when
   `V < N` split the list into "Verified (V)" and "Unverified (N−V)" groups.
3. **`Quote.status` is typed and unused.** `Chat.tsx:11` declares `status?: string | null` on a quote and no
   render path reads it. `[PROP]` map it through the same `labelFor()` used by `SourceCard` so a quote row
   carries the same stamp as the record it came from (`[CHECK R4]`).

### 6.3 One vocabulary everywhere

`/coverage` prints raw `data_status` values in the breakdown and in per-jurisdiction rows
`[OBS coverage/page.tsx:201-203, 232-235]` — so the same corpus speaks two languages depending on the page.
`[PROP]` export a single `labelFor(status)` from `SourceCard.tsx` (or a shared `web/lib/provenance.ts`), use it
in both, and keep the raw value in a `data-status` attribute for tests. `[CHECK R2]`.

### 6.4 F2 / F3 as *rendering* behaviour only (no security decision here)

- **F2 (`source_url` has no host allowlist).** Whatever the security owner decides, the UI must stop making an
  unqualified trust claim: `[PROP]` render the destination host next to the link — `official source ↗
  (pmkisan.gov.in)` — and, if the value is not `http(s)`, render it as **plain text** labelled "link not usable"
  rather than as an anchor. This is display logic only; it neither adds nor replaces an allowlist.
- **F3 (`/coverage` trusts the upstream JSON shape).** `[PROP]` narrow the payload with a type guard before
  render and fall back to the existing `unavailable` state with reason "the API returned an unexpected coverage
  payload". Today a wrong-typed `catalog_by_status` reaches `Object.entries` and crashes to the Next error
  boundary instead of the labelled state `[OBS coverage/page.tsx:57-68, 201-203]` — the only state on the site
  that shows a framework error page rather than an honest sentence. `[CHECK S4]` is expected to fail until this
  lands.

### 6.5 Citations inside the answer body

`[OBS]` the answer is one `<p>` with `whitespace-pre-wrap` `[Chat.tsx:294-302]`; the assessment observed literal
`**₹6,000 per year**` and `[schemes/pm-kisan.md, sample_verified]` in a real answer (Chat.tsx:299 applies no
transform). `[PROP]` a deliberately small renderer, no dependency: split on blank lines into paragraphs, render
`**…**` as bold, and match `\[([^,\]]+),\s*([a-z_]+)\]` into a citation chip whose label is `labelFor(status)`
and whose anchor scrolls to the matching `SourceCard`. Anything else stays literal text — do not attempt full
markdown. `[CHECK R5]` asserts the live-shaped stub answer contains no literal `**` and that each chip's text
maps to a source row.

---

## 7. State matrix — failure, loading, offline

| State | Trigger | Current rendering | Gap | Proposed v2 | Check |
|---|---|---|---|---|---|
| Empty | `/`, no messages | OfflinePanel only if `!apiConfigured`; else sample cards + composer `[OBS Chat.tsx:228-232, 435-459]` | Fine for both audiences | Keep | `[E2E]` |
| Streaming | after submit | Pill + caret, no announcement `[OBS Chat.tsx:246-253, 294-302]` | Silent to AT; focus lost | Live region + focus → Stop | K3, A1 |
| Done · live | `done{mode:"live"}` | "Live mode · Groq RAG" badge, quotes, sources, feedback `[OBS Chat.tsx:264-271, 334-428]` | Provider claim; quote header over-claims | Provider-free badge; counted header | R3 |
| Done · demo | `done{mode:"demo"}` | "Demo mode — no live model key configured" `[OBS Chat.tsx:255-262]` | Clear and honest | Keep | — |
| Offline (permanent) | `API_URL` unset → 501 `{offline:true}` `[OBS route.ts:20-38]` | OfflinePanel + full MetricsPanel inside the transcript `[OBS Chat.tsx:244, OfflinePanel.tsx:4-32]` | Good design, but only reachable when no API is configured | Keep; also link `/evidence` | `[CHECK S2]` |
| API unreachable | `fetch` throws → 502 `[OBS route.ts:48-56]` | Error box + Retry; 502-specific 30 s copy `[OBS Chat.tsx:124-135, 304-332]` | No `role="alert"`; Retry can fail identically; focus lost | `role="alert"`, focus → input, "Try again" | A3, S1 |
| Upstream rejected | upstream non-2xx → passthrough message `[OBS route.ts:57-65]` | Generic "verify the question or retry shortly" | Retry deterministically repeats a 4xx; no distinction from 5xx | Surface "this question was rejected — rephrase" for 4xx, keep Retry for 5xx | S1 |
| Aborted | Stop button `[OBS Chat.tsx:485-492]` | Stream stops, partial text stays, no label | User cannot tell "stopped" from "finished short" | Add "Stopped — answer may be incomplete" | K3 |
| `/coverage` loading | slow upstream | `loading.tsx` skeleton, `role=status`, `aria-busy` | Only accessible loading state on the site | Reuse the pattern for the homepage pill | S5 |
| `/coverage` unavailable | timeout >4 s / non-2xx | Labelled, `role=alert`, reason + committed figures `[OBS coverage/page.tsx:128-160]` | Good | Keep | `[E2E]` |
| `/coverage` malformed | wrong-typed JSON | Next error boundary `[OBS, per security F3]` | Framework error page = the one dishonest state | Type guard → `unavailable` | S4 |
| Home standby | `!apiReachable && apiConfigured` | Notice: "Example queries and demo answers remain fully functional" `[OBS page.tsx:65-74]` | **False**: the offline payload exists only when `API_URL` is unset `[OBS route.ts:20-38]`; in this state every ask returns 502 | "The answering service is waking up or down. Your question will fail until it returns — the measured evidence is still available." | R6 |

---

## 8. Prioritised v2 changes

### P0 — must fix now (bounded, one implementation pass, no new route, no new dependency)

| # | Change | Why | Where |
|---|---|---|---|
| P0-1 | One polite live region for the answer lifecycle + `role="alert"` on errors + `aria-busy` on the answer | The product is a streamed answer; today it is completely silent to AT | `Chat.tsx` (new status node, error box) |
| P0-2 | Skip link → `#main`; `aria-current="page"` on nav | First-tab and orientation on a 3-route site | `layout.tsx:36`, `Chrome.tsx:29-44` |
| P0-3 | Quote panel: counted header, split verified/unverified, map `q.status` | The panel currently contradicts itself over the word "Verified" | `Chat.tsx:334-382` |
| P0-4 | Shared `labelFor(data_status)` on `/coverage` | Same corpus, two vocabularies | `SourceCard.tsx`, `coverage/page.tsx:201-243` |
| P0-5 | Focus contract: focus → Stop on submit, → input on terminal state; `readOnly` instead of `disabled` | A keyboard user is dropped to `body` for the whole stream | `Chat.tsx:474-501` |
| P0-6 | 24 px minimum hit area on LANG, nav, feedback; 44 px on Ask/Stop at 375 | WCAG 2.2 AA 2.5.8 failures, measured | `Chrome.tsx:8-44`, `Chat.tsx:407-424, 494-501` |
| P0-7 | Reduced-motion reset covering `animate-pulse` and transitions | Motion contract is half-implemented | `globals.css:75-84` |
| P0-8 | `<html lang>` follows the toggle | G11; cheap and testable | `LanguageProvider.tsx:21-29` |
| P0-9 | Contrast: `ink/45` → `ink/60`; red-on-dim headings → `ink` | The honesty labels are the least readable text (3.31:1) | `SourceCard.tsx:94,111`, `MetricsPanel.tsx:105-108`, `evidence/page.tsx:63-65` |
| P0-10 | Home: `<Suspense>` the coverage pill so the hero does not wait on the API | 2 s TTFB risk on every cold free-tier visit | `page.tsx:37-74` |
| P0-11 | Fix the standby notice's false promise | Copy currently promises demo answers that cannot exist in that state | `page.tsx:65-74` |

### P1 — next slice (defer, still bounded)

1. Minimal answer renderer (paragraphs, bold, citation chips) + copy/permalink per answer (§6.5, G15).
2. Per-metric anchors on `/evidence`; uniform footer link row on all three routes.
3. Pin `EVIDENCE.*` URLs to a commit SHA instead of the branch ref `[measured.ts:64-75]` — gated by the D1
   decision, which is the user's.
4. `/coverage` type guard for malformed payloads (F3 rendering) — if the security owner does not land it first.
5. Source-link host display + non-http(s) plain-text rendering (F2 rendering).
6. Collapse "Execution pipeline" behind `<details>`; remove or drive `MODE[—]`; drop `role="text"`.
7. 320 px + 200 % zoom checks; safe-area bottom padding on the composer.
8. Fix the two dangling test references in source comments (`SourceCard.tsx:18` names a non-existent
   `tests/test_web_source_labels.py`; `evidence/page.tsx:9` names a non-existent `tests/test_web_routes.py`).
   The real guards are both in `tests/test_web_portfolio_surface.py`.

### P2 — not now (recorded so nobody re-litigates it)

Favicon/robots/sitemap/OG image (G6); `/method` or `/about` route; sticky/mobile composer; chat persistence;
answer permalinks across sessions; dark theme (G16 says single-theme is deliberate — keep); service-worker
offline mode; query-param handoff from `/coverage` to `/`.

### Explicitly not UI (do not fold into this slice)

- **Security** F1 (CSP/XFO/nosniff/referrer), F2 allowlist, F3/F4 backend shape and caching, F5 XFF/rate-limit
  bucket. §6.4 borrows F2/F3 only as display states.
- **Release/deploy** G1 (canonical branch / PR #2), G17 (CI triggers), G18 (build SHA — the footer slot is a UI
  hook, the value is release-ops'), G20 (cold-start cost decision, D2).
- **Product** D3 (retire the Streamlit UI), D4 (promotion of a shared free-tier key).

---

## 9. Implementation map

| Change | Files | Route(s) | Existing test surface |
|---|---|---|---|
| P0-1, P0-3, P0-5 | `web/components/Chat.tsx` | `/` | `web/e2e/journey.mjs` (add K3, A1-A3, R3) |
| P0-2, P0-6 | `web/app/layout.tsx`, `web/components/Chrome.tsx`, `web/app/globals.css` | all | new K1, K2, A6, T2 |
| P0-4, P0-9 (labels) | `web/components/SourceCard.tsx`, `web/app/coverage/page.tsx` | `/coverage`, `/` | `tests/test_web_source_labels.py`, harness R1/R2 |
| P0-8 | `web/components/LanguageProvider.tsx` | all | new A4 |
| P0-7, P0-9 (tokens) | `web/app/globals.css`, `MetricsPanel.tsx`, `evidence/page.tsx` | all | new M1; contrast is computed, not asserted |
| P0-10, P0-11 | `web/app/page.tsx`, `CoveragePill.tsx` | `/` | new P1 (TTFB), R6 (copy) |

Guardrails that already exist and must keep passing: `python tools/check_doc_links.py`,
`python tools/check_claims.py`, `python -m pytest -q tests/test_web_portfolio_surface.py
tests/test_web_measured_guard.py tests/test_evidence_guards.py`, `node web/e2e/journey.mjs --base …`.
Do not change a gate floor or an evidence number to make a UI check pass; if a number is wrong, the evidence
document changes first (`measured.ts:4-8` says exactly this).

---

## 10. Testable browser checks

Extend `web/e2e/journey.mjs` (364 lines, CDP over Node's built-in WebSocket, Chromium at
`%LOCALAPPDATA%/hermes/tools/chromium-1208`, deterministic stub at `web/e2e/stub-api.mjs`). Every check below
is a named `check(...)` in that harness; none of them requires a new dependency. Viewports: **1440×900** and
**375×812**, plus **320×640** for T1/T4.

| ID | Check | How |
|---|---|---|
| K1 | Skip link is the first Tab stop; Enter moves focus into `main` | Tab once, assert the anchor is focused and visible (`getBoundingClientRect().height > 0`), then `document.activeElement` inside `main` |
| K2 | Tab order matches visual order | Walk Tab 8 times, record `textContent`; expect `SchemeGPT, Evidence, Coverage, LANG` |
| K3 | Submitting moves focus to Stop; Escape aborts; focus returns to the input | `activeElement.dataset` after submit; dispatch Escape; `activeElement === input` |
| K4 | Visible focus ring on every interactive element | For each: focus, read `getComputedStyle(el).outlineWidth` ≥ 2 px and `outlineStyle !== "none"` |
| A1 | Streaming start is announced once | `role="status"` text matches the submit message; `aria-busy="true"` on the answer container |
| A2 | Completion announcement carries counts | Status text matches `Answer ready. \d+ sources, \d+ of \d+ verified quotes.` |
| A3 | Failure is an alert | `[role="alert"]` exists and contains the error copy |
| A4 | `documentElement.lang` follows the toggle and survives reload | en → toggle → hi → reload → `localStorage` + `lang` still hi |
| A5 | H1 accessible name is exactly "Ask your government." once | Compute name from the h1 subtree; assert no duplicate letter spans contribute text |
| A6 | `aria-current="page"` on the active nav item | On `/evidence`, the Evidence link has it |
| R1 | Every `data_status` gets a distinct label | Stub returns all five; assert the five labels in `[data-testid=source-card]` order |
| R2 | `/coverage` uses reader labels, not raw keys | Body contains "Imported · unverified"; no visible `myscheme_import` outside a `data-status` attribute |
| R3 | Quote header cannot over-claim | Stub with 1 verified + 2 unverified: header must not match `/^Verified source quotes/`; must contain "2 unverified" |
| R4 | Quote rows carry their record stamp | Each quote row's stamp equals the matching source row's stamp |
| R5 | Answer body has no literal markdown/citation tokens | Rendered answer contains no `**` and no `[doc, status]`; each citation chip resolves to a source row |
| R6 | Standby notice does not promise working demo answers | With `API_URL` set and the stub down: body must not contain "demo answers remain fully functional" |
| T1 | No horizontal scroll at 375 and 320 | `documentElement.scrollWidth <= innerWidth + 1` at both widths |
| T2 | Standalone controls ≥ 24×24 | Rect check on LANG, both nav links, both feedback buttons |
| T3 | Ask/Stop ≥ 44 px high at 375 | Rect check |
| T4 | Long source name wraps | Stub returns a 90-char filename; `card.scrollWidth <= card.clientWidth` |
| T5 | 200 % text zoom does not clip | Set root font-size 32 px, assert H1 and composer fully visible, no overflow |
| M1 | Reduced motion stops all animation | `Emulation.setEmulatedMedia {prefers-reduced-motion: reduce}`; `document.getAnimations().filter(a => a.playState === "running").length === 0` on `/` and during a stream |
| S1 | Failure → Retry succeeds when the stub recovers | Stub failure mode, flip to success, click Retry, assert a full answer |
| S2 | Permanent offline state is honest | Build/run with `API_URL` unset: OfflinePanel visible, MetricsPanel has 4 cards, no console error |
| S3 | `/coverage` unavailable leaks nothing | Stub down: `role="alert"`, reason present, body has no `127.0.0.1`, no `API_URL` value |
| S4 | `/coverage` malformed payload stays labelled | Stub returns wrong-typed JSON: expect `coverage-unavailable`, **not** a Next error boundary (expected to fail pre-fix) |
| S5 | `/coverage` loading is accessible | Slow stub (3 s): `role="status"` + `aria-busy="true"` present while pending |
| P1 | Hero does not wait for the API | `curl -w '%{time_starttransfer}'` against a local prod build with `API_URL` pointing at a blackhole: TTFB < 300 ms, pill resolves later |

Not asserted here and left to the verifier/axe pass: full colour-contrast audit of computed styles (the ratios
in §5.6 are arithmetic on tokens, which is necessary but not sufficient — a real axe run can still find
component-level combinations), screen-reader speech order, and Safari/Firefox behaviour.

---

## 11. Invariants this brief will not break

1. Zero border radius `[globals.css:24-29]`; paper/ink palette `[globals.css:4-13]`; Archivo + Martian Mono +
   Noto Sans Devanagari `[layout.tsx:7-18]`. This is the brand and it works — no restyle is proposed.
2. `/evidence` stays static and API-independent `[evidence/page.tsx:4-12]`; the measured numbers stay in
   `measured.ts` and are guarded by `tests/test_web_measured_guard.py`.
3. Honest labelling stays stronger than the components (`sample_verified` never becomes a generic "Source").
4. Nothing in the UI may imply a verified citation that is an import, a directory seed, or an absent URL.
5. No new public API endpoint, no new secret, no `NEXT_PUBLIC_*` (security review's scope map).

## 12. Reproduction

```bash
# base and state
git -C C:/Users/oliad/Desktop/SchemeGPT.wt/ux-brief rev-parse HEAD        # b49c4a4…
git -C C:/Users/oliad/Desktop/SchemeGPT.wt/ux-brief status --porcelain    # empty before this doc

# contrast arithmetic (no browser, no dependency)
python - <<'PY'
def lum(c):
    f=lambda v:(v/255)/12.92 if v/255<=0.03928 else (((v/255)+0.055)/1.055)**2.4
    r,g,b=[f(x) for x in c]; return .2126*r+.7152*g+.0722*b
def ratio(fg,bg=(251,250,244)):
    a,b=lum(fg),lum(bg); a,b=max(a,b),min(a,b); return (a+.05)/(b+.05)
def blend(a):  # black over paper at alpha a
    return tuple(round(251+(0-251)*a) for _ in range(3))
for a in (.45,.50,.55,.60,.70,.75,.85,.90): print(a, round(ratio(blend(a)),2))
PY

# UI queries actually used (skill-local script, no network)
python "<skills>/ui-ux-pro-max/scripts/search.py" "live status announcement screen reader" --domain ux -n 3
python "<skills>/ui-ux-pro-max/scripts/search.py" "touch target size" --domain ux -n 3
python "<skills>/ui-ux-pro-max/scripts/search.py" "streaming suspense focus" --stack nextjs -n 3

# existing browser harness (builder's; stub API, no live calls)
node web/e2e/stub-api.mjs --port 8099
API_URL=http://127.0.0.1:8099 npx next start -p 3100
node web/e2e/journey.mjs --base http://127.0.0.1:3100
```

## 13. Open questions for the integration owner

1. **Line drift.** `t_ff557fc5` starts from the security-reviewed SHA, not `b49c4a4`. Re-anchor each P0 item by
   symbol (`stampFor`, `STATUS_STAMPS`, the quote panel JSX, the composer form) before editing.
2. **Does the security baseline already change `/coverage`'s payload handling?** If F3 is fixed in that branch,
   S4 becomes a regression test rather than new work; if not, it is P1 item 4.
3. **Is `readOnly` acceptable on the composer?** It preserves focus and prevents typing mid-stream, but changes
   the visual affordance (`disabled:opacity-50` styling). If the builder prefers `disabled`, it must implement
   K3's focus-to-Stop explicitly.
4. **Where does the standby notice get its authority?** `initialApiReachable` is dead (`Chat.tsx:77`); the
   server already knows whether the API answered within 2 s. Wiring it is preferable to deleting it, but it is
   a component-contract change, so it is P1, not P0.
5. **Deployment is out of scope for this brief.** None of the above has been seen in a browser by me, and none
   of it is claimed to be live; the integration card owns the first real browser evidence.
