# SchemeGPT RAGAS Evaluation Report

- Generated: `2026-09-01T20:08:58+00:00` (UTC)
- Cases evaluated: 20 of 20
- Command: `python -m eval.run_eval`
- Threshold: **0.70** - any `faithfulness` or `answer_relevancy` score below this value (or a missing score) is a failure case.
- Judge LLM: Groq (settings.groq_model, free tier); embeddings: local sentence-transformers.

## Aggregate Scores

| Metric | Score |
| --- | --- |
| faithfulness | 0.667 |
| answer_relevancy | 0.842 |
| context_precision | 0.698 |
| context_recall | 0.600 |

## Delta vs previous run

| Metric | This run | Previous | Delta |
| --- | --- | --- | --- |
| faithfulness | 0.667 | n/a | n/a |
| answer_relevancy | 0.842 | n/a | n/a |
| context_precision | 0.698 | 0.000 | +0.698 |
| context_recall | 0.600 | n/a | n/a |

## Per-Question Scores

| # | Question | faithfulness | answer_relevancy | context_precision | context_recall | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | What health insurance cover does Ayushman Bharat PM-JAY provide per family per year? | 1.000 | 0.934 | 1.000 | n/a | FAIL |
| 2 | When was GST introduced in India and which indirect taxes did it subsume? | n/a | 0.887 | 1.000 | 1.000 | FAIL |
| 3 | What is the GST registration turnover threshold for goods and for services? | n/a | 0.936 | 1.000 | n/a | FAIL |
| 4 | How much income support does PM-KISAN provide and in what instalments is it paid? | 0.000 | 0.896 | 0.000 | 0.000 | FAIL |
| 5 | Who is excluded from receiving PM-KISAN benefits? | n/a | 0.919 | 1.000 | n/a | FAIL |
| 6 | What monthly pension does PM-SYM provide and at what age does it start? | n/a | 0.862 | 0.833 | n/a | FAIL |
| 7 | How much financial assistance does PMAY-G provide for building a pucca house? | n/a | 0.883 | 0.500 | n/a | FAIL |
| 8 | What are the eligibility conditions for DPIIT startup recognition under Startup India? | n/a | 0.953 | 0.500 | 1.000 | FAIL |
| 9 | What is the current exchange rate of Bitcoin to the Indian rupee? | n/a | n/a | 0.333 | 0.000 | FAIL |
| 10 | Which jurisdictions does the SchemeGPT directory cover, and what does a state or union territory entry tell a citizen? | n/a | 0.907 | n/a | n/a | FAIL |
| 11 | I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile? | n/a | 0.938 | 0.417 | n/a | FAIL |
| 12 | पीएम-किसान के तहत पात्र किसान परिवारों को प्रति वर्ष कितनी आय सहायता मिलती है और यह कितनी किश्तों में दी जाती है? | 1.000 | 0.803 | n/a | 1.000 | FAIL |
| 13 | pm kisan ka paisa kab aata hai | n/a | 0.862 | 1.000 | n/a | FAIL |
| 14 | kisan ko sarkar har saal kitne rupaye deti hai | 0.000 | 0.000 | 0.000 | n/a | FAIL |
| 15 | mera pension banao kaun sa scheme chune | n/a | 0.832 | 1.000 | n/a | FAIL |
| 16 | पीएम-श्रम योगी मानधन योजना कितनी पेंशन देती है और किस उम्र में शुरू होती है? | 1.000 | 0.839 | 1.000 | n/a | FAIL |
| 17 | Compare PM-KISAN and PM-SYM for a 40-year-old landless farm labourer. | n/a | 0.895 | 0.583 | n/a | FAIL |
| 18 | A 55-year-old wants a scheme; should they consider PM-KISAN or PM-SYM? | n/a | 0.918 | 1.000 | n/a | FAIL |
| 19 | What does the scheme document say verbatim about PMAY-G assistance amounts? | 1.000 | 0.900 | n/a | n/a | FAIL |
| 20 | Which scheme directory entry covers Sikkim and what does it link to? | n/a | n/a | n/a | n/a | FAIL |

## Failure Cases

20 case(s) flagged: score below the threshold or an evaluation error.

### 1. What health insurance cover does Ayushman Bharat PM-JAY provide per family per year?

- **Question**: What health insurance cover does Ayushman Bharat PM-JAY provide per family per year?
- **Reference**: Ayushman Bharat PM-JAY provides a health cover of ₹5 lakh per family per year, on a floater basis, for secondary and tertiary hospitalisation.
- **Answer**:

  ```text
  > Cover: ₹5 lakh per family per year. [Ayushman Bharat (PM‑JAY), sample_verified]
  ```

- **faithfulness**: 1.000
- **answer_relevancy**: 0.934
- **Error**: evaluation error: RAGAS did not return a score for context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6731, Requested 2740. Please try again in 11.0325s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

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
  GST was rolled out in India on 1 July 2017. It replaced a bunch of older indirect taxes – mainly VAT, service tax and excise duty.  

> The Goods and Services Tax (GST) … introduced in India on 1 July 2017. It subsumed multiple indirect taxes such as VAT, service tax, and excise duty. [GST Act, sample_verified]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.887
- **Error**: evaluation error: RAGAS did not return a score for faithfulness; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.)

