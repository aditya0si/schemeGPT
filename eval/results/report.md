# SchemeGPT RAGAS Evaluation Report

- Generated: `2026-08-02T10:54:04+00:00` (UTC)
- Cases evaluated: 12 of 12
- Command: `python -m eval.run_eval`
- Threshold: **0.70** - any `faithfulness` or `answer_relevancy` score below this value (or a missing score) is a failure case.
- Judge LLM: Groq (`llama-3.3-70b-versatile`, free tier); embeddings: local `all-MiniLM-L6-v2`.

## Aggregate Scores

| Metric | Score |
| --- | --- |
| faithfulness | 0.950 |
| answer_relevancy | 0.774 |

## Per-Question Scores

| # | Question | faithfulness | answer_relevancy | Status |
| --- | --- | --- | --- | --- |
| 1 | What health insurance cover does Ayushman Bharat PM-JAY provide per family per year? | 1.000 | 0.911 | pass |
| 2 | When was GST introduced in India and which indirect taxes did it subsume? | 1.000 | 0.915 | pass |
| 3 | What is the GST registration turnover threshold for goods and for services? | 1.000 | 0.995 | pass |
| 4 | How much income support does PM-KISAN provide and in what instalments is it paid? | n/a | 0.955 | FAIL |
| 5 | Who is excluded from receiving PM-KISAN benefits? | n/a | 0.996 | FAIL |
| 6 | What monthly pension does PM-SYM provide and at what age does it start? | 1.000 | 0.920 | pass |
| 7 | How much financial assistance does PMAY-G provide for building a pucca house? | n/a | 0.726 | FAIL |
| 8 | What are the eligibility conditions for DPIIT startup recognition under Startup India? | n/a | 0.992 | FAIL |
| 9 | What is the current exchange rate of Bitcoin to the Indian rupee? | 1.000 | 0.000 | FAIL |
| 10 | Which jurisdictions does the SchemeGPT directory cover, and what does a state or union territory entry tell a citizen? | 0.900 | 0.902 | pass |
| 11 | I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile? | 0.700 | 0.000 | FAIL |
| 12 | पीएम-किसान के तहत पात्र किसान परिवारों को प्रति वर्ष कितनी आय सहायता मिलती है और यह कितनी किश्तों में दी जाती है? | 1.000 | 0.976 | pass |

## Failure Cases

6 case(s) flagged: score below the threshold or an evaluation error.

### 1. How much income support does PM-KISAN provide and in what instalments is it paid?

- **Question**: How much income support does PM-KISAN provide and in what instalments is it paid?
- **Reference**: PM-KISAN provides ₹6,000 per year to eligible landholding farmer families, paid directly into their bank accounts through Direct Benefit Transfer (DBT) in three equal instalments of ₹2,000 each, released every four months.
- **Answer**:

  ```text
  PM-KISAN provides ₹6,000 per year as income support, paid in three equal instalments of ₹2,000 each, released every four months.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.955
- **Error**: evaluation error: RAGAS did not return a score for faithfulness; TimeoutError()

- **Retrieved sources/contexts**:
  1. schemes/pm-kisan.md:

     ```text
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Key facts
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
  3. schemes/pm-kisan.md:

     ```text
     ## Key facts

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- Eligibility: all landholding farmer families with cultivable land.
- Exclusions: institutional landholders, farmer families where any member pays
  income tax, and families with a government employee in a higher grade.
- Enrollment: through the online PM-KISAN portal or Common Service Centres (CSCs).
- Documents: Aadhaar, bank account details, and land records are required.

## Updates
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

### 2. Who is excluded from receiving PM-KISAN benefits?

- **Question**: Who is excluded from receiving PM-KISAN benefits?
- **Reference**: Excluded from PM-KISAN are institutional landholders, farmer families where any member pays income tax, and families with a government employee in a higher grade.
- **Answer**:

  ```text
  The following are excluded from receiving PM-KISAN benefits: 
