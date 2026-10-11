# 01 Discovery

Purpose: to leave the first call with a quantified baseline, a named owner, and a list of things we
could not answer. Everything numeric produced on the call is an assumption until the customer
replaces it with their own measurement.

## Part A: template

### A1. Roles to have on the call

| Role | Why they must be there | If they are missing |
| --- | --- | --- |
| Programme owner (the person who signs the pilot) | owns the baseline numbers and the go/no-go decision | reschedule; a pilot without a decision owner stalls in week 3 |
| Helpdesk manager / supervisor | knows actual handling times, languages and peak periods | baseline stays a guess |
| IT / infrastructure contact | host, network egress policy, proxy, database | week 1 fails on `PF-042` / `PF-044` egress checks |
| Security or data-protection contact | is the person who can stop the engagement | book them for a second call in week 0, not week 4 |
| One or two front-line agents | reality-check the workflow description | you will design for a process that does not exist |

### A2. Agenda (45 minutes)

| Minutes | Item | Output |
| --- | --- | --- |
| 0-5 | what we are and what we are not (grounding, corpus split, no eligibility rulings) | shared boundary |
| 5-15 | current workflow walkthrough: who answers, in which language, from which source | process notes |
| 15-30 | quantify the baseline (worksheet A4) | filled input table |
| 30-38 | constraints: network, hosting, data-protection, procurement, seasonal peaks | constraint list |
| 38-45 | what we need from them for a four-week pilot, and by when | prerequisite list with owners |

### A3. Question bank

| Theme | Question | Why we ask |
| --- | --- | --- |
| Volume | how many citizen queries a month, by channel? | drives the whole cost model |
| Handling time | median and worst-case minutes per query, by query type? | second cost driver |
| Containment today | what share of queries close on first contact? | the number the pilot has to beat |
| Language | split across Hindi, English, Hinglish, other? | decides the retrieval and answer-language test set |
| Source of truth | which document does an agent read today, and how current is it? | tells us what the corpus must contain and who verifies it |
| Escalation | what escalates, to whom, how long does it take? | becomes our escalation path in `05-handoff-and-rollout.md` |
| Peaks | when is volume 1.5x or more, and why? | throughput planning against the 8k tokens/minute ceiling |
| Network | is there outbound HTTPS, a proxy, or a full air gap? | decides the install path on day 1 |
| Hosting | whose host, which OS, how much RAM/disk? | `deploy/field/preflight.py` must pass before we promise anything |
| Data protection | who is the data-protection contact, what is their review process? | the security packet goes to them in week 0 |
| Records | what do they have to keep, for how long, for audit? | retention rules that our storage must respect |
| Failure | if the system is wrong, who is accountable to the citizen? | fixes the disclosure wording and the review policy |

### A4. Quantification worksheet

Fill this before leaving the call. Mark each cell: measured by the customer, or assumption.

| Input | Symbol | Value | Source | Label |
| --- | --- | --- | --- | --- |
| Inbound queries per month | Q | | | |
| Average handling time, minutes | T | | | |
| Loaded cost per agent hour (INR) | C | | | |
| Repeat-contact rate | p | | | |
| Escalation rate and extra minutes | e, E | | | |
| Peak factor and peak months | k | | | |
| Language split | | | | |
| Corpus owner for verification hours | | | | |

Baseline formula, stated so it can be argued with:

```
baseline monthly cost = [ Q x (T/60) + Q x p x (T/60) + Q x e x (E/60) ] x C
baseline cost per inbound query = baseline monthly cost / Q
```

### A5. Outputs of the call

- filled worksheet A4, with every cell either customer-measured or labelled assumption
- constraint list (network, hosting, data-protection, procurement)
- prerequisite list with owners and dates (mirrors `02-pilot-scope.md` section 5)
- three written open questions, with the person who will answer each
- the security packet (`03-security-packet.md`) sent to the security contact within 48 hours

---

## Part B: filled exemplar

**This section is an illustrative example.** The customer, its volumes and its costs are fabricated
to show what a completed discovery looks like. No real department is named or described. Every
number below is marked assumption (yours to change) and must be replaced before any decision.

Illustrative customer: a state government welfare-scheme helpdesk (single state, 31 districts).
Its stated job is to answer citizen questions about eligibility, documents and application status
across central and state schemes.

### B1. What they told us