- **Retrieved sources/contexts**:
  1. schemes/gst.md:

     ```text
     # Goods and Services Tax (GST) Act

The Goods and Services Tax (GST) is a comprehensive, multi-stage, destination-based
tax levied on every value addition, introduced in India on 1 July 2017. It subsumed
multiple indirect taxes such as VAT, service tax, and excise duty.

## Source

- **Official source:** https://www.gst.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- Businesses above the turnover threshold must register (₹40 lakh for goods and
  ₹20 lakh for services, with lower thresholds in some states).
- Small taxpayers with turnover up to ₹1.5 crore (₹75 lakh for services in some
  cases) can opt for the composition scheme.

## Exclusions

- Not specified in the official source.
     ```
  2. schemes/gst.md:

     ```text
     ## Exclusions

- Not specified in the official source.

## Benefits

- Structure: dual GST is levied by the Centre (CGST) and States (SGST);
  inter-state supplies attract Integrated GST (IGST).
- Slabs: the main tax slabs are 5%, 12%, 18%, and 28%. Some goods are exempt,
  and a compensation cess applies to demerit goods.
- GST Council: a constitutional body chaired by the Union Finance Minister that
  decides rates and rules.
- Input Tax Credit (ITC): credit of tax paid on inputs can be set off against
  output tax liability.
- Composition scheme: small taxpayers can pay a lower rate with limited
  compliance.
- Returns: registered taxpayers file returns such as GSTR-1 (outward supplies),
  GSTR-3B (summary), and the annual return GSTR-9 through the GST portal or
  offline tools.
     ```
  3. states/gujarat.md:

     ```text
     # Gujarat

**Type:** State
**Code:** GJ
**Region:** West
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Gujarat. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Gujarat has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Gujarat on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  4. states/gujarat.md:

     ```text
     - MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore

- income support
- health
- education
- housing
- jobs
- agriculture
- social security

## Verification note

This record has `data_status: directory_seed`. It is a discovery/coverage seed,
not a verified eligibility decision. Before applying, always verify scheme-level
eligibility for Gujarat against the official national MyScheme discovery portal
and the issuing department.
     ```

### 3. What is the GST registration turnover threshold for goods and for services?

- **Question**: What is the GST registration turnover threshold for goods and for services?
- **Reference**: Businesses above the turnover threshold must register for GST: ₹40 lakh for goods and ₹20 lakh for services, with lower thresholds in some states.
- **Answer**:

  ```text
  The GST registration turnover threshold is **₹40 lakh for goods** and **₹20 lakh for services** (states may have lower limits).  

> Businesses above the turnover threshold must register (₹40 lakh for goods and ₹20 lakh for services, with lower thresholds in some states). [Goods and Services Tax (GST) Act, sample_verified]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.936
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6511, Requested 2666. Please try again in 8.8275s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/gst.md:

     ```text
     # Goods and Services Tax (GST) Act

The Goods and Services Tax (GST) is a comprehensive, multi-stage, destination-based
tax levied on every value addition, introduced in India on 1 July 2017. It subsumed
multiple indirect taxes such as VAT, service tax, and excise duty.

## Source

- **Official source:** https://www.gst.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- Businesses above the turnover threshold must register (₹40 lakh for goods and
  ₹20 lakh for services, with lower thresholds in some states).
- Small taxpayers with turnover up to ₹1.5 crore (₹75 lakh for services in some
  cases) can opt for the composition scheme.

## Exclusions

- Not specified in the official source.
     ```
  2. schemes/gst.md:

     ```text
     ## Exclusions

- Not specified in the official source.

## Benefits

- Structure: dual GST is levied by the Centre (CGST) and States (SGST);
  inter-state supplies attract Integrated GST (IGST).
- Slabs: the main tax slabs are 5%, 12%, 18%, and 28%. Some goods are exempt,
  and a compensation cess applies to demerit goods.
- GST Council: a constitutional body chaired by the Union Finance Minister that
  decides rates and rules.
- Input Tax Credit (ITC): credit of tax paid on inputs can be set off against
  output tax liability.
- Composition scheme: small taxpayers can pay a lower rate with limited
  compliance.
- Returns: registered taxpayers file returns such as GSTR-1 (outward supplies),
  GSTR-3B (summary), and the annual return GSTR-9 through the GST portal or
  offline tools.
     ```
  3. schemes/gst.md:

     ```text
     ## Documents required

- Not specified in the official source.

## How to apply

- Not specified in the official source (the record states that businesses above
  the turnover threshold must register, but does not describe the application
  process).

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```
  4. states/gujarat.md:

     ```text
     # Gujarat

**Type:** State
**Code:** GJ
**Region:** West
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Gujarat. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Gujarat has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Gujarat on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```

### 4. How much income support does PM-KISAN provide and in what instalments is it paid?

- **Question**: How much income support does PM-KISAN provide and in what instalments is it paid?
- **Reference**: PM-KISAN provides ₹6,000 per year to eligible landholding farmer families, paid directly into their bank accounts through Direct Benefit Transfer (DBT) in three equal instalments of ₹2,000 each, released every four months.
- **Answer**:

  ```text
  PM-KISAN pays Rs 6000 per year.
  ```

- **faithfulness**: 0.000
- **answer_relevancy**: 0.896

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 5. Who is excluded from receiving PM-KISAN benefits?