1. Institutional landholders
2. Farmer families where any member pays income tax
3. Families with a government employee in a higher grade
4. Duplicate or ineligible beneficiaries (removed through periodic verification drives)
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.996
- **Error**: evaluation error: RAGAS did not return a score for faithfulness; TimeoutError()

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
     # PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)

PM-KISAN is a central sector scheme that provides income support to landholding
farmer families in India. Under the scheme, eligible farmers receive ₹6,000 per
year, paid directly into their bank accounts through Direct Benefit Transfer (DBT).

## Key facts
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
     ## Key facts

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- Eligibility: all landholding farmer families with cultivable land.
- Exclusions: institutional landholders, farmer families where any member pays
  income tax, and families with a government employee in a higher grade.
- Enrollment: through the online PM-KISAN portal or Common Service Centres (CSCs).
- Documents: Aadhaar, bank account details, and land records are required.

## Updates
     ```

### 3. How much financial assistance does PMAY-G provide for building a pucca house?

- **Question**: How much financial assistance does PMAY-G provide for building a pucca house?
- **Reference**: PMAY-G provides financial assistance of ₹1.20 lakh per house in plain areas and ₹1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
- **Answer**:

  ```text
  PMAY-G provides financial assistance of ₹1.20 lakh per house in plain areas and ₹1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.726
- **Error**: evaluation error: RAGAS did not return a score for faithfulness; TimeoutError()

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
  3. schemes/pmay-g.md:

     ```text
     ## Key facts

- Financial assistance: ₹1.20 lakh per house in plain areas and ₹1.30 lakh in hilly
  areas, difficult areas, and Integrated Action Plan (IAP) districts.
- Target: construction of around 2.95 crore houses (original target until 2024).
- Toilet: assistance for toilet construction is available under Swachh Bharat
  Mission - Gramin (SBM-G).
- MGNREGA convergence: 90 person-days of unskilled wage employment per house.
- Funding: shared between the central and state governments, 60:40 in plain areas
  and 90:10 in North-Eastern and hilly states.
- Beneficiary selection: based on housing deprivation parameters from SECC 2011.

## Eligibility
     ```
  4. schemes/pmay-g.md:

     ```text
     # PMAY-G (Pradhan Mantri Awas Yojana - Gramin)

Pradhan Mantri Awas Yojana - Gramin (PMAY-G) is a rural housing scheme that provides
financial assistance to eligible rural households for constructing a pucca house
with basic amenities.

## Key facts
     ```

### 4. What are the eligibility conditions for DPIIT startup recognition under Startup India?

- **Question**: What are the eligibility conditions for DPIIT startup recognition under Startup India?
- **Reference**: An entity must be incorporated as a private limited company, LLP, or registered partnership, be less than 10 years old, and have a turnover of up to ₹100 crore in any financial year.
- **Answer**:

  ```text
  To be eligible for DPIIT startup recognition under Startup India, an entity must: 
1. Be incorporated as a private limited company, LLP, or registered partnership.
2. Be less than 10 years old.
3. Have a turnover up to ₹100 crore in any financial year.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: 0.992
- **Error**: evaluation error: RAGAS did not return a score for faithfulness; TimeoutError()

- **Retrieved sources/contexts**:
  1. schemes/startup-india.md:

     ```text
     ## Key facts

- DPIIT recognition: startups are recognised by the Department for Promotion of
  Industry and Internal Trade (DPIIT) after an online application.
- Eligibility: an entity must be incorporated as a private limited company, LLP, or
  registered partnership, be less than 10 years old, and have a turnover up to
  ₹100 crore in any financial year.
- Tax exemption: a 100% income tax exemption on profits for 3 consecutive financial
  years out of the first 10 years.
- Angel tax: recognised startups are exempt from angel tax under Section 56(2)(viib)
  of the Income Tax Act.
- Fund of Funds: a Fund of Funds for Startups (FFS) of ₹10,000 crore, managed by
  SIDBI.
- Self-certification: startups can self-certify compliance with 9 labour and 3
  environmental laws.

## Benefits
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
  4. schemes/startup-india.md:

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

### 5. What is the current exchange rate of Bitcoin to the Indian rupee?

