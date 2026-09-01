# SchemeGPT RAGAS Evaluation Report

- Generated: `2026-09-01T21:50:00+00:00` (UTC)
- Cases evaluated: 8 of 8
- Command: `python -m eval.run_eval --limit 8`
- Threshold: **0.70** - any `faithfulness` or `answer_relevancy` score below this value (or a missing score) is a failure case.
- Judge LLM: Groq (settings.groq_model, free tier); embeddings: local sentence-transformers.

## Aggregate Scores

| Metric | Score |
| --- | --- |
| faithfulness | n/a |
| answer_relevancy | n/a |
| context_precision | n/a |
| context_recall | n/a |

## Delta vs previous run

| Metric | This run | Previous | Delta |
| --- | --- | --- | --- |
| faithfulness | n/a | n/a | n/a |
| answer_relevancy | n/a | n/a | n/a |
| context_precision | n/a | n/a | n/a |
| context_recall | n/a | n/a | n/a |

## Per-Question Scores

| # | Question | faithfulness | answer_relevancy | context_precision | context_recall | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | What health insurance cover does Ayushman Bharat PM-JAY provide per family per year? | n/a | n/a | n/a | n/a | FAIL |
| 2 | When was GST introduced in India and which indirect taxes did it subsume? | n/a | n/a | n/a | n/a | FAIL |
| 3 | What is the GST registration turnover threshold for goods and for services? | n/a | n/a | n/a | n/a | FAIL |
| 4 | How much income support does PM-KISAN provide and in what instalments is it paid? | n/a | n/a | n/a | n/a | FAIL |
| 5 | Who is excluded from receiving PM-KISAN benefits? | n/a | n/a | n/a | n/a | FAIL |
| 6 | What monthly pension does PM-SYM provide and at what age does it start? | n/a | n/a | n/a | n/a | FAIL |
| 7 | How much financial assistance does PMAY-G provide for building a pucca house? | n/a | n/a | n/a | n/a | FAIL |
| 8 | What are the eligibility conditions for DPIIT startup recognition under Startup India? | n/a | n/a | n/a | n/a | FAIL |

## Failure Cases

8 case(s) flagged: score below the threshold or an evaluation error.

### 1. What health insurance cover does Ayushman Bharat PM-JAY provide per family per year?

- **Question**: What health insurance cover does Ayushman Bharat PM-JAY provide per family per year?
- **Reference**: Ayushman Bharat PM-JAY provides a health cover of ₹5 lakh per family per year, on a floater basis, for secondary and tertiary hospitalisation.
- **Answer**:

  ```text
  Ayushman Bharat (PM‑JAY) gives each family a health‑insurance cover of **₹5 lakh per year**.  

> It provides a health cover of ₹5 lakh per family per year for secondary and tertiary hospitalisation. [Ayushman Bharat (PM-JAY), sample_verified]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, answer_relevancy, context_precision, context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-120b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 199911, Requested 1502. Please try again in 10m10.416s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-120b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 199910, Requested 1521. Please try again in 10m18.192s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-120b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 199908, Requested 2223. Please try again in 15m20.592s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-120b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 199903, Requested 2740. Please try again in 19m1.775999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/ayushman-bharat.md:

     ```text
     # Ayushman Bharat (PM-JAY)

Ayushman Bharat Pradhan Mantri Jan Arogya Yojana (PM-JAY) is the largest health
insurance scheme in the world. It provides a health cover of ₹5 lakh per family per
year for secondary and tertiary hospitalisation.

## Source

- **Official source:** https://pmjay.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- Eligibility follows the deprivation criteria of the Socio-Economic Caste
  Census (SECC) 2011; beneficiaries are identified from the SECC 2011 database.
- Rural families living in kutcha houses, or with no adult member aged 16-59,
  qualify for the scheme.
- Urban workers such as rag pickers, rickshaw pullers, and domestic workers
  qualify for the scheme.
     ```
  2. schemes/ayushman-bharat.md:

     ```text
     ## Exclusions

- Not specified in the official source.

## Benefits

- Cover: ₹5 lakh per family per year, on a floater basis.
- Beneficiaries: around 12 crore families (approximately 55 crore individuals),
  covering the bottom 40% of India's population.
- Treatment: hospitalisation, surgeries, and pre/post-hospitalisation expenses.
- Portability: benefits are portable anywhere in India.
- Card: eligible families receive an Ayushman card; treatment is cashless and
  paperless at empanelled hospitals (public and private).

## Documents required

- Not specified in the official source.

## How to apply

- Not specified in the official source.

## Not official advice
     ```
  3. schemes/pmay-g.md:

     ```text
     # PMAY-G (Pradhan Mantri Awas Yojana - Gramin)

Pradhan Mantri Awas Yojana - Gramin (PMAY-G) is a rural housing scheme that provides
financial assistance to eligible rural households for constructing a pucca house
with basic amenities.

## Source

- **Official source:** https://pmayg.nic.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- Eligible households include families living in kutcha houses, houses with zero
  or one room, and families that have no house at all.
- Beneficiary selection is based on housing deprivation parameters from SECC
  2011; selection is finalised through the Awaas+ survey and approved by the
  Gram Sabha.

## Exclusions

- Not specified in the official source.
     ```
  4. schemes/pm-sym.md:

     ```text
     # PM-SYM (Pradhan Mantri Shram Yogi Maandhan)