- **Question**: Who is excluded from receiving PM-KISAN benefits?
- **Reference**: Excluded from PM-KISAN are institutional landholders, farmer families where any member pays income tax, and families with a government employee in a higher grade.
- **Answer**:

  ```text
  The following people or families are excluded from getting PM‑KISAN benefits:

> Institutional landholders.  
> Farmer families where any member pays income tax.  
> Families with a government employee in a higher grade.  
> Duplicate or ineligible beneficiaries are removed through periodic verification drives.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.919
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6774, Requested 2617. Please try again in 10.4325s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6727, Requested 2523. Please try again in 9.375s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  2. schemes/pm-kisan.md:

     ```text
     ## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```
  3. schemes/pm-kisan.md:

     ```text
     ## Benefits

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- The scheme was launched in February 2019.
- As of the 2024-25 financial year, over 11 crore farmer families have received
  support.

## Documents required

- Aadhaar.
- Bank account details.
- Land records.
- Farmers must keep their Aadhaar linked to their bank account to continue
  receiving instalments.

## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice
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

### 6. What monthly pension does PM-SYM provide and at what age does it start?

- **Question**: What monthly pension does PM-SYM provide and at what age does it start?
- **Reference**: PM-SYM provides a monthly pension of ₹3,000 after the subscriber attains the age of 60 years; the entry age is 18 to 40 years.
- **Answer**:

  ```text
  It gives a monthly pension of ₹3,000, and the payment starts once the subscriber turns 60 years old.  
> Pradhan Mantri Shram Yogi Maandhan (PM‑SYM) is a pension scheme for unorganised workers. It provides a monthly pension of ₹3,000 after the subscriber attains the age of 60 years. [context, sample_verified]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.862
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6005, Requested 2658. Please try again in 4.9725s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-sym.md:

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
  2. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  3. schemes/pm-sym.md:

     ```text
     ## Exclusions

- Workers covered under EPFO or ESIC.
- Income tax payers.

## Benefits

- Pension: ₹3,000 per month after age 60.
- Contribution: ₹55 to ₹200 per month, depending on the entry age; the central
  government makes an equal matching contribution.
- The subscriber contributes a fixed monthly amount until age 60, and the
  central government contributes an equal amount; after 60, the subscriber
  receives ₹3,000 per month.
- On exit before age 60, the accumulated corpus plus interest is paid back,
  subject to conditions.
- On the subscriber's death, the spouse receives 50% of the pension as family
  pension.

## Documents required

- Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice
     ```
  4. schemes/pmay-g.md:

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

### 7. How much financial assistance does PMAY-G provide for building a pucca house?

- **Question**: How much financial assistance does PMAY-G provide for building a pucca house?
- **Reference**: PMAY-G provides financial assistance of ₹1.20 lakh per house in plain areas and ₹1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
- **Answer**:

  ```text
  PMAY‑G gives ₹1.20 लाख per house in plain areas and ₹1.30 लाख in hilly, difficult areas and Integrated Action Plan (IAP) districts.  
> Financial assistance: ₹1.20 lakh per house in plain areas and ₹1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts. [schemes/pmay-g.md, sample_verified]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.883
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 7734, Requested 2662. Please try again in 17.97s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pmay-g.md:

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
  2. schemes/pmay-g.md:

     ```text
     ## Exclusions

- Not specified in the official source.

## Benefits

- Financial assistance: ₹1.20 lakh per house in plain areas and ₹1.30 lakh in
  hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
- Target: construction of around 2.95 crore houses (original target until 2024).
- Toilet: assistance for toilet construction is available under Swachh Bharat
  Mission - Gramin (SBM-G).
- MGNREGA convergence: 90 person-days of unskilled wage employment per house.
- Funding: shared between the central and state governments, 60:40 in plain
  areas and 90:10 in North-Eastern and hilly states.

## Documents required

- Not specified in the official source.

## How to apply

- Not specified in the official source.

## Not official advice
     ```
  3. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  4. schemes/ayushman-bharat.md:

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

### 8. What are the eligibility conditions for DPIIT startup recognition under Startup India?

- **Question**: What are the eligibility conditions for DPIIT startup recognition under Startup India?
- **Reference**: An entity must be incorporated as a private limited company, LLP, or registered partnership, be less than 10 years old, and have a turnover of up to ₹100 crore in any financial year.
- **Answer**:

  ```text
  The DPIIT startup recognition under Startup India requires:

> - The entity must be incorporated as a private limited company, LLP, or registered partnership.  
> - It must be less than 10 years old.  
> - It must have a turnover up to ₹100 crore in any financial year.  

These are the eligibility conditions listed in the official source.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.953
- **Error**: evaluation error: RAGAS did not return a score for faithfulness; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.)

- **Retrieved sources/contexts**:
  1. schemes/startup-india.md:

     ```text
     ## Documents required

- Not specified in the official source.

## How to apply

1. Apply online: startups are recognised by the Department for Promotion of
   Industry and Internal Trade (DPIIT) after an online application.

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```
  2. schemes/startup-india.md:

     ```text
     # Startup India

Startup India is a flagship initiative of the Government of India to build a strong
ecosystem for innovation and startups. It offers recognition, tax benefits, and
simplified compliance to eligible startups.

## Source

- **Official source:** https://www.startupindia.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- The entity must be incorporated as a private limited company, LLP, or
  registered partnership.
- It must be less than 10 years old.
- It must have a turnover up to ₹100 crore in any financial year.

## Exclusions

- Not specified in the official source.

## Benefits
     ```
  3. schemes/startup-india.md:

     ```text
     ## Exclusions

- Not specified in the official source.

## Benefits

- Tax exemption: a 100% income tax exemption on profits for 3 consecutive
  financial years out of the first 10 years.
- Angel tax: recognised startups are exempt from angel tax under Section
  56(2)(viib) of the Income Tax Act.
- Fund of Funds: a Fund of Funds for Startups (FFS) of ₹10,000 crore, managed
  by SIDBI.
- Self-certification: startups can self-certify compliance with 9 labour and 3
  environmental laws.
- Recognised startups get fast-track patent examination, easier access to
  public procurement, and tax holidays.
- The Startup India Seed Fund Scheme (SISFS) provides financial assistance for
  proof of concept, prototype development, and market entry.

## Documents required
     ```
  4. schemes/pm-sym.md:

     ```text
     - Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```

