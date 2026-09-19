# 04 ROI model

A transparent arithmetic model, not a business case. Every input is in the table with a low, expected
and high value, so the customer can replace our numbers with theirs and see the answer move. Nothing
here is a measurement of their helpdesk: all customer-facing inputs are assumption (yours to change).

Worked example below is labelled **illustrative example** and uses the same illustrative customer as
`01-discovery.md`. Currency is INR. Where a USD conversion is implied, the rate assumption is
INR 88 per USD 1 (assumption (yours to change); replace with the rate on the decision date).

## 1. Scope of the claim

The model claims only the first-contact handling time that a grounded answer lets an agent avoid.
Repeat contacts and escalations are excluded from the benefit side on purpose, even though they are
part of today's cost (the baseline in `01-discovery.md` includes them and comes to INR 75.08 per
inbound query, against INR 52.50 for first-contact handling alone). Claiming the smaller number makes
the case harder to attack.

## 2. Formula

```
s        = r + (1 - r) x g                     saved-time factor per query
H_saved  = Q x (T / 60) x s                    agent-hours avoided per month
L_avoid  = H_saved x C                         labour value of those hours, per month
B        = L_avoid x d                         realised benefit (d = share actually redeployed)
C_sys    = I + (Q x k / 1000) x P + (H_m x E_m) + (V_h x V_r)
N        = B - C_sys                           net monthly benefit
c_q      = C_sys / Q                           cost per answered query (delivery cost only)
c_today  = (T / 60) x C                        today's cost per query handled by hand
c_blend  = (C_sys + Q x (T/60) x (1 - r) x (1 - g) x C) / Q
P_off    = one_off / N                         payback in months
```

## 3. Inputs

| # | Input | Symbol | Low | Expected | High | Basis |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Queries per month served by the system | Q | 15,000 | 50,000 | 200,000 | assumption (yours to change) |
| 2 | Handling time per query, minutes | T | 5 | 9 | 15 | assumption (yours to change) |
| 3 | Loaded cost per agent hour, INR | C | 240 | 350 | 520 | assumption (yours to change); loaded means salary plus benefits plus overhead |
| 4 | Containment rate (answer closes the query, no human follow-up) | r | 0.20 | 0.35 | 0.55 | assumption (yours to change); must be measured in the pilot, AC-14 |
| 5 | Partial time credit on non-contained queries | g | 0.30 | 0.30 | 0.30 | assumption (yours to change); pre-answering shortens the call even when an agent finishes it |
| 6 | Model calls per answered query | k | 1.0 | 2.0 | 3.5 | assumption (yours to change); measured behaviour is a normalization call plus an answer call, more on agentic routes |
| 7 | Provider cost per 1,000 model calls, INR | P | 0 | 25 | 75 | Low is measured (from this repository): the shipped default is a free tier with no per-call charge. Expected and high are assumption (yours to change) for a paid tier or gateway, about USD 0.28 and USD 0.85 per 1,000 calls at the stated rate |
| 8 | Infrastructure per month, INR | I | 0 | 12,000 | 40,000 | assumption (yours to change); 0 if an existing VM is reused, higher if a dedicated host with backup storage is provisioned |
| 9 | Engineering hour rate, INR | E_m | 900 | 1,400 | 2,400 | assumption (yours to change) |
| 10 | Maintenance and retraining hours per month | H_m | 8 | 20 | 45 | assumption (yours to change); prompt and corpus upkeep, operator time, quarterly re-verification of the named schemes |
| 11 | Corpus verification hours per month | V_h | 0 | 40 | 120 | assumption (yours to change); making a record verifiable is a human cost |
| 12 | Verification hour rate, INR | V_r | 400 | 400 | 400 | assumption (yours to change) |
| 13 | Realisation factor (share of saved hours actually redeployed) | d | 0.25 | 0.50 | 0.90 | assumption (yours to change, and the single most political input) |

One-off cost, used only for payback. This pack asserts no licence fee because the pilot has none; if
the engagement adds one, add a row and re-run the model.

| One-off item | Hours | Rate, INR | Cost, INR | Basis |
| --- | --- | --- | --- | --- |
| Pilot engineering (install, kit, drills, analysis) | 160 | 1,400 | 2,24,000 | assumption (yours to change) |
| Corpus verification sprint (named schemes) | 400 | 400 | 1,60,000 | assumption (yours to change) |
| Enablement content and delivery | 40 | 1,400 | 56,000 | assumption (yours to change) |
| Field travel and on-site days | - | - | 1,50,000 | assumption (yours to change) |
| Subtotal | | | 5,90,000 | |
| Contingency 15 percent | | | 88,500 | assumption (yours to change) |
| **One-off total** | | | **6,78,500** | |

## 4. Worked case (illustrative example, expected column)