| Item | What we heard | Label |
| --- | --- | --- |
| Channels | 62 percent telephone, 22 percent walk-in at block offices, 16 percent web form; no WhatsApp channel in scope | assumption (yours to change) |
| Languages | 55 percent Hindi, 20 percent English, 25 percent mixed Hindi-English (Hinglish) | assumption (yours to change) |
| Query mix | about 40 percent eligibility, 25 percent documents required, 20 percent application status, 15 percent benefit amounts or timelines | assumption (yours to change) |
| Current source of truth | a shared drive of PDF circulars, a state portal, and the national MyScheme discovery portal; agents say the circulars disagree with the portal on some schemes | assumption (yours to change) |
| Review | no second-person review; no record of what an agent told a citizen | assumption (yours to change) |
| Escalation | district welfare officer, typically 3 to 7 working days | assumption (yours to change) |
| Peaks | two windows per year where volume reaches about 1.8x for 5 to 6 weeks | assumption (yours to change) |
| Constraint: network | no direct outbound HTTPS from the application VLAN; a corporate proxy exists and is inspected (TLS interception) | assumption (yours to change) |
| Constraint: hosting | one on-prem virtual machine can be provided, 8 vCPU, 16 GB RAM, 250 GB disk | assumption (yours to change) |
| Constraint: policy | the helpdesk may not issue an eligibility determination; it may only explain published criteria and point to the official source | assumption (yours to change) |
| Constraint: data protection | they hold no citizen identity data in the helpdesk today and want to keep it that way | assumption (yours to change) |

### B2. Baseline model (all inputs are assumptions (yours to change))

| Input | Symbol | Value | Label |
| --- | --- | --- | --- |
| Inbound queries per month | Q | 50,000 | assumption (yours to change) |
| Average handling time | T | 9 minutes | assumption (yours to change) |
| Loaded agent cost per hour | C | INR 350 | assumption (yours to change) |
| Repeat-contact rate | p | 18 percent | assumption (yours to change) |
| Escalation rate | e | 9 percent | assumption (yours to change) |
| Extra minutes per escalation | E | 25 minutes | assumption (yours to change) |
| Peak factor | k | 1.8x for 2 months per year | assumption (yours to change) |

Arithmetic (shown, so it can be challenged line by line):

```
first-contact hours   = 50,000 x 9/60                       = 7,500 hours
repeat-contact hours  = 50,000 x 0.18 x 9/60                = 1,350 hours
escalation hours      = 50,000 x 0.09 x 25/60               = 1,875 hours
total                 =                                      10,725 hours per month
baseline monthly cost = 10,725 x 350                        = INR 37,53,750 per month
baseline annual cost  = 37,53,750 x 12                      = INR 4,50,45,000 per year
cost per inbound query= 37,53,750 / 50,000                  = INR 75.08
peak-month cost       = 37,53,750 x 1.8                     = INR 67,56,750
```

### B3. Problem statement (one paragraph, with the numbers attached)

The helpdesk handles 50,000 citizen queries a month across telephone, walk-in and web, in Hindi,
English and Hinglish, using PDF circulars and portals that agents describe as disagreeing on some
schemes. Roughly 10,725 agent-hours per month, INR 37.5 lakh a month and INR 4.50 crore a year go
into answering them, and because no record is kept of what was told, neither the department nor the
citizen can audit an answer afterwards. Two peak windows per year push volume to about 1.8x, which
is currently absorbed by overtime or by leaving calls unanswered. The proposal is a retrieval system
that answers from a curated corpus in the language of the question, quotes the exact policy lines it
relied on, and says so when the corpus does not cover a scheme. It would not decide eligibility.

### B4. What the pilot would have to demonstrate (carried into `02-pilot-scope.md`)

| Claim to test | How it is measured | Threshold |
| --- | --- | --- |
| Agents can find the source faster than today | median time to a cited source line, timed on the same 20 questions before and during the pilot | assumption (yours to change): at least 3 minutes per query saved |
| Answers are usable as written | subject-matter reviewer scores a sample of answers usable without correction | assumption (yours to change): at least 70 percent on 200 sampled answers |
| Quotes are real | every quote carries a verified flag from exact substring checking; fabricated quotes counted | 0 fabricated quotes presented as verified |
| Hindi and Hinglish work | the 20-question bilingual set runs in both languages with citations | all 20 return at least one source |
| The helpdesk can stop it | kill switch engaged during business hours, degraded answers served, then re-enabled | under 5 minutes, service stays up |

### B5. Open questions from the call

| Question | Owner | Needed by |
| --- | --- | --- |
| Which document set is authoritative for the six highest-volume schemes, and who signs off a verified record? | programme owner | end of week 1 |
| Will the network team allow one HTTPS destination (`api.groq.com`) through the inspecting proxy, or must we install fully air-gapped? | IT contact | before week 1 |
| Does the data-protection contact require that profile or query text never leave the state network, in which case generation must run on a local model instead of the hosted provider? | data-protection contact | week 0 |