### 9. What is the current exchange rate of Bitcoin to the Indian rupee?

- **Question**: What is the current exchange rate of Bitcoin to the Indian rupee?
- **Reference**: This question is out of scope for SchemeGPT: the provided context contains no information about cryptocurrency exchange rates, so the answer should state that the information is not available.
- **Answer**:

  ```text
  I’m sorry, but that information isn’t in the context provided.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, answer_relevancy; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6757, Requested 2588. Please try again in 10.0875s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pmay-g.md:

     ```text
     ## Exclusions

- Not specified in the official source.

## Benefits

- Financial assistance: ₹1.20 lakh per house in plain areas and ₹1.30 lakh in
  hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
- Target: construction of around 2.95 crore houses (original target until 2024).
- Toilet: assistance for toilet construction is available under Swachh Bharat
  Mission - Gramin (SBM-G).
- MGNREGA convergence: 90 person-days of unskilled wage employment per house.
- Funding: shared between the central and state governments, 60:40 in plain
  areas and 90:10 in North-Eastern and hilly states.

## Documents required

- Not specified in the official source.

## How to apply

- Not specified in the official source.

## Not official advice
     ```
  2. schemes/pm-sym.md:

     ```text
     - Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```
  3. states/bihar.md:

     ```text
     # Bihar

**Type:** State
**Code:** BR
**Region:** East
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Bihar. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Bihar has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Bihar on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  4. schemes/pm-sym.md:

     ```text
     ## Exclusions

- Workers covered under EPFO or ESIC.
- Income tax payers.

## Benefits

- Pension: ₹3,000 per month after age 60.
- Contribution: ₹55 to ₹200 per month, depending on the entry age; the central
  government makes an equal matching contribution.
- The subscriber contributes a fixed monthly amount until age 60, and the
  central government contributes an equal amount; after 60, the subscriber
  receives ₹3,000 per month.
- On exit before age 60, the accumulated corpus plus interest is paid back,
  subject to conditions.
- On the subscriber's death, the spouse receives 50% of the pension as family
  pension.

## Documents required

- Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice
     ```

### 10. Which jurisdictions does the SchemeGPT directory cover, and what does a state or union territory entry tell a citizen?

- **Question**: Which jurisdictions does the SchemeGPT directory cover, and what does a state or union territory entry tell a citizen?
- **Reference**: The SchemeGPT directory covers 36 jurisdictions: 28 states and 8 union territories. Each state/UT entry is a directory_seed discovery entry: it maps the jurisdiction for scheme search and links to the official national MyScheme discovery portal, but it is not a verified scheme-level eligibility decision.
- **Answer**:

  ```text
  SchemeGPT covers the Union Territories that are listed as “directory seed” entries – for example Puducherry, Andaman and Nicobar Islands, Ladakh and Jammu and Kashmir.  

Each entry is basically a **discovery/coverage record** that tells you two things:

1. **Coverage** – SchemeGPT can look up any nationwide central‑government scheme for that jurisdiction.  
2. **What’s NOT verified yet** – The portal does **not** claim any specific state‑level scheme names, benefit amounts or eligibility decisions for that UT; you’ll need to check the official MyScheme portal for the exact details.

> This is a discovery/coverage directory seed for Puducherry. It confirms that SchemeGPT covers this jurisdiction for nationwide scheme search and points citizens to the official national discovery portal. Scheme-level eligibility for Puducherry has not been individually verified yet, and no state scheme names, benefit amounts, or eligibility decisions are claimed here. [Puducherry, directory_seed]

The same wording appears for the other Union Territories (Andaman and Nicobar Islands, Ladakh, Jammu and Kashmir). So, when you see a state or UT entry, it’s basically saying: “We can search for schemes that apply here, but you should go to the MyScheme portal (https://www.myscheme.gov.in/) for the final, verified eligibility and benefit details.”
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.907
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_precision, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6595, Requested 2703. Please try again in 9.735s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. states/puducherry.md:

     ```text
     # Puducherry

**Type:** Union Territory
**Code:** PY
**Region:** South
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Puducherry. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Puducherry has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Puducherry on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  2. states/andaman-and-nicobar-islands.md:

     ```text
     # Andaman and Nicobar Islands

**Type:** Union Territory
**Code:** AN
**Region:** South
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Andaman and Nicobar Islands. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Andaman and Nicobar Islands has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Andaman and Nicobar Islands on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/
     ```
  3. states/ladakh.md:

     ```text
     # Ladakh

**Type:** Union Territory
**Code:** LA
**Region:** North
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Ladakh. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Ladakh has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Ladakh on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  4. states/jammu-and-kashmir.md:

     ```text
     # Jammu and Kashmir

**Type:** Union Territory
**Code:** JK
**Region:** North
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Jammu and Kashmir. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Jammu and Kashmir has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Jammu and Kashmir on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```

### 11. I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile?

- **Question**: I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile?
- **Reference**: PM-SYM (Pradhan Mantri Shram Yogi Maandhan) is a pension scheme for unorganised workers with monthly income up to Rs 15,000 and an entry age of 18 to 40 years; a 35-year-old unorganised worker earning about Rs 12,000 per month is within the documented entry age and income band. The Karnataka directory seed is a discovery entry, not a verified eligibility decision.
- **Answer**:

  ```text
  आपकी प्रोफ़ाइल (35 वर्ष, अनऑर्गेनाइज़्ड वर्कर, ₹12,000/माह, ग्रामीण कर्नाटक) के लिए सबसे उपयुक्त केंद्रीय पेंशन योजना **PM‑SYM (Pradhan Mantri Shram Yogi Maandhan)** है।  

