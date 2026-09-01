# SchemeGPT RAGAS Evaluation Report

- Generated: `2026-09-01T18:13:19+00:00` (UTC)
- Cases evaluated: 20 of 20
- Command: `python -m eval.run_eval`
- Threshold: **0.70** - any `faithfulness` or `answer_relevancy` score below this value (or a missing score) is a failure case.
- Judge LLM: Groq (settings.groq_model, free tier); embeddings: local sentence-transformers.

## Aggregate Scores

| Metric | Score |
| --- | --- |
| faithfulness | n/a |
| answer_relevancy | n/a |
| context_precision | 0.000 |
| context_recall | n/a |

## Delta vs previous run

| Metric | This run | Previous | Delta |
| --- | --- | --- | --- |
| faithfulness | n/a | n/a | n/a |
| answer_relevancy | n/a | 0.835 | n/a |
| context_precision | 0.000 | 1.000 | -1.000 |
| context_recall | n/a | n/a | n/a |

## Per-Question Scores

| # | Question | faithfulness | answer_relevancy | context_precision | context_recall | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | What health insurance cover does Ayushman Bharat PM-JAY provide per family per year? | n/a | n/a | n/a | n/a | FAIL |
| 2 | When was GST introduced in India and which indirect taxes did it subsume? | n/a | n/a | n/a | n/a | FAIL |
| 3 | What is the GST registration turnover threshold for goods and for services? | n/a | n/a | n/a | n/a | FAIL |
| 4 | How much income support does PM-KISAN provide and in what instalments is it paid? | n/a | n/a | 0.000 | n/a | FAIL |
| 5 | Who is excluded from receiving PM-KISAN benefits? | n/a | n/a | n/a | n/a | FAIL |
| 6 | What monthly pension does PM-SYM provide and at what age does it start? | n/a | n/a | n/a | n/a | FAIL |
| 7 | How much financial assistance does PMAY-G provide for building a pucca house? | n/a | n/a | n/a | n/a | FAIL |
| 8 | What are the eligibility conditions for DPIIT startup recognition under Startup India? | n/a | n/a | n/a | n/a | FAIL |
| 9 | What is the current exchange rate of Bitcoin to the Indian rupee? | n/a | n/a | n/a | n/a | FAIL |
| 10 | Which jurisdictions does the SchemeGPT directory cover, and what does a state or union territory entry tell a citizen? | n/a | n/a | n/a | n/a | FAIL |
| 11 | I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile? | n/a | n/a | n/a | n/a | FAIL |
| 12 | पीएम-किसान के तहत पात्र किसान परिवारों को प्रति वर्ष कितनी आय सहायता मिलती है और यह कितनी किश्तों में दी जाती है? | n/a | n/a | n/a | n/a | FAIL |
| 13 | pm kisan ka paisa kab aata hai | n/a | n/a | n/a | n/a | FAIL |
| 14 | kisan ko sarkar har saal kitne rupaye deti hai | n/a | n/a | n/a | n/a | FAIL |
| 15 | mera pension banao kaun sa scheme chune | n/a | n/a | n/a | n/a | FAIL |
| 16 | पीएम-श्रम योगी मानधन योजना कितनी पेंशन देती है और किस उम्र में शुरू होती है? | n/a | n/a | n/a | n/a | FAIL |
| 17 | Compare PM-KISAN and PM-SYM for a 40-year-old landless farm labourer. | n/a | n/a | n/a | n/a | FAIL |
| 18 | A 55-year-old wants a scheme; should they consider PM-KISAN or PM-SYM? | n/a | n/a | n/a | n/a | FAIL |
| 19 | What does the scheme document say verbatim about PMAY-G assistance amounts? | n/a | n/a | n/a | n/a | FAIL |
| 20 | Which scheme directory entry covers Sikkim and what does it link to? | n/a | n/a | n/a | n/a | FAIL |

## Failure Cases

20 case(s) flagged: score below the threshold or an evaluation error.

### 1. What health insurance cover does Ayushman Bharat PM-JAY provide per family per year?