Pradhan Mantri Shram Yogi Maandhan (PM-SYM) is a pension scheme for unorganised
workers. It provides a monthly pension of ₹3,000 after the subscriber attains the
age of 60 years.

## Source

- **Official source:** https://labour.gov.in/pm-sym
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- Unorganised workers with monthly income up to ₹15,000.
- Entry age: 18 to 40 years.

## Exclusions

- Workers covered under EPFO or ESIC.
- Income tax payers.

## Benefits
     ```

### 2. When was GST introduced in India and which indirect taxes did it subsume?

- **Question**: When was GST introduced in India and which indirect taxes did it subsume?
- **Reference**: GST was introduced in India on 1 July 2017. It subsumed multiple indirect taxes such as VAT, service tax, and excise duty.
- **Answer**:

  ```text
  The Goods and Services Tax (GST) was introduced in India on 1 July 2017 and subsumed multiple indirect taxes such as VAT, service tax, and excise duty. Businesses above the turnover threshold must register: Rs 40 lakh for goods and Rs 20 lakh for services, with lower thresholds in some states. The main tax slabs are 5%, 12%, 18%, and 28%.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 3. What is the GST registration turnover threshold for goods and for services?

- **Question**: What is the GST registration turnover threshold for goods and for services?
- **Reference**: Businesses above the turnover threshold must register for GST: ₹40 lakh for goods and ₹20 lakh for services, with lower thresholds in some states.
- **Answer**:

  ```text
  The Goods and Services Tax (GST) was introduced in India on 1 July 2017 and subsumed multiple indirect taxes such as VAT, service tax, and excise duty. Businesses above the turnover threshold must register: Rs 40 lakh for goods and Rs 20 lakh for services, with lower thresholds in some states. The main tax slabs are 5%, 12%, 18%, and 28%.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 4. How much income support does PM-KISAN provide and in what instalments is it paid?

- **Question**: How much income support does PM-KISAN provide and in what instalments is it paid?
- **Reference**: PM-KISAN provides ₹6,000 per year to eligible landholding farmer families, paid directly into their bank accounts through Direct Benefit Transfer (DBT) in three equal instalments of ₹2,000 each, released every four months.
- **Answer**:

  ```text
  PM-KISAN (Pradhan Mantri Kisan Samman Nidhi) is a central sector scheme that provides income support of Rs 6,000 per year to eligible landholding farmer families in India. The amount is paid directly into the beneficiary's bank account through Direct Benefit Transfer (DBT) in three equal instalments of Rs 2,000 each, released every four months.

> eligible farmers receive Rs 6,000 per year, paid directly into their bank accounts through Direct Benefit Transfer (DBT). [schemes/pm-kisan.md, sample_verified]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 5. Who is excluded from receiving PM-KISAN benefits?

- **Question**: Who is excluded from receiving PM-KISAN benefits?
- **Reference**: Excluded from PM-KISAN are institutional landholders, farmer families where any member pays income tax, and families with a government employee in a higher grade.
- **Answer**:

  ```text
  Excluded from PM-KISAN are institutional landholders, farmer families where any member pays income tax, and families with a government employee in a higher grade. Duplicate or ineligible beneficiaries are also removed through periodic verification drives.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 6. What monthly pension does PM-SYM provide and at what age does it start?

- **Question**: What monthly pension does PM-SYM provide and at what age does it start?
- **Reference**: PM-SYM provides a monthly pension of ₹3,000 after the subscriber attains the age of 60 years; the entry age is 18 to 40 years.
- **Answer**:

  ```text
  Pradhan Mantri Shram Yogi Maandhan (PM-SYM) provides a monthly pension of Rs 3,000 after the subscriber attains the age of 60 years. The entry age is 18 to 40 years, contributions range from Rs 55 to Rs 200 per month, and the central government makes an equal matching contribution. Eligible workers are unorganised workers with monthly income up to Rs 15,000.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 7. How much financial assistance does PMAY-G provide for building a pucca house?

- **Question**: How much financial assistance does PMAY-G provide for building a pucca house?
- **Reference**: PMAY-G provides financial assistance of ₹1.20 lakh per house in plain areas and ₹1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
- **Answer**:

  ```text
  Pradhan Mantri Awas Yojana - Gramin (PMAY-G) provides financial assistance of Rs 1.20 lakh per house in plain areas and Rs 1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts for constructing a pucca house with basic amenities. Funding is shared between the central and state governments (60:40 in plain areas).
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 8. What are the eligibility conditions for DPIIT startup recognition under Startup India?

- **Question**: What are the eligibility conditions for DPIIT startup recognition under Startup India?
- **Reference**: An entity must be incorporated as a private limited company, LLP, or registered partnership, be less than 10 years old, and have a turnover of up to ₹100 crore in any financial year.
- **Answer**:

  ```text
  Under Startup India, an entity is eligible for DPIIT recognition if it is incorporated as a private limited company, LLP, or registered partnership, is less than 10 years old, and has a turnover of up to Rs 100 crore in any financial year. Recognised startups get a 100% income tax exemption on profits for 3 consecutive financial years out of the first 10 years and are exempt from angel tax.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

## Notes

- The threshold of **0.70** is a project triage threshold, not a universal quality claim.
- RAGAS evaluation consumes Groq free-tier quota; `--limit N` provides cheap/free partial runs.
- Per-case scores are also available in `scores.json`.