> Pradhan Mantri Shram Yogi Maandhan (PM‑SYM) is a pension scheme for unorganised workers. It provides a monthly pension of ₹3,000 after the subscriber attains the age of 60 years. [labour.gov.in/pm-sym, sample_verified]  

> Eligibility: Unorganised workers with monthly income up to ₹15,000. Entry age: 18 to 40 years. [labour.gov.in/pm-sym, sample_verified]  

आपकी आय ₹12,000/माह (₹144,000/वर्ष) और उम्र 35 वर्ष दोनों ही इन मानदंडों में फिट होते हैं, इसलिए आप इस योजना के लिए पात्र हो सकते हैं।  

**आवश्यक दस्तावेज़**  
- आधार कार्ड  
- जेनरल डिपॉज़िट खाता (जैसे जेन डैश)  

**कैसे आवेदन करें**  
- आधिकारिक वेबसाइट https://labour.gov.in/pm-sym पर जाएँ और “Apply” या “Register” विकल्प चुनें।  
- यदि ऑनलाइन फ़ॉर्म उपलब्ध नहीं है, तो नजदीकी श्रम कार्यालय या जेन डैश शाखा में जाकर कागजी आवेदन जमा कर सकते हैं।  

**ध्यान दें**  
- यह जानकारी “sample_verified” है, परंतु कर्नाटक में आपकी व्यक्तिगत पात्रता की पुष्टि के लिए **MyScheme** (https://www.myscheme.gov.in/) पर जाकर या संबंधित राज्य/केंद्र विभाग से संपर्क करके अंतिम सत्यापन कर लें।  

इस योजना के तहत, 60 वर्ष की आयु के बाद आपको ₹3,000/माह पेंशन मिलेगी, और यदि आप 60 वर्ष से पहले बाहर निकलते हैं तो जमा राशि व ब्याज वापस मिल सकता है।  

आपकी प्रोफ़ाइल के अनुसार यह योजना आपके लिए उपयुक्त है, परंतु आवेदन से पहले ऊपर बताए गए सत्यापन चरणों को पूरा करना ज़रूरी है।
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.938
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6362, Requested 2704. Please try again in 7.995s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. states/karnataka.md:

     ```text
     - MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore

- income support
- health
- education
- housing
- jobs
- agriculture
- social security

## Verification note

This record has `data_status: directory_seed`. It is a discovery/coverage seed,
not a verified eligibility decision. Before applying, always verify scheme-level
eligibility for Karnataka against the official national MyScheme discovery portal
and the issuing department.
     ```
  2. states/karnataka.md:

     ```text
     # Karnataka

**Type:** State
**Code:** KA
**Region:** South
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Karnataka. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Karnataka has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Karnataka on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  3. schemes/pm-sym.md:

     ```text
     ## Exclusions

- Workers covered under EPFO or ESIC.
- Income tax payers.

## Benefits

- Pension: ₹3,000 per month after age 60.
- Contribution: ₹55 to ₹200 per month, depending on the entry age; the central
  government makes an equal matching contribution.
- The subscriber contributes a fixed monthly amount until age 60, and the
  central government contributes an equal amount; after 60, the subscriber
  receives ₹3,000 per month.
- On exit before age 60, the accumulated corpus plus interest is paid back,
  subject to conditions.
- On the subscriber's death, the spouse receives 50% of the pension as family
  pension.

## Documents required

- Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice
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

### 12. पीएम-किसान के तहत पात्र किसान परिवारों को प्रति वर्ष कितनी आय सहायता मिलती है और यह कितनी किश्तों में दी जाती है?

- **Question**: पीएम-किसान के तहत पात्र किसान परिवारों को प्रति वर्ष कितनी आय सहायता मिलती है और यह कितनी किश्तों में दी जाती है?
- **Reference**: पीएम-किसान के तहत पात्र भूमिधारी किसान परिवारों को प्रति वर्ष ₹6,000 की आय सहायता मिलती है, जो डीबीटी द्वारा सीधे उनके बैंक खाते में ₹2,000 की तीन समान किश्तों में दी जाती है, और हर चार महीने में एक किश्त जारी की जाती है।
- **Answer**:

  ```text
  > भुगतान: ₹6,000 प्रति वर्ष, तीन समान किश्तों में ₹2,000 प्रत्येक। [schemes/pm-kisan.md, sample_verified]
  ```

- **faithfulness**: 1.000
- **answer_relevancy**: 0.803
- **Error**: evaluation error: RAGAS did not return a score for context_precision; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 7799, Requested 2251. Please try again in 15.374999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  2. schemes/pm-kisan.md:

     ```text
     ## Benefits

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- The scheme was launched in February 2019.
- As of the 2024-25 financial year, over 11 crore farmer families have received
  support.

## Documents required

- Aadhaar.
- Bank account details.
- Land records.
- Farmers must keep their Aadhaar linked to their bank account to continue
  receiving instalments.

## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice
     ```
  3. schemes/ayushman-bharat.md:

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
  4. schemes/pmay-g.md:

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

### 13. pm kisan ka paisa kab aata hai

- **Question**: pm kisan ka paisa kab aata hai
- **Reference**: PM-KISAN income support of Rs 6,000 per year is released in three equal instalments of Rs 2,000 each, every four months, by Direct Benefit Transfer (DBT).
- **Answer**:

  ```text
  PM‑KISAN का पैसा साल में ₹6,000 मिलता है, जो तीन बराबर किस्तों में बाँटा जाता है। हर किस्त ₹2,000 की होती है और **हर चार महीने में एक‑एक instalment रिलीज़ होता है**।  

> Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each. Frequency: instalments are released every four months. [PM‑KISAN (Pradhan Mantri Kisan Samman Nidhi), sample_verified]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.862
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6509, Requested 2737. Please try again in 9.345s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  2. schemes/pm-kisan.md:

     ```text
     ## Benefits

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- The scheme was launched in February 2019.
- As of the 2024-25 financial year, over 11 crore farmer families have received
  support.

## Documents required

- Aadhaar.
- Bank account details.
- Land records.
- Farmers must keep their Aadhaar linked to their bank account to continue
  receiving instalments.

## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

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
  4. schemes/ayushman-bharat.md:

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

### 14. kisan ko sarkar har saal kitne rupaye deti hai

- **Question**: kisan ko sarkar har saal kitne rupaye deti hai
- **Reference**: PM-KISAN provides income support of Rs 6,000 per year to eligible landholding farmer families in India, paid directly into their bank accounts through Direct Benefit Transfer (DBT).
- **Answer**:

  ```text
  मुझे इस विषय पर जानकारी नहीं है।
  ```

- **faithfulness**: 0.000
- **answer_relevancy**: 0.000
- **Error**: evaluation error: RAGAS did not return a score for context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 7023, Requested 2696. Please try again in 12.8925s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. states/kerala.md:

     ```text
     # Kerala

**Type:** State
**Code:** KL
**Region:** South
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Kerala. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Kerala has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Kerala on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  2. states/karnataka.md:

     ```text
     # Karnataka

**Type:** State
**Code:** KA
**Region:** South
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Karnataka. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Karnataka has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Karnataka on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  3. states/sikkim.md:

     ```text
     # Sikkim

**Type:** State
**Code:** SK
**Region:** Northeast
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Sikkim. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Sikkim has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Sikkim on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  4. schemes/ayushman-bharat.md:

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

### 15. mera pension banao kaun sa scheme chune

- **Question**: mera pension banao kaun sa scheme chune
- **Reference**: PM-SYM (Pradhan Mantri Shram Yogi Maandhan) is a pension scheme for unorganised workers with monthly income up to Rs 15,000 and an entry age of 18 to 40 years; it provides a monthly pension of Rs 3,000 after the subscriber attains the age of 60 years.
- **Answer**:

  ```text
  अगर आप अनऑर्गेनाइज़्ड वर्कर हैं और आपकी मासिक आय ₹15,000 से कम है, तो **PM‑SYM (Pradhan Mantri Shram Yogi Maandhan)** आपके लिए सही विकल्प है।  

> "Unorganised workers with monthly income up to ₹15,000." [schemes/pm-sym.md, sample_verified]  
> "Entry age: 18 to 40 years." [schemes/pm-sym.md, sample_verified]  
> "Pension: ₹3,000 per month after age 60." [schemes/pm-sym.md, sample_verified]  
> "Contribution: ₹55 to ₹200 per month, depending on the entry age; the central government makes an equal matching contribution." [schemes/pm-sym.md, sample_verified]  

PM‑KISAN तो किसान परिवारों के लिए है और यह पेंशन नहीं देता, इसलिए यदि आप पेंशन चाहते हैं तो PM‑SYM चुनें।  

**ध्यान दें:**  
- EPFO/ESIC या आयकरदाता नहीं होना चाहिए।  
- आवेदन ऑनलाइन PM‑KISAN पोर्टल या CSC के माध्यम से कर सकते हैं (PM‑SYM के लिए भी यही प्रक्रिया है)।  

इस योजना के लिए आपको अपना आधार, बैंक खाता और ज़मीन के दस्तावेज़ तैयार रखने होंगे। यदि आप इन शर्तों पर खरे उतरते हैं, तो 60 वर्ष की उम्र के बाद आपको ₹3,000 प्रति माह पेंशन मिल जाएगी।
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.832
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6717, Requested 2733. Please try again in 10.875s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-sym.md:

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
  2. schemes/pm-kisan.md:

     ```text
     ## Benefits

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- The scheme was launched in February 2019.
- As of the 2024-25 financial year, over 11 crore farmer families have received
  support.

## Documents required

- Aadhaar.
- Bank account details.
- Land records.
- Farmers must keep their Aadhaar linked to their bank account to continue
  receiving instalments.

## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice
     ```
  3. schemes/pm-sym.md:

     ```text
     ## Exclusions

- Workers covered under EPFO or ESIC.
- Income tax payers.

## Benefits

- Pension: ₹3,000 per month after age 60.
- Contribution: ₹55 to ₹200 per month, depending on the entry age; the central
  government makes an equal matching contribution.
- The subscriber contributes a fixed monthly amount until age 60, and the
  central government contributes an equal amount; after 60, the subscriber
  receives ₹3,000 per month.
- On exit before age 60, the accumulated corpus plus interest is paid back,
  subject to conditions.
- On the subscriber's death, the spouse receives 50% of the pension as family
  pension.

## Documents required

- Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice
     ```
  4. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```

### 16. पीएम-श्रम योगी मानधन योजना कितनी पेंशन देती है और किस उम्र में शुरू होती है?

- **Question**: पीएम-श्रम योगी मानधन योजना कितनी पेंशन देती है और किस उम्र में शुरू होती है?
- **Reference**: पीएम-श्रम योगी मानधन (पीएम-एसवाईएम) असंगठित क्षेत्र के श्रमिकों के लिए पेंशन योजना है, जो अभिदाता के 60 वर्ष की आयु पूरी करने पर ₹3,000 मासिक पेंशन देती है; प्रवेश आयु 18 से 40 वर्ष है।
- **Answer**:

  ```text
  > Pension: ₹3,000 per month after age 60. [schemes/pm-sym.md, sample_verified]
  ```

- **faithfulness**: 1.000
- **answer_relevancy**: 0.839
- **Error**: evaluation error: RAGAS did not return a score for context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6367, Requested 2773. Please try again in 8.549999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-sym.md:

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
  2. schemes/pm-sym.md:

     ```text
     ## Exclusions

- Workers covered under EPFO or ESIC.
- Income tax payers.

## Benefits

- Pension: ₹3,000 per month after age 60.
- Contribution: ₹55 to ₹200 per month, depending on the entry age; the central
  government makes an equal matching contribution.
- The subscriber contributes a fixed monthly amount until age 60, and the
  central government contributes an equal amount; after 60, the subscriber
  receives ₹3,000 per month.
- On exit before age 60, the accumulated corpus plus interest is paid back,
  subject to conditions.
- On the subscriber's death, the spouse receives 50% of the pension as family
  pension.

## Documents required

- Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice
     ```
  3. schemes/ayushman-bharat.md:

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
  4. schemes/pm-kisan.md:

     ```text
     ## Benefits

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- The scheme was launched in February 2019.
- As of the 2024-25 financial year, over 11 crore farmer families have received
  support.

## Documents required

- Aadhaar.
- Bank account details.
- Land records.
- Farmers must keep their Aadhaar linked to their bank account to continue
  receiving instalments.

## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice
     ```

### 17. Compare PM-KISAN and PM-SYM for a 40-year-old landless farm labourer.

- **Question**: Compare PM-KISAN and PM-SYM for a 40-year-old landless farm labourer.
- **Reference**: PM-KISAN provides income support to landholding farmer families (Rs 6,000 per year via DBT), so a landless labourer does not qualify for it; PM-SYM covers unorganised workers aged 18-40 with income up to Rs 15,000 and pays Rs 3,000 per month from age 60, so a 40-year-old landless farm labourer fits PM-SYM.
- **Answer**:

  ```text
  **PM‑KISAN**  
- **Who gets it?** “All landholding farmer families with cultivable land.”  
- **What you get?** “eligible farmers receive ₹6,000 per year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).”  
- **Your case:** You’re a 40‑year‑old farm labourer who doesn’t own land, so you don’t meet the “landholding farmer families” requirement. **You’re not eligible for PM‑KISAN.**