- **Question**: What health insurance cover does Ayushman Bharat PM-JAY provide per family per year?
- **Reference**: Ayushman Bharat PM-JAY provides a health cover of ₹5 lakh per family per year, on a floater basis, for secondary and tertiary hospitalisation.
- **Answer**:

  ```text
  Ayushman Bharat Pradhan Mantri Jan Arogya Yojana (PM-JAY) provides a health cover of Rs 5 lakh per family per year, on a floater basis, for secondary and tertiary hospitalisation. Around 12 crore families (approximately 55 crore individuals) are covered, and treatment is cashless and paperless at empanelled hospitals anywhere in India.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

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
  PM-KISAN pays Rs 6000 per year.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: evaluation error: RAGAS did not return a score for faithfulness, answer_relevancy, context_recall; RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-120b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 199052, Requested 1443. Please try again in 3m33.84s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-120b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 199050, Requested 1891. Please try again in 6m46.512s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}); RateLimitError(Error code: 429 - {'error': {'message': 'Rate limit reached for model \`openai/gpt-oss-120b\` in organization \`org_01ks7njm54ehm9mbfdc97rda95\` service tier \`on_demand\` on tokens per day (TPD): Limit 200000, Used 199048, Requested 1675. Please try again in 5m12.336s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

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

### 9. What is the current exchange rate of Bitcoin to the Indian rupee?

- **Question**: What is the current exchange rate of Bitcoin to the Indian rupee?
- **Reference**: This question is out of scope for SchemeGPT: the provided context contains no information about cryptocurrency exchange rates, so the answer should state that the information is not available.
- **Answer**:

  ```text
  The Goods and Services Tax (GST) was introduced in India on 1 July 2017 and subsumed multiple indirect taxes such as VAT, service tax, and excise duty. Businesses above the turnover threshold must register: Rs 40 lakh for goods and Rs 20 lakh for services, with lower thresholds in some states. The main tax slabs are 5%, 12%, 18%, and 28%.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 10. Which jurisdictions does the SchemeGPT directory cover, and what does a state or union territory entry tell a citizen?

- **Question**: Which jurisdictions does the SchemeGPT directory cover, and what does a state or union territory entry tell a citizen?
- **Reference**: The SchemeGPT directory covers 36 jurisdictions: 28 states and 8 union territories. Each state/UT entry is a directory_seed discovery entry: it maps the jurisdiction for scheme search and links to the official national MyScheme discovery portal, but it is not a verified scheme-level eligibility decision.
- **Answer**:

  ```text
  This question is outside the pre-made demo topics, and the live Groq answer service is not configured or is currently unavailable, so no retrieval or LLM answer could be produced. The demo fallback covers PM-KISAN, Ayushman Bharat PM-JAY, PMAY-G, PM-SYM, Startup India, and GST. Add a valid GROQ_API_KEY and restart the API to enable live RAG answers.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 11. I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile?

- **Question**: I am a 35-year-old unorganised worker earning about 12,000 rupees per month in rural Karnataka. Which central pension scheme could match my profile?
- **Reference**: PM-SYM (Pradhan Mantri Shram Yogi Maandhan) is a pension scheme for unorganised workers with monthly income up to Rs 15,000 and an entry age of 18 to 40 years; a 35-year-old unorganised worker earning about Rs 12,000 per month is within the documented entry age and income band. The Karnataka directory seed is a discovery entry, not a verified eligibility decision.
- **Answer**:

  ```text
  Pradhan Mantri Shram Yogi Maandhan (PM-SYM) provides a monthly pension of Rs 3,000 after the subscriber attains the age of 60 years. The entry age is 18 to 40 years, contributions range from Rs 55 to Rs 200 per month, and the central government makes an equal matching contribution. Eligible workers are unorganised workers with monthly income up to Rs 15,000.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 12. पीएम-किसान के तहत पात्र किसान परिवारों को प्रति वर्ष कितनी आय सहायता मिलती है और यह कितनी किश्तों में दी जाती है?

- **Question**: पीएम-किसान के तहत पात्र किसान परिवारों को प्रति वर्ष कितनी आय सहायता मिलती है और यह कितनी किश्तों में दी जाती है?
- **Reference**: पीएम-किसान के तहत पात्र भूमिधारी किसान परिवारों को प्रति वर्ष ₹6,000 की आय सहायता मिलती है, जो डीबीटी द्वारा सीधे उनके बैंक खाते में ₹2,000 की तीन समान किश्तों में दी जाती है, और हर चार महीने में एक किश्त जारी की जाती है।
- **Answer**:

  ```text
  यह प्रश्न पहले से बनाए गए डेमो विषयों से बाहर है, और लाइव ग्रूक उत्तर सेवा कॉन्फ़िगर नहीं है या अभी उपलब्ध नहीं है, इसलिए कोई रिट्रीवल या एलएलएम उत्तर नहीं बनाया जा सका। डेमो फॉलबैक पीएम-किसान, आयुष्मान भारत पीएम-जय, पीएमएवाई-जी, पीएम-एसवाईएम, स्टार्टअप इंडिया और जीएसटी को कवर करता है। लाइव आरएजी उत्तर सक्षम करने के लिए एक मान्य GROQ_API_KEY जोड़ें और API को पुनः आरंभ करें।
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 13. pm kisan ka paisa kab aata hai

- **Question**: pm kisan ka paisa kab aata hai
- **Reference**: PM-KISAN income support of Rs 6,000 per year is released in three equal instalments of Rs 2,000 each, every four months, by Direct Benefit Transfer (DBT).
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

### 14. kisan ko sarkar har saal kitne rupaye deti hai

- **Question**: kisan ko sarkar har saal kitne rupaye deti hai
- **Reference**: PM-KISAN provides income support of Rs 6,000 per year to eligible landholding farmer families in India, paid directly into their bank accounts through Direct Benefit Transfer (DBT).
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

### 15. mera pension banao kaun sa scheme chune

- **Question**: mera pension banao kaun sa scheme chune
- **Reference**: PM-SYM (Pradhan Mantri Shram Yogi Maandhan) is a pension scheme for unorganised workers with monthly income up to Rs 15,000 and an entry age of 18 to 40 years; it provides a monthly pension of Rs 3,000 after the subscriber attains the age of 60 years.
- **Answer**:

  ```text
  Pradhan Mantri Shram Yogi Maandhan (PM-SYM) provides a monthly pension of Rs 3,000 after the subscriber attains the age of 60 years. The entry age is 18 to 40 years, contributions range from Rs 55 to Rs 200 per month, and the central government makes an equal matching contribution. Eligible workers are unorganised workers with monthly income up to Rs 15,000.
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 16. पीएम-श्रम योगी मानधन योजना कितनी पेंशन देती है और किस उम्र में शुरू होती है?

