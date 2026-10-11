# Temporal inventory: how much real version signal this corpus contains

Phase 8 / track 1, **Task 0**. This is the honesty gate for the whole
"answer as of a date" track. The corpus was captured as a **single snapshot**,
so the question is not "can we build a version-history feature" but "does the
corpus contain any *declared* date we may build one on". This document reports
the measured answer, not the hoped-for one. **Zero declared dates would have
been a valid result; it is not zero, but it is a small minority.**

**Bottom line:** of **2,105** ingested documents, **79 declare an effective /
amendment / notification date** (`declared`), **44 carry a non-authoritative
date only** (`inferred`), and **1,982 carry no temporal signal at all**
(`none`). A real, quotable before/after pair **does exist** — the Haryana
destitute-children assistance rate ladder in `data/myscheme/fadcs.md` — so the
track can be anchored in fact for a minority of documents. The rest of the
corpus cannot support a real version history. See
[What this means for the plan](#what-this-means-for-the-plan).

## Scope

| Source | Files | Role |
| --- | ---: | --- |
| `data/myscheme/*.md` | 2,063 | automated myScheme import (`data_status: myscheme_import`) |
| `data/schemes/*.md` | 6 | hand-verified central schemes (`sample_verified`) |
| `data/states/*.md` | 36 | state/UT discovery seeds (`directory_seed`) |
| **Total** | **2,105** | read-only |

The Postgres corpus (`scheme_docs_v2`) holds **26,395** chunks from exactly
these 2,105 sources under a single `corpus_generation`. Its provenance is
reported in [Postgres provenance](#postgres-provenance) and adds no date the
files do not already carry.

## Reproduce

```bash
# per-class counts and the summary table
./.venv/Scripts/python.exe scripts/inventory_temporal_signal.py

# machine-readable payload (every number quoted below)
./.venv/Scripts/python.exe scripts/inventory_temporal_signal.py --json

# audit which documents were classified declared, and by which clause
./.venv/Scripts/python.exe scripts/inventory_temporal_signal.py --list-declared
```

The script is **stdlib-only, offline, and read-only**. It reads the three
Markdown trees, `data/scheme_catalog.json`, and `data/.cache/myscheme_pdfs/`.
It writes nothing and makes no network call.

## Classification rules

Every document is assigned **exactly one** class. Signals are ranked; the
strongest present wins.

| Class | Definition | Count |
| --- | --- | ---: |
| `declared` | The document states its **own** effective / amendment / notification date: an effective/amendment clause *and* a **specific calendar date** (day-month-year or month-year) within 100 characters. | **79** |
| `inferred` | No declared clause, but the record carries a **non-authoritative** date: the front-matter `Checked on` / `Last verified` line (42 catalog records) or a four-digit **year in the filename** (2 files). | **44** |
| `none` | No declared clause and no recorded non-authoritative date. | **1,982** |
| **Total** | | **2,105** |

Per directory:

| Source | `declared` | `inferred` | `none` |
| --- | ---: | ---: | ---: |
| `data/myscheme/` | 79 | 2 | 1,982 |
| `data/schemes/` | 0 | 6 | 0 |
| `data/states/` | 0 | 36 | 0 |

The 42 catalog records break down as the 6 `data/schemes/` documents (each
carries `**Checked on:** 2026-08-02`) and the 36 `data/states/` documents (each
carries `**Last verified:** 2026-08-02`). All 42 also appear as
`last_verified: 2026-08-02` in `data/scheme_catalog.json` and in the Postgres
chunk metadata.

The 2 `inferred` `data/myscheme/` documents carry a four-digit year in the
filename and no declared clause: `data/myscheme/rgssspf-2012.md` (2012) and
`data/myscheme/sda2013.md` (2013).

### Why `mtime` is not used as the `inferred` signal

Every one of the 2,105 files has an mtime, so counting mtime would make
`none = 0` by construction and carry no information. The mtime is also not
evidence about when a document took effect: cloning, checkout and copying all
rewrite it. It is recorded below as a **hint**, exactly as the brief requires,
and deliberately excluded from the classifier. For completeness, running the
script in `--count-mtime` mode yields the degenerate `declared=79,
inferred=2,026, none=0`, which is why it is not the default.

Recorded `data/**` mtimes span
`2026-08-18T20:05:55Z .. 2026-09-01T18:32:22Z` (all 2,105 files). That is the
span of a single checkout/copy, not a span of scheme effective dates, which is
precisely why it is a hint and not a fact.

## Evidence patterns

The actual patterns searched (case-insensitive; `DATE` is the specific-date
regex below). "Qualified" = clause present **and** a specific date within the
window, i.e. what feeds `declared`; "phrase" = the clause appears at all.

| Pattern | Regex / keyword | Qualified files | Phrase-present files |
| --- | --- | ---: | ---: |
| `w.e.f` | `\bw\s*\.\s*e\s*\.\s*f\.?\b` | 22 | 28 |
| `with effect from` | `\bwith effect from\b` | 15 | 21 |
| `effective from` | `\beffective from\b` | 4 | 13 |
| `came into force` | `\bcame into force\b` | 11 | 12 |
| `came into effect` | `\bcame into effect\b` | 2 | 2 |
| `as amended by` | `\bas amended by\b` | 0 | 2 |
| `amended by` | `\bamended by\b` | 0 | 3 |
| `amended vide` | `\bamended vide\b` | 0 | 0 |
| `inserted by` | `\binserted by\b` | 0 | 0 |
| `substituted by` | `\bsubstituted by\b` | 0 | 0 |
| `amendment ... dated` | `\bamend(?:ment\|ed)\b[^.\n]{0,60}\bdated\b` | 1 | 1 |
| `notification/order ... dated` | `\b(?:notification\|order\|circular\|memorandum\|resolution\|gazette\|letter\|g\.?r\.?\|o\.?m\.?)\b[^.\n]{0,80}\bdated\b` | 8 | 9 |
| `dated <date>` | `\bdated\b` | 35 | 41 |
| `as on <date>` | `\bas on\b` | **3** | 65 |
| `revised ... <date>` | `\brevis(?:ed\|ing)\b` | 6 | 51 |

`DATE` (the specific-date requirement; a bare year does **not** qualify):

```regex
\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b
|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:January|...|December),?\s+\d{4}\b
|\b(?:January|...|December)\s+\d{1,2},?\s+\d{4}\b
|\b(?:January|...|December),?\s+\d{4}\b
```

Two calibrations are worth stating outright, because both **reduce** the
declared count rather than inflate it:

* **`as on <date>` is reported but not counted.** The phrase appears in 65
  documents, but inspection shows it is always an *eligibility reference date*,
  never a document effective date — e.g. `data/myscheme/tncmfp.md`
  ("age ... as on 25.05.2022"), `data/myscheme/pmbjp.md` ("sales ... as on
  30.11.2023"), `data/myscheme/pmuy.md` ("as on 1st Jan 2016"). Counting it
  would have added 3 documents to `declared`; they are not effective dates.
* **A bare year does not satisfy the date requirement.** This drops phrases
  such as `data/myscheme/dtu-cmsguy.md` ("income by 2022 ... new revised tractor
  scheme") that share a year with a clause but declare no effective date. It
  also drops `as amended by` / `amended by`, which occur only with statute
  enactment years (`... Order, 1950 (as amended by ...)` in
  `data/myscheme/asha(1).md`), not with a scheme date.

## Verbatim examples

Each line below is copied from the named file. Where the source wraps a line,
the wrap is marked `⏎`; spacing inside the line is otherwise unchanged.

1. `data/myscheme/fadcs.md` (Financial Assistance to Destitute Children
   Scheme, Haryana) — a rate ladder:
   > Initially the rate of financial assistance of ₹200/- per month per child w.e.f. 01.03.2009.⏎
   > The rate of pension under this scheme is ₹500/- per month per child from January 2014, ₹700/- w.e.f. 01-11-2016, ₹ 900/- w.e.f. 01-⏎
   > 11-2017, ₹1100/- w.e.f. 01-11-2018, ₹1350/- w.e.f. 01.01.2020, ₹1600/- w.e.f. 01.04.2021 and ₹1850/- (one child) w.e.f.⏎
   > 01.04.2023.

2. `data/myscheme/aes.md` (Allowance to Eunuchs Scheme, Haryana) — a rate
   ladder:
   > The rate of allowance was ₹1400/- per month per beneficiary w.e.f.⏎
   > 01.01.2016, ₹1600/- w.e.f. 01.11.2016, ₹1800/- w.e.f. 01.11.2017, ₹2000/- w.e.f. 01.11.2018, ₹ 2250/- w.e.f. 01.01.2020, ₹2500/-⏎
   > w.e.f. 01.04.2021 and ₹ 2750/- w.e.f. 01.04.2023.

3. `data/myscheme/40shydcs.md` — effective date:
   > ... for sale, if these are used in the industry for manufacturing or on sales or any other production related purpose with effect from 1st Dec 2016.

4. `data/myscheme/aewc-mesifai-vi.md` — commencement:
   > The scheme came into force with effect from 1st April 2017 and is in operation in the whole⏎
   > of the UT of Puducherry.

5. `data/myscheme/aasra.md` — a dated order:
   > ... the scheme is being implemented by the Government vide Order No. 150-F of 2015 dated 20.08.2015.

6. `data/myscheme/ctms.md` — a dated gazette notification:
   > ... by the Ministry of MSME vide Gazette Notification No. S.O. 581(E) dated 23rd March, 2012 has⏎
   > circulated the Public Procurement Order 2012 for MSME.

7. `data/myscheme/nspgy.md` — two dated notifications:
   > ... Notification No.5654 dated 27.06.2009 and No.5985 dated 28.07.2014 of the Labour & ESI Deptt., Govt. of Odisha ...

8. `data/myscheme/ati.md` — an amendment date:
   > ... Notification No.H22011/2/2014-SDE-I dated 15.07.2015 as amended from⏎
   > time to time.

## Limits of each signal class

**`declared`.** A declared date is usable as fact, but only for the document
that states it. Most are **eligibility cut-offs or commencement/notification
dates**, not values that changed: `dated <date>` (35 files) and
`notification/order ... dated` (8) usually fix when a rule was issued, not when
a benefit amount changed. The `revised ... <date>` clause is the noisiest of
the counted patterns (6 of 51 phrase hits get a date); a few — e.g.
`data/myscheme/amas-haryana.md` ("Revised – 2009") — are revision *labels*, not
clean effective dates. A declared date also does **not** imply the document
records the *superseded* value: only the rate-ladder documents (next section)
provide both sides of a before/after pair.

**`inferred`.** The `Checked on` / `Last verified` value is when the record was
verified/fetched, **not** when the scheme took effect. Treating it as an
effective date would be exactly the fabrication this task forbids. The
filename years (`rgssspf-2012`, `sda2013`) name the scheme's vintage in a slug,
not a document version.

**`none`.** 1,982 documents (94.2%) contain no declared date whatsoever. This is
the dominant truth of the corpus: for these, any version history would be
invented.

**File mtimes.** Universal, therefore uninformative, and rewritten by
clone/copy — a hint only, never a fact. See
[Why `mtime` is not used](#why-mtime-is-not-used-as-the-inferred-signal).

**Source URL / filename dates.** Every `myscheme` source URL is
`https://www.myscheme.gov.in/schemes/<slug>` — the slug carries no date.
Only 5 of 2,105 filenames embed a four-digit year (`kmys2016`, `rgssspf-2012`,
`sda2013`, `sdys2016`, `sjgdys2016`); of these, 3 already have a declared
clause and the other 2 are the `inferred` filename cases above. Filenames
therefore add essentially no temporal signal.

**Cached artefacts.** `data/.cache/myscheme_pdfs/` holds 2,153 PDFs (the
dataset ships duplicates). Their timestamps span
`2026-09-01T17:24:45Z .. 2026-09-01T18:32:22Z` — a single download burst, i.e.
when the cache was populated, not when any scheme took effect. Same caveat as
mtimes; not used for classification.

## Postgres provenance

Inspected read-only (no writes). The chunk metadata carries **no** fetch
timestamp and **no** content hash. Exact queries and results:

```sql
-- table public.scheme_docs_v2: 26,395 rows, one generation
SELECT corpus_generation, count(*) FROM scheme_docs_v2 GROUP BY 1;
-- 7213926b8590933d7ae13281f84597695ee8a5df60f8a2b1b133361465a6e689 | 26395

-- the only keys present in the metadata JSON
SELECT DISTINCT jsonb_object_keys(metadata::jsonb) FROM scheme_docs_v2;
-- chunk_index, data_status, jurisdiction, last_verified, source, source_url, state

SELECT metadata->>'data_status', count(*) FROM scheme_docs_v2 GROUP BY 1;
-- myscheme_import | 26305 ; directory_seed | 72 ; sample_verified | 18

SELECT DISTINCT metadata->>'last_verified' FROM scheme_docs_v2;
-- 2026-08-02
```

The active-corpus bookkeeping table `scheme_docs_vector_metadata` holds
`embedding_model=intfloat/multilingual-e5-small`,
`corpus_generation=7213926b...a6e689`, `corpus_chunk_count=26395`. The only
date anywhere in Postgres is `last_verified = 2026-08-02` on the 42 catalog
records — a **verification** date, already captured by the `inferred` class. No
`fetched_at`, creation time, or hash is stored.

## The six hand-verified central schemes (R3)

The `data/schemes/` records are the richest, hand-written documents and the
best hope of a real before/after pair. **None contains amendment or
effective-date language.** All six are `inferred` (via the front-matter
`Checked on: 2026-08-02` verification date), so they cannot anchor a real
version history.

| Document | Class | Amendment / effective clause | Recorded date | Other date language |
| --- | --- | --- | --- | --- |
| `data/schemes/pm-kisan.md` | `inferred` | none | `Checked on: 2026-08-02` | "launched in February 2019"; "As of the 2024-25 financial year" |
| `data/schemes/ayushman-bharat.md` | `inferred` | none | `Checked on: 2026-08-02` | eligibility cites "SECC 2011" (a census year, not an effective date) |
| `data/schemes/pmay-g.md` | `inferred` | none | `Checked on: 2026-08-02` | "original target until 2024" |
| `data/schemes/pm-sym.md` | `inferred` | none | `Checked on: 2026-08-02` | none |
| `data/schemes/gst.md` | `inferred` | none | `Checked on: 2026-08-02` | "introduced in India on 1 July 2017" |
| `data/schemes/startup-india.md` | `inferred` | none | `Checked on: 2026-08-02` | none |

`pm-kisan` and `gst` do declare *enactment* dates (a fact), but those are launch
dates, not amendment or effective-date clauses, and neither record contains a
superseded value. They cannot anchor a before/after pair on their own.

## Strongest real before/after candidate (R4)

**Found: one real before/after pair, anchored in a single document.**
`data/myscheme/fadcs.md` — *Financial Assistance to Destitute Children Scheme
(FADCS)*, Department of Social Justice and Empowerment, Government of Haryana —
states the same benefit value changing over time with an explicit effective
date for each change:

> Initially the rate of financial assistance of ₹200/- per month per child w.e.f. 01.03.2009.⏎
> The rate of pension under this scheme is ₹500/- per month per child from January 2014, ₹700/- w.e.f. 01-11-2016, ₹ 900/- w.e.f. 01-⏎
> 11-2017, ₹1100/- w.e.f. 01-11-2018, ₹1350/- w.e.f. 01.01.2020, ₹1600/- w.e.f. 01.04.2021 and ₹1850/- (one child) w.e.f.⏎
> 01.04.2023.

This is verifiable WITHOUT cross-document linking: ask "what was the FADCS
child allowance on 1 January 2021?" → **₹1350 per month** (in force from
01.01.2020 until 31.03.2021, when ₹1600 took over). The "as of a date" answer
and the supersession chain both come from this one file. The eight qualifying
values and their effect dates are: ₹200 (01.03.2009), ₹500 (Jan 2014), ₹700
(01.11.2016), ₹900 (01.11.2017), ₹1100 (01.11.2018), ₹1350 (01.01.2020), ₹1600
(01.04.2021), ₹1850 (01.04.2023).

Four more documents carry the same kind of same-value-over-time ladder:

| Document | Effect dates detected | Effect dates |
| --- | ---: | --- |
| `data/myscheme/hdps.md` | 10 | 1.1.2006, 1-1-2014, 01-01-2015, 1-1-2016, 01-11-2016, 01-11-2017, 01-11-2018, 01.01.2020, 01.04.2021 |
| `data/myscheme/lssas.md` | 10 | 01.04.2007, 01.04.2014, 01-01-2015, 1-1-2016, 01-11-2016, 01-11-2017, 01-11-2018, 01.01.2020, 01.04.2021, 01.04.2023 |
| `data/myscheme/aes.md` | 7 | 01.01.2016, 01.11.2016, 01.11.2017, 01.11.2018, 01.01.2020, 01.04.2021, 01.04.2023 |
| `data/myscheme/dot-pli-scheme.md` | 2 | 1st April 2021, 1st April 2022 |

(Two further "candidates" detected by the script — `atd.md` and `hsjps.md` —
are a single date written in two formats, e.g. `01-04-2021` / `01.04.2021`;
they are not changes.)

So the answer to "is there a real before/after pair in this corpus?" is **yes**
— but it lives in a small number of Haryana/state social-security rate tables,
not in the hand-verified central records, and it is a per-**value** ladder, not
a general per-document version chain.

## What this means for the plan

A real version history is available for a **small, enumerable minority** of the
corpus: 79 of 2,105 documents declare an effective/amendment/notification date,
and 5 of them (the Haryana rate ladders above, most clearly `fadcs.md`) document
a benefit value changing over time with an effective date for each change, which
is a genuine, quotable before/after pair. Those can anchor Tasks 3–5 in fact.
For the other ~94% of documents there is no declared effective date and no
superseded value, so any per-document version chain for them would be invented;
Tasks 3–5 must therefore be built and tested against a **clearly-labelled
synthetic history** for the bulk corpus, with the handful of declared-date
documents used as the real regression anchors and the honest ceiling on
achievable temporal accuracy stated alongside any synthetic number.

## What was built on this inventory (2026-10-06)

Task 0's decision — anchor only in declared dates, invent nothing — was carried
through Tasks 1–4. The synthetic-history fallback named in the previous paragraph
was **dropped** by the post-Task-0 amendment to the plan; the bulk corpus is not
given an invented version chain. The findings above (79 `declared` / 44
`inferred` / 1,982 `none`; the per-class table; the ladder table) are the
measured basis and are unchanged.

What now exists on top of this inventory:

- **The claims artifact** —
  [`eval/fixtures/temporal_claims.jsonl`](../../eval/fixtures/temporal_claims.jsonl):
  41 effective-dated claims over the 10 source ladders, every one carrying a
  verbatim `span` that a test proves literally appears in its named source.
- **The answer path** — [`app/temporal.py`](../../app/temporal.py) (dated
  claims, `resolve_as_of`, supersession chains) and
  [`app/temporal_answer.py`](../../app/temporal_answer.py)
  (`temporal_answer(question, as_of, language)`, `mode="as_of"`), which returns
  the value in force on the requested date with its verbatim span, or refuses
  without substituting a current value.
- **The gate** — [`eval/temporal_gate.py`](../../eval/temporal_gate.py) and the
  derived [`eval/fixtures/temporal_golden.jsonl`](../../eval/fixtures/temporal_golden.jsonl)
  (124 cases from the same 10 ladders, regenerable byte-identically by
  [`scripts/generate_temporal_golden.py`](../../scripts/generate_temporal_golden.py)).
- **The published evidence** —
  [`docs/evidence/TEMPORAL-GATE.md`](../evidence/TEMPORAL-GATE.md).