**PM‑SYM**  
- **Who gets it?** “Unorganised workers with monthly income up to ₹15,000.” “Entry age: 18 to 40 years.”  
- **What you get?** “Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.” “Frequency: instalments are released every four months.”  
- **Exclusions:** “Workers covered under EPFO or ESIC.” “Income tax payers.”  
- **Your case:** As a 40‑year‑old farm labourer, you fall inside the age window and, if your monthly earnings are ≤₹15,000, you’re eligible. You’re unlikely to be covered by EPFO/ESIC or paying income tax, so those exclusions don’t apply.  
- **Documents you’ll need:** “Aadhaar.” “Bank account details.” (Land records are not required for PM‑SYM.)

**Bottom line:**  
- **PM‑KISAN:** Not for you because you don’t own land.  
- **PM‑SYM:** Likely for you, giving you ₹6,000 a year in three ₹2,000 instalments, as long as your income stays ≤₹15,000 and you’re not covered by EPFO/ESIC or paying income tax.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.895
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 6128, Requested 2670. Please try again in 5.985s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  2. schemes/pm-sym.md:

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
  3. schemes/pm-kisan.md:

     ```text
     ## Benefits

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- The scheme was launched in February 2019.
- As of the 2024-25 financial year, over 11 crore farmer families have received
  support.

## Documents required

- Aadhaar.
- Bank account details.
- Land records.
- Farmers must keep their Aadhaar linked to their bank account to continue
  receiving instalments.

## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice
     ```
  4. schemes/pm-kisan.md:

     ```text
     ## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```