- **Question**: पीएम-श्रम योगी मानधन योजना कितनी पेंशन देती है और किस उम्र में शुरू होती है?
- **Reference**: पीएम-श्रम योगी मानधन (पीएम-एसवाईएम) असंगठित क्षेत्र के श्रमिकों के लिए पेंशन योजना है, जो अभिदाता के 60 वर्ष की आयु पूरी करने पर ₹3,000 मासिक पेंशन देती है; प्रवेश आयु 18 से 40 वर्ष है।
- **Answer**:

  ```text
  यह प्रश्न पहले से बनाए गए डेमो विषयों से बाहर है, और लाइव ग्रूक उत्तर सेवा कॉन्फ़िगर नहीं है या अभी उपलब्ध नहीं है, इसलिए कोई रिट्रीवल या एलएलएम उत्तर नहीं बनाया जा सका। डेमो फॉलबैक पीएम-किसान, आयुष्मान भारत पीएम-जय, पीएमएवाई-जी, पीएम-एसवाईएम, स्टार्टअप इंडिया और जीएसटी को कवर करता है। लाइव आरएजी उत्तर सक्षम करने के लिए एक मान्य GROQ_API_KEY जोड़ें और API को पुनः आरंभ करें।
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 17. Compare PM-KISAN and PM-SYM for a 40-year-old landless farm labourer.

- **Question**: Compare PM-KISAN and PM-SYM for a 40-year-old landless farm labourer.
- **Reference**: PM-KISAN provides income support to landholding farmer families (Rs 6,000 per year via DBT), so a landless labourer does not qualify for it; PM-SYM covers unorganised workers aged 18-40 with income up to Rs 15,000 and pays Rs 3,000 per month from age 60, so a 40-year-old landless farm labourer fits PM-SYM.
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

### 18. A 55-year-old wants a scheme; should they consider PM-KISAN or PM-SYM?

- **Question**: A 55-year-old wants a scheme; should they consider PM-KISAN or PM-SYM?
- **Reference**: PM-SYM has an entry age of 18 to 40 years, so a 55-year-old cannot newly join PM-SYM; PM-KISAN is for landholding farmer families and has no stated upper age limit, so a landholding farmer of 55 could consider PM-KISAN.
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

### 19. What does the scheme document say verbatim about PMAY-G assistance amounts?

- **Question**: What does the scheme document say verbatim about PMAY-G assistance amounts?
- **Reference**: PMAY-G provides financial assistance of Rs 1.20 lakh per house in plain areas and Rs 1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts.
- **Answer**:

  ```text
  Pradhan Mantri Awas Yojana - Gramin (PMAY-G) provides financial assistance of Rs 1.20 lakh per house in plain areas and Rs 1.30 lakh in hilly areas, difficult areas, and Integrated Action Plan (IAP) districts for constructing a pucca house with basic amenities. Funding is shared between the central and state governments (60:40 in plain areas).
  ```

- **faithfulness**: n/a
- **answer_relevancy**: n/a
- **Error**: Live RAG returned demo fallback; provide a valid GROQ_API_KEY before evaluating

- **Retrieved sources/contexts**:
  - (no contexts retrieved)

### 20. Which scheme directory entry covers Sikkim and what does it link to?

- **Question**: Which scheme directory entry covers Sikkim and what does it link to?
- **Reference**: The Sikkim entry is a directory_seed discovery record (data_status: directory_seed) that confirms scheme-search coverage for the jurisdiction and links citizens to the official national MyScheme discovery portal (https://www.myscheme.gov.in/); it makes no scheme-level eligibility claims.
- **Answer**:

  ```text
  This question is outside the pre-made demo topics, and the live Groq answer service is not configured or is currently unavailable, so no retrieval or LLM answer could be produced. The demo fallback covers PM-KISAN, Ayushman Bharat PM-JAY, PMAY-G, PM-SYM, Startup India, and GST. Add a valid GROQ_API_KEY and restart the API to enable live RAG answers.
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