- **Question**: What is the current exchange rate of Bitcoin to the Indian rupee?
- **Reference**: This question is out of scope for SchemeGPT: the provided context contains no information about cryptocurrency exchange rates, so the answer should state that the information is not available.
- **Answer**:

  ```text
  The answer is not in the context. The provided context only discusses the Indian government scheme PM-KISAN and its related details, but does not mention Bitcoin or exchange rates.
  ```

- **faithfulness**: 1.000
- **answer_relevancy**: 0.000

- **Retrieved sources/contexts**:
  1. schemes/pm-kisan.md:

     ```text
     ## Key facts

- Payment: ₹6,000 per year, paid in three equal instalments of ₹2,000 each.
- Frequency: instalments are released every four months.
- Eligibility: all landholding farmer families with cultivable land.
- Exclusions: institutional landholders, farmer families where any member pays
  income tax, and families with a government employee in a higher grade.
- Enrollment: through the online PM-KISAN portal or Common Service Centres (CSCs).
- Documents: Aadhaar, bank account details, and land records are required.

## Updates
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
  3. schemes/pm-sym.md:

     ```text
     ## How it works

The subscriber contributes a fixed monthly amount until age 60, and the central
government contributes an equal amount. After 60, the subscriber receives ₹3,000
per month. On exit before age 60, the accumulated corpus plus interest is paid
back, subject to conditions. On the subscriber's death, the spouse receives 50% of
the pension as family pension.
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

### 6. I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile?

- **Question**: I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile?
- **Reference**: PM-SYM (Pradhan Mantri Shram Yogi Maandhan) is a pension scheme for unorganised workers with monthly income up to Rs 15,000 and an entry age of 18 to 40 years; a 35-year-old unorganised worker earning about Rs 12,000 per month is within the documented entry age and income band. The Karnataka directory seed is a discovery entry, not a verified eligibility decision.
- **Answer**:

  ```text
  Based on the provided context, the Pradhan Mantri Shram Yogi Maandhan (PM-SYM) scheme may match your profile. It is a pension scheme for unorganised workers with a monthly income up to ₹15,000, and your income of ₹12,000 per month falls within this limit. Additionally, your age of 35 is within the entry age range of 18 to 40 years for the scheme. However, to confirm eligibility, verification of your income and occupation is required, as well as checking if you are covered under EPFO or ESIC, or if you are an income tax payer, as these are exclusion criteria.
  ```

- **faithfulness**: 0.700
- **answer_relevancy**: 0.000

- **Retrieved sources/contexts**:
  1. schemes/pm-sym.md:

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
  2. schemes/pm-sym.md:

     ```text
     # PM-SYM (Pradhan Mantri Shram Yogi Maandhan)

Pradhan Mantri Shram Yogi Maandhan (PM-SYM) is a pension scheme for unorganised
workers. It provides a monthly pension of ₹3,000 after the subscriber attains the
age of 60 years.

## Key facts

- Pension: ₹3,000 per month after age 60.
- Entry age: 18 to 40 years.
- Contribution: ₹55 to ₹200 per month, depending on the entry age.
- Government contribution: the central government makes an equal matching
  contribution.
- Eligibility: unorganised workers with monthly income up to ₹15,000.
- Excluded: workers covered under EPFO or ESIC, and income tax payers.
- Documents: Aadhaar and a savings bank account (Jan Dhan) are required.

## How it works
     ```
  3. schemes/pm-sym.md:

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
  4. schemes/pm-sym.md:

     ```text
     ## How it works

The subscriber contributes a fixed monthly amount until age 60, and the central
government contributes an equal amount. After 60, the subscriber receives ₹3,000
per month. On exit before age 60, the accumulated corpus plus interest is paid
back, subject to conditions. On the subscriber's death, the spouse receives 50% of
the pension as family pension.
     ```

## Notes

- The threshold of **0.70** is a project triage threshold, not a universal quality claim.
- RAGAS evaluation consumes Groq free-tier quota; `--limit N` provides cheap/free partial runs.
- Per-case scores are also available in `scores.json`.