### 18. A 55-year-old wants a scheme; should they consider PM-KISAN or PM-SYM?

- **Question**: A 55-year-old wants a scheme; should they consider PM-KISAN or PM-SYM?
- **Reference**: PM-SYM has an entry age of 18 to 40 years, so a 55-year-old cannot newly join PM-SYM; PM-KISAN is for landholding farmer families and has no stated upper age limit, so a landholding farmer of 55 could consider PM-KISAN.
- **Answer**:

  ```text
  A 55‑year‑old can’t join PM‑SYM because the scheme is only for workers who are **18 to 40 years old**.  
> “Entry age: 18 to 40 years.” [schemes/pm-sym.md, sample_verified]

If the person owns cultivable land and is a farmer, they can apply for PM‑KISAN.  
> “All landholding farmer families with cultivable land.” [schemes/pm-kisan.md, sample_verified]

So, the 55‑year‑old should look at PM‑KISAN (if they meet the land‑holding requirement). If they’re not a farmer, they’ll need to explore other schemes.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.918
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, context_recall; LLMDidNotFinishException(The LLM generation was not completed. Please increase the max_tokens and try again.); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per minute (TPM): Limit 8000, Used 7770, Requested 2644. Please try again in 18.105s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  2. schemes/pm-sym.md:

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
  3. schemes/pm-kisan.md:

     ```text
     ## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```
  4. schemes/pm-kisan.md:

     ```text
     ## Benefits

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- The scheme was launched in February 2019.
- As of the 2024-25 financial year, over 11 crore farmer families have received
  support.

## Documents required

- Aadhaar.
- Bank account details.
- Land records.
- Farmers must keep their Aadhaar linked to their bank account to continue
  receiving instalments.

## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice
     ```