```
s        = 0.35 + (0.65 x 0.30)                     = 0.545
H_saved  = 50,000 x (9 / 60) x 0.545                = 4,087.5 agent-hours per month
L_avoid  = 4,087.5 x 350                            = INR 14,30,625 per month
B        = 14,30,625 x 0.50                         = INR 7,15,312 per month (realised)

C_sys    = 12,000                                   infrastructure
         + (50,000 x 2.0 / 1000) x 25 = 100 x 25    = INR 2,500   provider
         + (20 x 1,400)                             = INR 28,000  maintenance
         + (40 x 400)                               = INR 16,000  verification
         ------------------------------------------------------------
                                                    = INR 58,500 per month

N        = 7,15,312 - 58,500                        = INR 6,56,812 per month
c_q      = 58,500 / 50,000                          = INR 1.17 per answered query
c_today  = (9 / 60) x 350                           = INR 52.50 per query handled by hand
c_q,contained = 58,500 / (50,000 x 0.35)            = INR 3.34 per contained query
c_blend  = (58,500 + 50,000 x (9/60) x 0.65 x 0.70 x 350) / 50,000
         = (58,500 + 11,94,375) / 50,000            = INR 25.06 per query
           (against INR 52.50 today: 52 percent lower cost per query)
P_off    = 6,78,500 / 6,56,812                      = 1.03 months, about 5 weeks
```

## 5. The three columns

| Result | Pessimistic | Expected | Optimistic |
| --- | --- | --- | --- |
| Agent-hours avoided per month | 550 | 4,087.5 | 34,250 |
| Labour value, INR per month | 1,32,000 | 14,30,625 | 1,78,10,000 |
| Realised benefit, INR per month | 33,000 | 7,15,312 | 1,60,29,000 |
| System cost, INR per month | 7,200 | 58,500 | 2,48,500 |
| Net monthly benefit, INR | 25,800 | 6,56,812 | 1,57,80,500 |
| Cost per answered query, INR | 0.48 | 1.17 | 1.24 |
| Today's cost per query handled, INR | 20.00 | 52.50 | 130.00 |
| Payback on 6,78,500 one-off, months | 26.3 | 1.03 | 0.04 |

The pessimistic column is a combination of every unfavourable input at once (low volume, 5-minute
handling, low wage, low containment, no redeployment), not a forecast. It is in the table because a
model that cannot say no is not a model.

## 6. Sensitivity (expected values except the row being varied)

| Varied input | Value | Payback, months |
| --- | --- | --- |
| Q, queries per month | 15,000 / 30,000 / 50,000 / 100,000 / 200,000 | 4.30 / 1.83 / 1.03 / 0.50 / 0.24 |
| T, handling minutes | 5 / 9 / 15 | 2.00 / 1.03 / 0.60 |
| r, containment | 0.20 / 0.35 / 0.55 | 1.31 / 1.03 / 0.81 |
| d, realisation | 0.25 / 0.50 / 0.90 | 2.27 / 1.03 / 0.55 |

Payback is dominated by volume and handling time, not by model or infrastructure cost. Below roughly
8,000 queries per month, the expected case stops paying back inside a year.

## 7. Cash, or capacity

The benefit is agent capacity. It becomes cash only if one of these is true, and the department has
to say which one it is relying on:

- temporary or outsourced staffing for the helpdesk is reduced at contract renewal, or
- hiring planned for the two peak windows is not done, or
- staff are reassigned to work that is currently not done (callbacks, grievance backlog, proactive
  outreach).

If none of those applies, the honest statement is that the system absorbs peak volume and improves
answer consistency, and the payback figure in this document does not apply. Write that sentence into
the decision note rather than leaving it implied.

## 8. What would falsify the model

| Falsifier | Where it would show up | Consequence |
| --- | --- | --- |
| Measured containment below 0.20 | AC-14 in the pilot | labour claim collapses; the model becomes a quality and consistency case, not a cost case |
| Median handling time actually 3 to 4 minutes, not 9 | baseline timing in week 1 | the pool of avoidable time is roughly half or less of the assumed pool |
| Median time saved below 3 minutes per query | AC-14 | no measurable labour benefit at the assumed wage |
| No process change: agents keep answering the same queries in parallel | observation in week 2 to 3 | d falls toward 0; benefit is capacity only, cash payback is absent |
| Fewer than about 8,000 queries per month | their own ticket counts | payback beyond 12 months on the expected column |
| Provider cost above INR 75 per 1,000 calls, or more than 3.5 calls per query | their gateway invoice, or `/metrics` counters | system cost rises, but labour still dominates; the free-tier throughput ceiling is the likelier binding limit |
| Sustained verification workload above 120 hours per month | the corpus verification log | the maintenance and verification rows understate the run cost by multiples, and the defensibility claim is unfunded |
| Saved time counted by self-report rather than ticket timestamps | measurement design | the benefit number is not auditable and should be rejected by finance |
| Answers routed to a citizen that state an eligibility determination | AC-13 review | the model is void for citizen-facing use regardless of the numbers |
| Provider free tier throttling keeps users on the phone at peak | degraded-answer counts on `/ops/status` during peaks | effective coverage falls exactly when volume is highest, which is when the benefit was claimed |

## 9. How to argue with this model

Replace the inputs in this order, because that is the order in which they change the answer:

1. Q and T, from the ticket system, last 12 months, split by channel and by peak window.
2. C, from payroll or the outsourced contract, including benefits and supervision.
3. r, from the pilot measurement (AC-14), not from a vendor claim.
4. d, from the programme owner, in writing, naming the redeployment or the hiring decision it avoids.
5. Everything else (provider cost, infrastructure, maintenance) is small enough that arguing about it
   changes the payback by days, not months. Argue about it anyway if it makes the model easier to
   sign.