### 19. What does the scheme document say verbatim about PMAY-G assistance amounts?

- **Question**: What does the scheme document say verbatim about PMAY-G assistance amounts?
- **Reference**: PMAY-G provides financial assistance of Rs 1.20 lakh per house in plain areas and Rs 1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
- **Answer**:

  ```text
  The provided context does not mention any specific assistance amounts for PMAY‑G.
  ```

- **faithfulness**: 1.000
- **answer_relevancy**: 0.900
- **Error**: evaluation error: RAGAS did not return a score for context_precision, context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 198865, Requested 1894. Please try again in 5m27.888s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 198837, Requested 2603. Please try again in 10m22.079999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. schemes/pmay-g.md:

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
  2. schemes/pm-sym.md:

     ```text
     - Aadhaar.
- A savings bank account (Jan Dhan).

## How to apply

- Not specified in the official source.

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```
  3. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Source

- **Official source:** https://pmkisan.gov.in/
- **Checked on:** 2026-08-02
- **Data status:** sample_verified

## Jurisdiction

- **Jurisdiction:** Central government

## Eligibility

- All landholding farmer families with cultivable land.

## Exclusions

- Institutional landholders.
- Farmer families where any member pays income tax.
- Families with a government employee in a higher grade.
- Duplicate or ineligible beneficiaries are removed through periodic
  verification drives.
     ```
  4. schemes/pm-kisan.md:

     ```text
     ## How to apply

1. Enroll through the online PM-KISAN portal or Common Service Centres (CSCs).

## Not official advice

This record is a `sample_verified` entry: facts were checked against the
official national MyScheme discovery portal on 2026-08-02, but government
schemes change. SchemeGPT is a discovery assistant, not an official eligibility
decision. Before applying, re-verify eligibility, exclusions, and documents on
the official national discovery portal above.
     ```

### 20. Which scheme directory entry covers Sikkim and what does it link to?

- **Question**: Which scheme directory entry covers Sikkim and what does it link to?
- **Reference**: The Sikkim entry is a directory_seed discovery record (data_status: directory_seed) that confirms scheme-search coverage for the jurisdiction and links citizens to the official national MyScheme discovery portal (https://www.myscheme.gov.in/); it makes no scheme-level eligibility claims.
- **Answer**:

  ```text
  The entry for **Sikkim** is the directory seed that covers the state.  
It points you to the official national discovery portal:

> This is a discovery/coverage directory seed for Sikkim. [Sikkim, directory_seed]  
> MyScheme (official national discovery portal): https://www.myscheme.gov.in/ [Sikkim, directory_seed]
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, answer_relevancy, context_precision, context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 198861, Requested 1530. Please try again in 2m48.912s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 198858, Requested 1514. Please try again in 2m40.704s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 198855, Requested 2204. Please try again in 7m37.488s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-20b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 198853, Requested 2395. Please try again in 8m59.135999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

- **Retrieved sources/contexts**:
  1. states/sikkim.md:

     ```text
     # Sikkim

**Type:** State
**Code:** SK
**Region:** Northeast
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Sikkim. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Sikkim has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Sikkim on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```
  2. states/sikkim.md:

     ```text
     - MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore

- income support
- health
- education
- housing
- jobs
- agriculture
- social security

## Verification note

This record has `data_status: directory_seed`. It is a discovery/coverage seed,
not a verified eligibility decision. Before applying, always verify scheme-level
eligibility for Sikkim against the official national MyScheme discovery portal
and the issuing department.
     ```
  3. states/dadra-and-nagar-haveli-and-daman-and-diu.md:

     ```text
     # Dadra and Nagar Haveli and Daman and Diu

**Type:** Union Territory
**Code:** DD
**Region:** West
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Dadra and Nagar Haveli and Daman and Diu. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Dadra and Nagar Haveli and Daman and Diu has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Dadra and Nagar Haveli and Daman and Diu on the official national MyScheme
discovery portal:
     ```
  4. states/ladakh.md:

     ```text
     # Ladakh

**Type:** Union Territory
**Code:** LA
**Region:** North
**Data status:** `directory_seed`
**Last verified:** 2026-08-02

## What this record is

This is a discovery/coverage directory seed for Ladakh. It confirms that
SchemeGPT covers this jurisdiction for nationwide scheme search and points
citizens to the official national discovery portal. Scheme-level eligibility
for Ladakh has not been individually verified yet, and no state scheme names,
benefit amounts, or eligibility decisions are claimed here.

## Official discovery

Search for schemes available in Ladakh on the official national MyScheme
discovery portal:

- MyScheme (official national discovery portal): https://www.myscheme.gov.in/

## Categories you can explore
     ```

## Notes

- The threshold of **0.70** is a project triage threshold, not a universal quality claim.
- RAGAS evaluation consumes Groq free-tier quota; `--limit N` provides cheap/free partial runs.
- Per-case scores are also available in `scores.json`.
