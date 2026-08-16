"""SchemeGPT — Civic Pulse (Streamlit product surface).

Iteration 3 rewrite of the demo UI. The backend API contracts are untouched:

    GET  /states                  -> list of 36 state/UT records
    POST /profiles                -> {profile_id, access_token, ...} (one-time token)
    GET/PUT/DELETE /profiles/{id} -> authenticated with X-Profile-Token header
    POST /query                   -> {question, language, profile} -> {answer, sources, mode, notice, language}
    POST /recommendations         -> {profile, question, language} -> {recommendations, disclaimer, profile_state}

Design goals: a calm, modern civic product for young citizens of India. Deep
ink/navy background, warm saffron accent, mint success color, coral attention
color, rounded cards, compact status pills, full English/Hindi localization,
responsive to desktop and mobile, no external assets and no emojis.

Security rules observed here:
  * The one-time profile ``access_token`` lives only in ``st.session_state``.
    It is never logged, never placed in a query string, and only ever sent in
    the ``X-Profile-Token`` header.
  * Error messages are always fixed, localized strings. Raw exception bodies
    (which can contain secrets or database URLs) are never rendered.
"""

import html
import os
from typing import Callable

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_URL = os.environ.get("STREAMLIT_API_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 120  # generous: live RAG answers can take a while
PROFILE_TIMEOUT = 15
OFFICIAL_PORTAL_URL = "https://www.myscheme.gov.in/"

# Approachable goal picker. Values intentionally mirror the catalog tags so the
# deterministic recommender's overlap scoring keeps working in both languages.
GOAL_TAGS = [
    "income support",
    "health",
    "education",
    "housing",
    "jobs",
    "agriculture",
    "pension",
    "social security",
    "startups",
    "tax",
]
GOAL_LABELS_HI = {
    "income support": "आय सहायता",
    "health": "स्वास्थ्य",
    "education": "शिक्षा",
    "housing": "आवास",
    "jobs": "नौकरियाँ",
    "agriculture": "कृषि",
    "pension": "पेंशन",
    "social security": "सामाजिक सुरक्षा",
    "startups": "स्टार्टअप",
    "tax": "कर / टैक्स",
}

# Social category picker. Raw option values are the stable English sentinels
# ("" = none) stored verbatim in ProfileData payloads and matched by the
# recommender; these Hindi strings are cosmetic display labels applied only
# via format_func.
CATEGORY_LABELS_HI = {
    "General": "सामान्य",
    "OBC": "ओबीसी",
    "SC": "अनुसूचित जाति",
    "ST": "अनुसूचित जनजाति",
    "EWS": "आर्थिक रूप से कमजोर वर्ग",
}

# Gender picker. Same pattern as above: stable English sentinel values with
# Hindi display labels applied only via format_func.
GENDER_LABELS_HI = {
    "Female": "महिला",
    "Male": "पुरुष",
    "Other": "अन्य",
}

# Canonical 36 states + UTs, used ONLY if /states cannot be reached. Same order
# as data/india_states.json so it never contradicts the service.
FALLBACK_STATE_NAMES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi (NCT)",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

# ---------------------------------------------------------------------------
# Localization
# ---------------------------------------------------------------------------
T = {
    "en": {
        "brand": "Civic Pulse",
        "hero_title": "Your benefits, decoded.",
        "hero_sub": "Tell us what's going on — we'll surface support you can "
                    "actually explore.",
        "coverage": "36 states + UTs · coverage directory",
        # Iteration 4: truthful line rendered when GET /coverage is available.
        # Placeholders are filled from the endpoint; when the endpoint is
        # unreachable the static `coverage` string above is the safe fallback.
        "coverage_live": "{j} jurisdictions mapped · {v} verified sample "
                         "schemes · state directories expanding",
        "step_tell": "Tell us",
        "step_tell_sub": "Describe your situation in plain words.",
        "step_match": "We match",
        "step_match_sub": "We scan the coverage directory for schemes worth "
                          "exploring.",
        "step_verify": "You verify",
        "step_verify_sub": "Open the official links and confirm eligibility "
                           "before applying.",
        "tab_ask": "Ask SchemeGPT",
        "tab_matches": "My matches",
        "tab_profile": "My profile",
        "ask_placeholder": "Ask about a scheme, an act, or a benefit you may "
                           "qualify for…",
        "ask_empty_title": "Ask anything",
        "ask_empty_body": 'Try: "What is PM-KISAN and who is eligible?" or '
                          '"Which housing schemes could fit me?"',
        "thinking": "Thinking…",
        "sources_label": "Sources",
        "live_pill": "Live answer",
        "demo_pill": "Demo fallback",
        "jurisdiction": "Jurisdiction",
        "state": "State/UT",
        "verified": "Verified",
        "status": "Status",
        "seed_label": "Discovery only — verify eligibility",
        "status_sample": "Sample verified",
        "status_seed": "Directory seed",
        "status_unknown": "Status unknown",
        "official_source": "Official source",
        "official_portal": "Official national discovery portal",
        "source_unknown": "Source",
        "rec_unknown": "Scheme",
        "reason": "Reason",
        "scope": "Scope / benefits",
        "match_hint": "Based on your saved profile, from the coverage "
                      "directory.",
        "match_question": "Anything specific to prioritize? (optional)",
        "find_matches": "Find my matches",
        "matching_spinner": "Finding matches…",
        "match_none": "No matches found with the current profile. Try adding a "
                      "few more details.",
        "matches_empty_title": "No profile yet",
        "matches_empty_body": "Create and save a profile in the sidebar, then "
                              "come back here to see tailored matches.",
        "disclaimer_title": "About these results",
        "disclaimer_body": "SchemeGPT is a discovery assistant, not an official "
                           "eligibility decision. Always use the official link "
                           "to apply.",
        "profile_section": "My profile",
        "build_profile": "Build my profile",
        "edit_profile": "Edit my profile",
        "f_state": "State / UT",
        "state_placeholder": "— Select —",
        "f_name": "Name (optional)",
        "f_name_placeholder": "e.g. Ravi",
        "f_age": "Age",
        "f_income": "Annual income (₹)",
        "f_occupation": "Occupation (optional)",
        "f_occupation_placeholder": "e.g. farmer, student, government job",
        "f_category": "Social category",
        "category_none": "— None —",
        "f_gender": "Gender",
        "gender_none": "Prefer not to say",
        "f_area": "Area",
        "area_none": "Not specified",
        "rural": "Rural",
        "urban": "Urban",
        "f_disability": "Disability",
        "disability_none": "Prefer not to say",
        "yes": "Yes",
        "no": "No",
        "f_family": "Family size",
        "f_goals": "What matters to you?",
        "save_profile": "Save my profile",
        "save_hint": "Saved only when you press Save. Please don't enter "
                     "Aadhaar numbers or sensitive documents.",
        "profile_saved": "Profile saved. Note your private save code below.",
        "profile_updated": "Profile updated.",
        "load_profile": "Load saved profile",
        "profile_id_field": "Profile ID",
        "save_code_label": "Save code",
        "save_code_help": "The private one-time code shown when you saved your "
                          "profile.",
        "load_btn": "Load",
        "profile_loaded": "Profile loaded.",
        "connected_pill": "Saved profile connected",
        "not_connected_pill": "Not saved — this session only",
        "delete_profile": "Delete my saved profile",
        "delete_confirm": "I understand this permanently removes my saved "
                          "profile.",
        "profile_deleted": "Saved profile deleted.",
        "save_code_title": "Your private save code",
        "save_code_intro": "Note these down now — they are shown once and the "
                           "service will never show them again.",
        "save_code_warn": "Keep this private. Anyone with these details can "
                          "view or delete your saved profile. This MVP uses a "
                          "private save code — not a login account.",
        "profile_summary_title": "Your profile",
        "save_guidance": "Your profile lives only in this browser session "
                         "until you press Save. The private save code lets you "
                         "restore it on another device.",
        "profile_empty_title": "No profile yet",
        "profile_empty": "Use the sidebar to build and save your profile — or "
                         "load it with your private save code.",
        "save_load_guide_title": "Saving & loading",
        "save_load_guide": '1. Build your profile in the sidebar and press '
                           '"Save my profile".\n2. Note the private save code '
                           'shown once.\n3. On another device, open the sidebar '
                           '→ "Load saved profile" and enter the Profile ID + '
                           "save code.",
        "privacy_title": "Privacy",
        "privacy_note": "Profiles are stored only when you choose to save. The "
                        "save code is private. Please avoid entering Aadhaar "
                        "numbers or sensitive documents.",
        "mvp_note": "This MVP uses a private save code — not a full account "
                    "login.",
        "reset_session": "Reset session",
        "reset_done": "Session reset.",
        "language_label": "Language",
        "err_timeout": "The service took too long to respond. Please try "
                       "again.",
        "err_unreachable": "We couldn't reach the SchemeGPT service. Please "
                           "check that it is running and try again.",
        "err_bad_response": "The service returned an unexpected response.",
        "err_generic": "Something went wrong. Please try again.",
        "err_profile_auth": "Profile not found, or the save code is incorrect. "
                            "Please check both and try again.",
        "err_validation": "Some details couldn't be saved. Please check the "
                          "values and try again.",
        "err_missing_id_token": "Please enter both the profile ID and the save "
                                "code.",
        "err_empty_profile": "Add at least one detail before saving.",
        "err_states_shape": "The states list looked unexpected; using a "
                            "built-in fallback list.",
        "err_states_unreachable": "We couldn't load the states list from the "
                                  "service. Showing a built-in fallback.",
        "err_chat_fallback": "The service is temporarily unavailable. Please "
                             "try again.",
        "empty_answer": "The service returned an empty answer. Please try a "
                        "different question.",
        "age_unit": "yrs",
    },
    "hi": {
        "brand": "सिविक पल्स",
        "hero_title": "आपके लाभ, सरल शब्दों में।",
        "hero_sub": "बताइए क्या चल रहा है — हम ऐसी मदद सामने लाएँगे जिन्हें आप "
                    "वास्तव में देखकर समझ सकते हैं।",
        "coverage": "36 राज्य + केंद्र शासित प्रदेश · कवरेज निर्देशिका",
        "coverage_live": "{j} क्षेत्राधिकार मैप किए गए · {v} सत्यापित नमूना "
                         "योजनाएँ · राज्य निर्देशिकाएँ विस्तारित हो रही हैं",
        "step_tell": "हमें बताएं",
        "step_tell_sub": "अपनी स्थिति साधारण शब्दों में बताएं।",
        "step_match": "हम मिलाते हैं",
        "step_match_sub": "हम कवरेज निर्देशिका में देखने लायक योजनाएँ खोजते हैं।",
        "step_verify": "आप सत्यापित करें",
        "step_verify_sub": "आवेदन से पहले आधिकारिक लिंक से पात्रता की पुष्टि करें।",
        "tab_ask": "SchemeGPT से पूछें",
        "tab_matches": "मेरे मिलान",
        "tab_profile": "मेरी प्रोफ़ाइल",
        "ask_placeholder": "किसी योजना, अधिनियम या लाभ के बारे में पूछें जिसके "
                           "लिए आप पात्र हो सकते हैं…",
        "ask_empty_title": "कुछ भी पूछें",
        "ask_empty_body": 'जैसे: "PM-KISAN क्या है और कौन पात्र है?" या '
                          '"मेरे लिए कौन सी आवास योजनाएँ उपयुक्त हो सकती हैं?"',
        "thinking": "सोच रहे हैं…",
        "sources_label": "स्रोत",
        "live_pill": "लाइव उत्तर",
        "demo_pill": "डेमो फॉलबैक",
        "jurisdiction": "क्षेत्राधिकार",
        "state": "राज्य/कें.शा.",
        "verified": "सत्यापन",
        "status": "स्थिति",
        "seed_label": "केवल खोज — पात्रता जांचें",
        "status_sample": "नमूना सत्यापित",
        "status_seed": "डिस्कवरी प्रविष्टि",
        "status_unknown": "स्थिति अज्ञात",
        "official_source": "आधिकारिक स्रोत",
        "official_portal": "आधिकारिक राष्ट्रीय डिस्कवरी पोर्टल",
        "source_unknown": "स्रोत",
        "rec_unknown": "योजना",
        "reason": "कारण",
        "scope": "दायरा / लाभ",
        "match_hint": "आपकी सहेजी गई प्रोफ़ाइल के आधार पर, कवरेज निर्देशिका से।",
        "match_question": "कोई विशेष प्राथमिकता? (वैकल्पिक)",
        "find_matches": "मेरे मिलान देखें",
        "matching_spinner": "मिलान खोज रहे हैं…",
        "match_none": "वर्तमान प्रोफ़ाइल से कोई मिलान नहीं मिला। कुछ और विवरण "
                      "जोड़कर देखें।",
        "matches_empty_title": "अभी कोई प्रोफ़ाइल नहीं",
        "matches_empty_body": "साइडबार से प्रोफ़ाइल बनाकर सहेजें, फिर यहाँ आकर "
                              "अपने मिलान देखें।",
        "disclaimer_title": "इन परिणामों के बारे में",
        "disclaimer_body": "SchemeGPT एक खोज सहायक है, आधिकारिक पात्रता निर्णय "
                           "नहीं। आवेदन के लिए हमेशा आधिकारिक लिंक का उपयोग करें।",
        "profile_section": "मेरी प्रोफ़ाइल",
        "build_profile": "प्रोफ़ाइल बनाएं",
        "edit_profile": "प्रोफ़ाइल बदलें",
        "f_state": "राज्य / कें.शा. प्रदेश",
        "state_placeholder": "— चुनें —",
        "f_name": "नाम (वैकल्पिक)",
        "f_name_placeholder": "जैसे: रवि",
        "f_age": "आयु",
        "f_income": "वार्षिक आय (₹)",
        "f_occupation": "व्यवसाय (वैकल्पिक)",
        "f_occupation_placeholder": "जैसे: किसान, छात्र, सरकारी नौकरी",
        "f_category": "सामाजिक श्रेणी",
        "category_none": "— कोई नहीं —",
        "f_gender": "लिंग",
        "gender_none": "कहना नहीं चाहते",
        "f_area": "क्षेत्र",
        "area_none": "निर्दिष्ट नहीं",
        "rural": "ग्रामीण",
        "urban": "शहरी",
        "f_disability": "विकलांगता",
        "disability_none": "कहना नहीं चाहते",
        "yes": "हाँ",
        "no": "नहीं",
        "f_family": "परिवार का आकार",
        "f_goals": "आपके लिए क्या मायने रखता है?",
        "save_profile": "मेरी प्रोफ़ाइल सहेजें",
        "save_hint": "केवल सहेजें दबाने पर ही सहेजा जाता है। कृपया आधार नंबर या "
                     "संवेदनशील दस्तावेज़ न डालें।",
        "profile_saved": "प्रोफ़ाइल सहेज ली गई। नीचे अपना निजी सेव कोड नोट करें।",
        "profile_updated": "प्रोफ़ाइल अपडेट हो गई।",
        "load_profile": "सहेजी गई प्रोफ़ाइल लोड करें",
        "profile_id_field": "प्रोफ़ाइल आईडी",
        "save_code_label": "सेव कोड",
        "save_code_help": "वह निजी कोड जो प्रोफ़ाइल सहेजते समय दिखाया गया था।",
        "load_btn": "लोड करें",
        "profile_loaded": "प्रोफ़ाइल लोड हो गई।",
        "connected_pill": "सहेजी गई प्रोफ़ाइल जुड़ी है",
        "not_connected_pill": "अभी सहेजी नहीं — केवल इस सत्र में",
        "delete_profile": "सहेजी गई प्रोफ़ाइल हटाएं",
        "delete_confirm": "मैं समझता/समझती हूँ कि इससे सहेजी गई प्रोफ़ाइल स्थायी "
                          "रूप से हट जाएगी।",
        "profile_deleted": "सहेजी गई प्रोफ़ाइल हटा दी गई।",
        "save_code_title": "आपका निजी सेव कोड",
        "save_code_intro": "इन्हें अभी नोट कर लें — ये केवल एक बार दिखाए जाते हैं, "
                           "सेवा इन्हें दोबारा नहीं दिखाएगी।",
        "save_code_warn": "इसे निजी रखें। इन विवरणों से कोई भी आपकी सहेजी गई "
                          "प्रोफ़ाइल देख या हटा सकता है। यह MVP निजी सेव कोड का "
                          "उपयोग करता है — लॉगिन खाता नहीं।",
        "profile_summary_title": "आपकी प्रोफ़ाइल",
        "save_guidance": "सहेजें दबाने तक आपकी प्रोफ़ाइल केवल इस ब्राउज़र सत्र में "
                         "रहती है। निजी सेव कोड से आप इसे किसी अन्य डिवाइस पर "
                         "पुनः लोड कर सकते हैं।",
        "profile_empty_title": "अभी कोई प्रोफ़ाइल नहीं",
        "profile_empty": "अपनी प्रोफ़ाइल बनाने और सहेजने के लिए साइडबार का "
                         "उपयोग करें — या अपने निजी सेव कोड से लोड करें।",
        "save_load_guide_title": "सहेजना और लोड करना",
        "save_load_guide": '1. साइडबार में प्रोफ़ाइल बनाएं और "मेरी प्रोफ़ाइल '
                           'सहेजें" दबाएं। 2. एक बार दिखाए गए निजी सेव कोड को '
                           'नोट करें। 3. किसी अन्य डिवाइस पर साइडबार → "सहेजी गई '
                           'प्रोफ़ाइल लोड करें" से प्रोफ़ाइल आईडी और सेव कोड '
                           "दर्ज करें।",
        "privacy_title": "गोपनीयता",
        "privacy_note": "प्रोफ़ाइल केवल तभी सहेजी जाती है जब आप सहेजें चुनते हैं। "
                        "सेव कोड निजी है। कृपया आधार नंबर या संवेदनशील दस्तावेज़ "
                        "दर्ज न करें।",
        "mvp_note": "यह MVP निजी सेव कोड का उपयोग करता है — पूर्ण लॉगिन खाता नहीं।",
        "reset_session": "सत्र रीसेट करें",
        "reset_done": "सत्र रीसेट हो गया।",
        "language_label": "भाषा",
        "err_timeout": "सेवा को उत्तर देने में बहुत समय लगा। कृपया पुनः प्रयास करें।",
        "err_unreachable": "हम SchemeGPT सेवा तक नहीं पहुँच सके। कृपया जांचें कि "
                           "सेवा चालू है और पुनः प्रयास करें।",
        "err_bad_response": "सेवा ने एक अप्रत्याशित प्रतिक्रिया दी।",
        "err_generic": "कुछ गड़बड़ हुई। कृपया पुनः प्रयास करें।",
        "err_profile_auth": "प्रोफ़ाइल नहीं मिली, या सेव कोड गलत है। कृपया दोनों "
                            "जांचकर पुनः प्रयास करें।",
        "err_validation": "कुछ विवरण सहेजे नहीं जा सके। कृपया मान जांचकर पुनः "
                          "प्रयास करें।",
        "err_missing_id_token": "कृपया प्रोफ़ाइल आईडी और सेव कोड दोनों दर्ज करें।",
        "err_empty_profile": "सहेजने से पहले कम से कम एक विवरण जोड़ें।",
        "err_states_shape": "राज्यों की सूची अपेक्षित नहीं थी; अंतर्निर्मित "
                            "वैकल्पिक सूची दिखाई जा रही है।",
        "err_states_unreachable": "हम सेवा से राज्यों की सूची लोड नहीं कर सके। "
                                  "अंतर्निर्मित वैकल्पिक सूची दिखाई जा रही है।",
        "err_chat_fallback": "सेवा अभी अस्थायी रूप से अनुपलब्ध है। कृपया पुनः "
                             "प्रयास करें।",
        "empty_answer": "सेवा ने खाली उत्तर दिया। कृपया कोई और प्रश्न पूछें।",
        "age_unit": "वर्ष",
    },
}


def _t(key: str) -> str:
    """Look up the current-language string for ``key`` (English fallback)."""
    lang = st.session_state.get("lang", "en")
    lang = "hi" if lang == "hi" else "en"
    return T[lang].get(key, T["en"].get(key, key))


def _esc(value) -> str:
    """HTML-escape a value so user/AI text can never break out of cards."""
    return html.escape(str(value if value is not None else ""))


# ---------------------------------------------------------------------------
# Inline visual system (no external assets, no build step)
# ---------------------------------------------------------------------------
CSS = """
<style>
:root {
  --cp-bg: #0a1120;
  --cp-bg-soft: #0d1526;
  --cp-surface: #111c33;
  --cp-surface-2: #16233f;
  --cp-border: #22304f;
  --cp-text: #e8eef8;
  --cp-muted: #94a3c0;
  --cp-saffron: #f5a623;
  --cp-saffron-soft: #ffc75f;
  --cp-mint: #3ddc97;
  --cp-mint-soft: #6fe8b4;
  --cp-coral: #ff6b6b;
  --cp-coral-soft: #ff9c9c;
}

html, body, .stApp { overflow-x: hidden; }

.stApp, [data-testid="stAppViewContainer"] {
  background-color: var(--cp-bg);
  color: var(--cp-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", "Noto Sans", Arial, sans-serif;
}

[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stStatusWidget"] { display: none; }

[data-testid="stSidebar"] {
  background-color: var(--cp-bg-soft);
  border-right: 1px solid var(--cp-border);
}

.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 1120px;
  padding-top: 2.2rem;
  padding-bottom: 6rem;
}

h1, h2, h3 { color: var(--cp-text); letter-spacing: -0.01em; }
p, li, label { color: var(--cp-text); }
a { color: var(--cp-mint); }

[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] { color: var(--cp-muted) !important; }
[data-testid="stCaptionContainer"] p { color: var(--cp-muted) !important; }
input::placeholder, textarea::placeholder { color: var(--cp-muted); opacity: 1; }

/* Buttons */
[data-testid="stBaseButton-primary"], button[kind="primary"] {
  background-color: var(--cp-saffron);
  color: #1a1205;
  border: none;
  border-radius: 10px;
  font-weight: 650;
}
[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover {
  background-color: var(--cp-saffron-soft);
  color: #1a1205;
  border: none;
}
[data-testid="stBaseButton-secondary"], button[kind="secondary"] {
  background-color: transparent;
  color: var(--cp-text);
  border: 1px solid var(--cp-border);
  border-radius: 10px;
}
[data-testid="stBaseButton-secondary"]:hover, button[kind="secondary"]:hover {
  border-color: var(--cp-saffron);
  color: var(--cp-saffron-soft);
}
[data-testid="stBaseButton-tertiary"], button[kind="tertiary"] {
  background-color: transparent;
  color: var(--cp-muted);
  border: none;
}
button:focus-visible,
[data-testid="stBaseButton-primary"]:focus-visible,
[data-testid="stBaseButton-secondary"]:focus-visible,
[data-testid="stBaseButton-tertiary"]:focus-visible,
[data-testid="stSelectbox"] [data-baseweb="select"]:focus-within,
[data-testid="stTextInput"] input:focus-visible,
[data-testid="stNumberInput"] input:focus-visible {
  outline: 2px solid var(--cp-saffron);
  outline-offset: 2px;
}

/* Inputs */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stChatInput"] textarea {
  background-color: var(--cp-bg-soft) !important;
  border: 1px solid var(--cp-border) !important;
  color: var(--cp-text) !important;
  border-radius: 10px;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stChatInput"] textarea:focus {
  border-color: var(--cp-saffron) !important;
}

[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
  background-color: var(--cp-bg-soft) !important;
  border-color: var(--cp-border) !important;
  border-radius: 10px;
  color: var(--cp-text) !important;
}
[data-testid="stSelectbox"] div[data-baseweb="select"] div[dir="auto"],
[data-testid="stMultiSelect"] div[data-baseweb="select"] div[dir="auto"] {
  color: var(--cp-text) !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] input,
[data-testid="stMultiSelect"] [data-baseweb="select"] input {
  color: var(--cp-text) !important;
}
[data-baseweb="popover"] [data-baseweb="menu"],
[data-testid="stSelectbox"] [data-baseweb="popover"] ul,
[data-testid="stMultiSelect"] [data-baseweb="popover"] ul {
  background-color: var(--cp-surface-2) !important;
}
[data-baseweb="menu"] li, [data-baseweb="menu"] li[role="option"] {
  color: var(--cp-text) !important;
}

/* Radio + checkbox */
[data-testid="stRadio"] label, [data-testid="stCheckbox"] label {
  color: var(--cp-text);
}

/* Expander */
[data-testid="stExpander"] {
  background-color: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 12px;
}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p {
  color: var(--cp-text);
}
[data-testid="stExpander"] details[aria-expanded="true"] summary,
[data-testid="stExpander"] details[aria-expanded="true"] summary p {
  color: var(--cp-saffron-soft);
}

/* Tabs */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 6px;
  border-bottom: 1px solid var(--cp-border);
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  color: var(--cp-muted);
  border-radius: 10px 10px 0 0;
  font-weight: 600;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover { color: var(--cp-saffron-soft); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--cp-saffron); }

/* Alerts + spinner */
[data-testid="stAlert"] {
  background-color: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 12px;
  color: var(--cp-text);
}
[data-testid="stAlert"] p { color: var(--cp-text); }
[data-testid="stSpinner"] { color: var(--cp-muted); }

/* Chat */
[data-testid="stChatMessage"] {
  background-color: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 14px;
  padding: 0.6rem 0.9rem;
  margin-bottom: 0.5rem;
}
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] p {
  color: var(--cp-text);
}
[data-testid="stChatInput"] {
  border: 1px solid var(--cp-border);
  border-radius: 14px;
  background-color: var(--cp-bg-soft);
}
[data-testid="stChatInputSubmitButton"] button {
  background-color: var(--cp-saffron);
  color: #1a1205;
  border-radius: 10px;
}

/* Form */
[data-testid="stForm"] { border: none; padding: 0; }

/* ---------- Custom components ---------- */
.cp-eyebrow {
  color: var(--cp-saffron);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  margin-bottom: 0.3rem;
}
.cp-hero h1 {
  font-size: 2.6rem;
  line-height: 1.12;
  margin: 0.2rem 0 0.5rem;
  letter-spacing: -0.02em;
}
.cp-hero > p {
  color: var(--cp-muted);
  font-size: 1.08rem;
  max-width: 660px;
  margin: 0 0 1rem;
}
.cp-hero-row { margin: 0.6rem 0 1.2rem; }

.cp-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.22rem 0.75rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.5;
  white-space: nowrap;
  vertical-align: middle;
}
.cp-pill-saffron { background: rgba(245,166,35,0.13); color: var(--cp-saffron-soft); border: 1px solid rgba(245,166,35,0.4); }
.cp-pill-mint { background: rgba(61,220,151,0.13); color: var(--cp-mint-soft); border: 1px solid rgba(61,220,151,0.4); }
.cp-pill-coral { background: rgba(255,107,107,0.13); color: var(--cp-coral-soft); border: 1px solid rgba(255,107,107,0.4); }
.cp-pill-neutral { background: rgba(148,163,192,0.14); color: var(--cp-muted); border: 1px solid rgba(148,163,192,0.35); }

.cp-steps {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.4rem;
}
.cp-step {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 12px;
  padding: 0.55rem 0.85rem;
  min-width: 0;
}
.cp-step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 999px;
  background: rgba(245,166,35,0.15);
  color: var(--cp-saffron-soft);
  font-weight: 700;
  font-size: 0.8rem;
  flex-shrink: 0;
}
.cp-step-text { display: flex; flex-direction: column; line-height: 1.3; }
.cp-step-text b { color: var(--cp-text); font-weight: 650; font-size: 0.92rem; }
.cp-step-sub { color: var(--cp-muted); font-size: 0.78rem; }
.cp-step-arrow { color: var(--cp-saffron); font-weight: 700; align-self: center; }

.cp-side-title {
  color: var(--cp-saffron);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin: 0.4rem 0 0.4rem;
}
.cp-hr { border: none; border-top: 1px solid var(--cp-border); margin: 0.8rem 0; }

.cp-card {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 14px;
  padding: 0.9rem 1rem;
}
.cp-card p { color: var(--cp-muted); font-size: 0.82rem; line-height: 1.55; margin: 0.4rem 0 0; }
.cp-card b { color: var(--cp-text); }

.cp-sec-heading {
  color: var(--cp-saffron);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  margin: 0.9rem 0 0.5rem;
}

details.cp-source-card {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 12px;
  padding: 0.5rem 0.85rem;
  margin: 0.4rem 0;
}
details.cp-source-card summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
details.cp-source-card summary::-webkit-details-marker { display: none; }
details.cp-source-card summary::before { content: "▸"; color: var(--cp-muted); }
details.cp-source-card[open] summary::before { content: "▾"; }
.cp-src-name { color: var(--cp-text); font-weight: 650; font-size: 0.9rem; word-break: break-word; }
.cp-src-body { margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px dashed var(--cp-border); }
.cp-meta { color: var(--cp-muted); font-size: 0.82rem; line-height: 1.6; }
.cp-src-content {
  color: var(--cp-muted);
  font-size: 0.85rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0.5rem 0 0;
}

.cp-seed-label {
  background: rgba(255,107,107,0.12);
  border: 1px solid rgba(255,107,107,0.45);
  color: var(--cp-coral-soft);
  border-radius: 8px;
  padding: 0.25rem 0.6rem;
  font-size: 0.74rem;
  font-weight: 650;
  margin: 0.4rem 0;
  display: inline-block;
}

.cp-rec-card {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 14px;
  padding: 1rem 1.1rem;
  margin: 0.6rem 0;
}
.cp-rec-head { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.cp-rec-head h3 { margin: 0; font-size: 1.05rem; color: var(--cp-text); }
.cp-rec-reason { color: var(--cp-text); margin: 0.5rem 0 0; font-size: 0.92rem; }
.cp-rec-scope { color: var(--cp-muted); margin: 0.4rem 0 0; font-size: 0.88rem; overflow-wrap: anywhere; }
.cp-link {
  color: var(--cp-mint);
  text-decoration: none;
  font-weight: 600;
  font-size: 0.88rem;
  overflow-wrap: anywhere;
}
.cp-link:hover { text-decoration: underline; color: var(--cp-mint-soft); }

.cp-notice {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-left: 3px solid var(--cp-saffron);
  border-radius: 10px;
  padding: 0.55rem 0.8rem;
  color: var(--cp-muted);
  font-size: 0.85rem;
  line-height: 1.5;
  margin: 0.5rem 0;
}
.cp-notice b { color: var(--cp-text); }
.cp-notice-warn { border-left-color: var(--cp-coral); }
.cp-notice-ok { border-left-color: var(--cp-mint); }

.cp-save-code {
  background: linear-gradient(180deg, rgba(245,166,35,0.12), rgba(245,166,35,0.03));
  border: 1px solid rgba(245,166,35,0.5);
  border-radius: 14px;
  padding: 0.9rem 1rem;
  margin: 0.6rem 0;
}
.cp-save-code-title { color: var(--cp-saffron-soft); font-weight: 700; font-size: 0.95rem; }
.cp-save-code p { color: var(--cp-muted); font-size: 0.82rem; line-height: 1.5; margin: 0.4rem 0; }
.cp-save-row {
  display: flex;
  justify-content: space-between;
  gap: 0.6rem;
  align-items: center;
  margin: 0.3rem 0;
  font-size: 0.8rem;
  color: var(--cp-muted);
}
.cp-save-row code {
  background: rgba(10,17,32,0.6);
  border: 1px solid rgba(245,166,35,0.3);
  color: var(--cp-saffron-soft);
  border-radius: 6px;
  padding: 0.15rem 0.5rem;
  word-break: break-all;
  font-size: 0.78rem;
}
.cp-save-code-warn { color: var(--cp-coral-soft) !important; }

.cp-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.6rem 0; }
.cp-chip {
  background: var(--cp-bg-soft);
  border: 1px solid var(--cp-border);
  border-radius: 10px;
  padding: 0.35rem 0.7rem;
  display: inline-flex;
  flex-direction: column;
  gap: 0.1rem;
}
.cp-chip b { color: var(--cp-muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 650; }
.cp-chip span { color: var(--cp-text); font-size: 0.88rem; }

.cp-empty {
  background: var(--cp-surface);
  border: 1px dashed var(--cp-border);
  border-radius: 14px;
  padding: 1.4rem 1.4rem;
  color: var(--cp-muted);
}
.cp-empty b { color: var(--cp-text); font-size: 1.05rem; }
.cp-empty p { margin: 0.4rem 0 0; color: var(--cp-muted); }

.cp-foot { color: var(--cp-muted); font-size: 0.8rem; line-height: 1.55; }

/* Responsive */
@media (max-width: 768px) {
  .block-container { padding: 1.2rem 1rem 5rem; }
  .cp-hero h1 { font-size: 1.9rem; }
  .cp-hero > p { font-size: 0.98rem; }
  .cp-steps { flex-direction: column; align-items: stretch; }
  .cp-step-arrow { transform: rotate(90deg); align-self: center; }
}
@media (max-width: 480px) {
  .cp-hero h1 { font-size: 1.6rem; }
  .cp-save-row { flex-direction: column; align-items: flex-start; }
}
</style>
"""


# ---------------------------------------------------------------------------
# API helpers (requests + timeouts + safe, localized error handling)
# ---------------------------------------------------------------------------
class ApiError(Exception):
    """A user-safe error; ``message`` is always a fixed, localized string."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _validation_msgs(payload) -> list[str]:
    """Sanitized validation detail lines (no secrets, no raw bodies)."""
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, list):
        return []
    out: list[str] = []
    for item in detail:
        if not isinstance(item, dict):
            continue
        loc = [str(part) for part in item.get("loc", []) if str(part) != "body"]
        msg = str(item.get("msg", "")).strip()
        if not msg:
            continue
        out.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
    return out


def _detail_text(resp: requests.Response) -> str:
    """Best-effort, user-safe message for a non-2xx response.

    Only sanitized Pydantic validation details for HTTP 422 are surfaced (via
    ``_validation_msgs``). Every other 4xx returns the fixed localized generic
    error, so raw proxy/internal/database ``detail`` text from a payload is
    never rendered.
    """
    status = resp.status_code
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if status in (401, 404):
        return _t("err_profile_auth")
    if status == 422:
        details = _validation_msgs(payload)
        if details:
            return _t("err_validation") + " " + "; ".join(details[:2])
        return _t("err_validation")
    return _t("err_generic")


def _api_json(method: str, path: str, *, json=None, headers=None, timeout=None):
    """Perform an API call and return parsed JSON, or raise a user-safe ApiError."""
    url = f"{API_URL}{path}"
    try:
        resp = requests.request(
            method,
            url,
            json=json,
            headers=headers,
            timeout=timeout or REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise ApiError(_t("err_timeout"))
    except requests.RequestException:
        raise ApiError(_t("err_unreachable"))
    if resp.status_code >= 400:
        raise ApiError(_detail_text(resp), status_code=resp.status_code)
    try:
        return resp.json()
    except ValueError:
        raise ApiError(_t("err_bad_response"))


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
_FORM_KEYS = (
    "pf_display_name", "pf_state", "pf_age", "pf_income", "pf_occupation",
    "pf_category", "pf_gender", "pf_area", "pf_disability", "pf_family_size",
    "pf_goals",
)


def _init_session() -> None:
    ss = st.session_state
    ss.setdefault("lang", "en")
    ss.setdefault("messages", [])
    ss.setdefault("profile", None)
    ss.setdefault("profile_id", None)
    ss.setdefault("access_token", None)
    ss.setdefault("last_created", None)
    ss.setdefault("states", None)
    ss.setdefault("states_error", None)
    ss.setdefault("matches", None)


def _reset_session() -> None:
    ss = st.session_state
    for key in (
        "messages", "profile", "profile_id", "access_token", "last_created",
        "matches", "delete_confirm", "load_pid", "load_tok", "match_q",
    ):
        ss.pop(key, None)
    for key in _FORM_KEYS:
        ss.pop(key, None)
    ss["flash"] = _t("reset_done")


def _on_lang_change() -> None:
    st.session_state["lang"] = st.session_state.get("lang_selector", "en")


# ---------------------------------------------------------------------------
# States catalog
# ---------------------------------------------------------------------------
def _fallback_states() -> list[dict]:
    return [{"name": name} for name in FALLBACK_STATE_NAMES]


def _load_states() -> list[dict]:
    ss = st.session_state
    cached = ss.get("states")
    if cached is not None:
        return cached
    try:
        data = _api_json("GET", "/states", timeout=PROFILE_TIMEOUT)
    except ApiError as exc:
        ss["states_error"] = exc.message
        ss["states"] = _fallback_states()
        return ss["states"]
    if isinstance(data, list) and data and all(
        isinstance(item, dict) for item in data
    ):
        ss["states"] = data
        ss["states_error"] = None
    else:
        ss["states_error"] = _t("err_states_shape")
        ss["states"] = _fallback_states()
    return ss["states"]


def _coverage_pill_text() -> str:
    """Truthful coverage line from GET /coverage, falling back to static copy.

    Uses the endpoint when available (jurisdiction + verified-sample counts),
    otherwise the existing static `coverage` string. Cached per session so the
    request is made at most once. The line never claims all government schemes
    have been ingested.
    """
    ss = st.session_state
    if "coverage" not in ss:
        try:
            data = _api_json("GET", "/coverage", timeout=PROFILE_TIMEOUT)
            ss["coverage"] = (
                data
                if isinstance(data, dict) and data.get("jurisdiction_count")
                else None
            )
        except ApiError:
            ss["coverage"] = None
    data = ss.get("coverage")
    if data:
        return _t("coverage_live").format(
            j=int(data.get("jurisdiction_count") or 36),
            v=int(data.get("catalog_sample_verified_count") or 0),
        )
    return _t("coverage")


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------
def _index_of(options: list, value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return options.index(value)
    except ValueError:
        return default


def _label_formatter(labels: dict) -> Callable[[str], str]:
    """Return a STATELESS display formatter for a widget's raw option values.

    ``labels`` maps raw option values to their current-language display strings
    and is resolved once, at widget-creation time. This is important: Streamlit's
    test harness re-invokes ``format_func`` while serializing widget state, and a
    formatter that reads ``st.session_state`` lazily can then disagree with the
    option list that was rendered in the previous language. Capturing the strings
    here keeps options and formatter consistent in every run.
    """

    def _fmt(value: str) -> str:
        return labels.get(value, value)

    return _fmt


def _profile_from_form() -> dict:
    """Build a ProfileData payload from the current form widget values."""
    ss = st.session_state

    def clean(value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    profile: dict = {}
    name = clean(ss.get("pf_display_name"))
    if name:
        profile["display_name"] = name[:100]
    state = ss.get("pf_state")
    if state and state != _t("state_placeholder"):
        profile["state"] = str(state)[:80]
    age = ss.get("pf_age")
    if age:
        profile["age"] = int(age)
    income = ss.get("pf_income")
    if income is not None:
        profile["annual_income"] = float(income)
    occupation = clean(ss.get("pf_occupation"))
    if occupation:
        profile["occupation"] = occupation[:100]
    # Widgets store stable raw values ("" = none); localized labels are only
    # cosmetic (format_func), so no localized comparison is needed here.
    category = ss.get("pf_category")
    if category:
        profile["social_category"] = str(category)[:50]
    gender = ss.get("pf_gender")
    if gender:
        profile["gender"] = str(gender)[:50]
    # Area/disability widgets use a stable "" sentinel for "not specified /
    # prefer not to say": only explicit "Rural"/"Urban"/"Yes"/"No" raw values
    # map to True/False, so an unset field is omitted from the API payload
    # (None) and citizens are never forced to reveal these facts.
    area = ss.get("pf_area")
    if area == "Rural":
        profile["rural"] = True
    elif area == "Urban":
        profile["rural"] = False
    disability = ss.get("pf_disability")
    if disability == "Yes":
        profile["disability"] = True
    elif disability == "No":
        profile["disability"] = False
    family = ss.get("pf_family_size")
    if family:
        profile["family_size"] = int(family)
    goals = ss.get("pf_goals") or []
    if goals:
        profile["goals"] = [str(goal)[:60] for goal in goals][:20]
    profile["language"] = ss.get("lang", "en")
    return profile


def _profile_has_content(profile: dict) -> bool:
    return any(
        value not in (None, [], "")
        for key, value in profile.items()
        if key != "language"
    )


def _sync_form_from_profile(profile: dict | None) -> None:
    ss = st.session_state
    p = profile or {}
    ss["pf_display_name"] = p.get("display_name")
    ss["pf_state"] = p.get("state")
    ss["pf_age"] = p.get("age")
    ss["pf_income"] = p.get("annual_income")
    ss["pf_occupation"] = p.get("occupation")
    ss["pf_category"] = p.get("social_category")
    ss["pf_gender"] = p.get("gender")
    rural = p.get("rural")
    ss["pf_area"] = "Rural" if rural is True else ("Urban" if rural is False else "")
    disability = p.get("disability")
    ss["pf_disability"] = "Yes" if disability is True else ("No" if disability is False else "")
    ss["pf_family_size"] = p.get("family_size")
    ss["pf_goals"] = p.get("goals") or []


def _save_or_update_profile() -> None:
    ss = st.session_state
    payload = _profile_from_form()
    if not _profile_has_content(payload):
        st.warning(_t("err_empty_profile"))
        return
    try:
        if ss.get("profile_id") and ss.get("access_token"):
            data = _api_json(
                "PUT",
                f"/profiles/{ss['profile_id']}",
                json=payload,
                headers={"X-Profile-Token": ss["access_token"]},
                timeout=PROFILE_TIMEOUT,
            )
            st.success(_t("profile_updated"))
        else:
            data = _api_json("POST", "/profiles", json=payload, timeout=PROFILE_TIMEOUT)
            ss["profile_id"] = data.get("profile_id")
            ss["access_token"] = data.get("access_token")
            ss["last_created"] = {
                "profile_id": ss["profile_id"],
                "access_token": ss["access_token"],
            }
            st.success(_t("profile_saved"))
    except ApiError as exc:
        st.error(exc.message)
        return
    ss["profile"] = data.get("profile") or payload
    ss["matches"] = None  # cached matches are now stale


def _load_profile() -> None:
    ss = st.session_state
    pid = str(ss.get("load_pid") or "").strip()
    token = str(ss.get("load_tok") or "").strip()
    if not pid or not token:
        st.error(_t("err_missing_id_token"))
        return
    try:
        data = _api_json(
            "GET",
            f"/profiles/{pid}",
            headers={"X-Profile-Token": token},
            timeout=PROFILE_TIMEOUT,
        )
    except ApiError as exc:
        st.error(exc.message)
        return
    profile = data.get("profile") or {}
    ss["profile"] = profile
    ss["profile_id"] = pid
    ss["access_token"] = token
    ss["last_created"] = None
    ss["matches"] = None
    ss["pending_profile"] = profile
    ss["flash"] = _t("profile_loaded")
    st.rerun()


def _delete_profile() -> None:
    ss = st.session_state
    try:
        _api_json(
            "DELETE",
            f"/profiles/{ss['profile_id']}",
            headers={"X-Profile-Token": ss["access_token"]},
            timeout=PROFILE_TIMEOUT,
        )
        st.success(_t("profile_deleted"))
    except ApiError as exc:
        st.error(exc.message)
        return
    for key in ("profile", "profile_id", "access_token", "last_created",
                "matches", "delete_confirm"):
        ss.pop(key, None)


# ---------------------------------------------------------------------------
# Small HTML component builders
# ---------------------------------------------------------------------------
def _pill(text: str, kind: str = "neutral") -> str:
    return f'<span class="cp-pill cp-pill-{kind}">{_esc(text)}</span>'


def _data_status_label(data_status) -> str:
    t = _t
    status = str(data_status or "").strip().lower()
    if status == "sample_verified":
        return t("status_sample")
    if status in ("directory_seed", "seed"):
        return t("status_seed")
    if not status:
        return t("status_unknown")
    return str(data_status)


def _notice_card(title: str, body: str, kind: str = "warn") -> str:
    return (
        f'<div class="cp-notice cp-notice-{kind}"><b>{_esc(title)}</b>'
        f'<div>{_esc(body)}</div></div>'
    )


def _source_card(src: dict) -> str:
    t = _t
    name = str(src.get("source") or t("source_unknown"))
    data_status = str(src.get("data_status") or "").strip()
    is_seed = data_status == "directory_seed"
    jurisdiction = src.get("jurisdiction")
    state = src.get("state")
    last_verified = src.get("last_verified")
    source_url = src.get("source_url")
    content = str(src.get("content") or "")

    status_pill = _pill(_data_status_label(data_status), "saffron" if is_seed else "mint")

    meta: list[str] = []
    if jurisdiction:
        meta.append(f"{_esc(t('jurisdiction'))}: {_esc(jurisdiction)}")
    if state and state != jurisdiction:
        meta.append(f"{_esc(t('state'))}: {_esc(state)}")
    if last_verified:
        meta.append(f"{_esc(t('verified'))}: {_esc(last_verified)}")
    meta_html = " · ".join(meta)

    url_html = ""
    if source_url:
        url_html = (
            f'<div style="margin-top:0.4rem"><a class="cp-link" '
            f'href="{_esc(source_url)}" target="_blank" rel="noopener noreferrer">'
            f'{_esc(t("official_source"))}</a></div>'
        )

    seed_html = f'<div class="cp-seed-label">{_esc(t("seed_label"))}</div>' if is_seed else ""
    content_html = f'<p class="cp-src-content">{_esc(content)}</p>' if content.strip() else ""

    return (
        f'<details class="cp-source-card">'
        f'<summary><span class="cp-src-name">{_esc(name)}</span> {status_pill}</summary>'
        f'<div class="cp-src-body">{seed_html}'
        f'<div class="cp-meta">{meta_html}</div>{url_html}{content_html}</div>'
        f'</details>'
    )


def _recommendation_card(rec: dict) -> str:
    t = _t
    name = str(rec.get("name") or t("rec_unknown"))
    jurisdiction = rec.get("jurisdiction")
    reason = str(rec.get("reason") or "")
    scope = str(rec.get("benefits_or_scope") or "")
    data_status = str(rec.get("data_status") or "").strip()
    last_verified = rec.get("last_verified")
    is_seed = data_status == "directory_seed"

    status_pill = _pill(_data_status_label(data_status), "saffron" if is_seed else "mint")
    seed_html = f'<div class="cp-seed-label">{_esc(t("seed_label"))}</div>' if is_seed else ""

    meta: list[str] = []
    if jurisdiction:
        meta.append(f"{_esc(t('jurisdiction'))}: {_esc(jurisdiction)}")
    if last_verified:
        meta.append(f"{_esc(t('verified'))}: {_esc(last_verified)}")
    meta_html = " · ".join(meta)

    source_url = rec.get("source_url")
    if source_url:
        link_label = t("official_source")
    else:
        source_url = OFFICIAL_PORTAL_URL
        link_label = t("official_portal")
    link_html = (
        f'<div style="margin-top:0.5rem"><a class="cp-link" href="{_esc(source_url)}" '
        f'target="_blank" rel="noopener noreferrer">{_esc(link_label)}</a></div>'
    )

    reason_html = (
        f'<p class="cp-rec-reason"><b>{_esc(t("reason"))}:</b> {_esc(reason)}</p>'
        if reason
        else ""
    )
    scope_html = (
        f'<p class="cp-rec-scope"><b>{_esc(t("scope"))}:</b> {_esc(scope)}</p>'
        if scope
        else ""
    )

    return (
        f'<div class="cp-rec-card">'
        f'<div class="cp-rec-head"><h3>{_esc(name)}</h3> {status_pill}</div>'
        f'{seed_html}'
        f'<div class="cp-meta">{meta_html}</div>'
        f'{reason_html}{scope_html}'
        f'{link_html}'
        f'</div>'
    )


def _save_code_card(created: dict) -> str:
    t = _t
    return (
        f'<div class="cp-save-code">'
        f'<div class="cp-save-code-title">{_esc(t("save_code_title"))}</div>'
        f'<p>{_esc(t("save_code_intro"))}</p>'
        f'<div class="cp-save-row"><span>{_esc(t("profile_id_field"))}</span>'
        f'<code>{_esc(created.get("profile_id") or "")}</code></div>'
        f'<div class="cp-save-row"><span>{_esc(t("save_code_label"))}</span>'
        f'<code>{_esc(created.get("access_token") or "")}</code></div>'
        f'<p class="cp-save-code-warn">{_esc(t("save_code_warn"))}</p>'
        f'</div>'
    )


def _profile_summary_html(profile: dict) -> str:
    t = _t
    p = profile or {}
    lang = st.session_state.get("lang", "en")
    pairs: list[tuple[str, str]] = []
    if p.get("display_name"):
        pairs.append((t("f_name"), str(p["display_name"])))
    if p.get("state"):
        pairs.append((t("f_state"), str(p["state"])))
    if p.get("age") is not None:
        pairs.append((t("f_age"), f"{int(p['age'])} {t('age_unit')}"))
    if p.get("annual_income") is not None:
        pairs.append((t("f_income"), f"₹{float(p['annual_income']):,.0f}"))
    if p.get("occupation"):
        pairs.append((t("f_occupation"), str(p["occupation"])))
    if p.get("social_category"):
        raw_category = str(p["social_category"])
        category_label = (
            CATEGORY_LABELS_HI.get(raw_category, raw_category)
            if lang == "hi"
            else raw_category
        )
        pairs.append((t("f_category"), category_label))
    if p.get("gender"):
        raw_gender = str(p["gender"])
        gender_label = (
            GENDER_LABELS_HI.get(raw_gender, raw_gender)
            if lang == "hi"
            else raw_gender
        )
        pairs.append((t("f_gender"), gender_label))
    if p.get("rural") is True:
        pairs.append((t("f_area"), t("rural")))
    elif p.get("rural") is False:
        pairs.append((t("f_area"), t("urban")))
    if p.get("disability") is True:
        pairs.append((t("f_disability"), t("yes")))
    elif p.get("disability") is False:
        pairs.append((t("f_disability"), t("no")))
    if p.get("family_size") is not None:
        pairs.append((t("f_family"), str(int(p["family_size"]))))
    goals = p.get("goals") or []
    if goals:
        if lang == "hi":
            display_goals = ", ".join(
                GOAL_LABELS_HI.get(str(g), str(g)) for g in goals
            )
        else:
            display_goals = ", ".join(str(g) for g in goals)
        pairs.append((t("f_goals"), display_goals))
    if not pairs:
        return ""
    chips = "".join(
        f'<span class="cp-chip"><b>{_esc(label)}</b><span>{_esc(value)}</span></span>'
        for label, value in pairs
    )
    return f'<div class="cp-chips">{chips}</div>'


# ---------------------------------------------------------------------------
# Chat rendering
# ---------------------------------------------------------------------------
def _render_mode_notice(item: dict) -> None:
    mode = item.get("mode")
    if mode == "demo":
        st.markdown(_pill(_t("demo_pill"), "coral"), unsafe_allow_html=True)
        notice = item.get("notice")
        if notice:
            st.markdown(
                f'<div class="cp-notice cp-notice-warn">{_esc(notice)}</div>',
                unsafe_allow_html=True,
            )
    elif mode == "live":
        st.markdown(_pill(_t("live_pill"), "mint"), unsafe_allow_html=True)


def _render_sources(sources) -> None:
    items = [s for s in (sources or []) if isinstance(s, dict)]
    if not items:
        return
    st.markdown(
        f'<div class="cp-sec-heading">{_esc(_t("sources_label"))}</div>',
        unsafe_allow_html=True,
    )
    for src in items:
        st.markdown(_source_card(src), unsafe_allow_html=True)


def _render_message(msg: dict) -> None:
    role = "user" if msg.get("role") == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg.get("content", ""))
        if msg.get("error"):
            st.markdown(
                f'<div class="cp-notice cp-notice-warn">'
                f'{_esc(_t("err_chat_fallback"))}</div>',
                unsafe_allow_html=True,
            )
        elif msg.get("mode"):
            _render_mode_notice(msg)
            _render_sources(msg.get("sources") or [])


def _query_api(question: str):
    """POST /query; returns ``(data, error_message)``. Never raises."""
    ss = st.session_state
    payload: dict = {"question": question, "language": ss.get("lang", "en")}
    profile = ss.get("profile")
    if isinstance(profile, dict) and profile:
        payload["profile"] = profile
    try:
        data = _api_json("POST", "/query", json=payload, timeout=REQUEST_TIMEOUT)
    except ApiError as exc:
        return None, exc.message
    return data, None


def _submit_question(prompt: str) -> None:
    ss = st.session_state
    ss["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner(_t("thinking")):
            data, error = _query_api(prompt)
        if error or data is None:
            message = error or _t("err_chat_fallback")
            st.markdown(
                f'<div class="cp-notice cp-notice-warn">{_esc(message)}</div>',
                unsafe_allow_html=True,
            )
            ss["messages"].append({"role": "assistant", "content": message, "error": True})
            return
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            answer = _t("empty_answer")
        st.markdown(answer)
        _render_mode_notice(data)
        _render_sources(data.get("sources") or [])
        ss["messages"].append(
            {
                "role": "assistant",
                "content": answer,
                "mode": data.get("mode") or "live",
                "notice": data.get("notice"),
                "sources": data.get("sources") or [],
                "lang": data.get("language") or ss.get("lang", "en"),
            }
        )


# ---------------------------------------------------------------------------
# Main surface
# ---------------------------------------------------------------------------
def render_hero() -> None:
    t = _t
    st.markdown(
        f"""
        <div class="cp-hero">
          <div class="cp-eyebrow">{_esc(t("brand"))}</div>
          <h1>{_esc(t("hero_title"))}</h1>
          <p>{_esc(t("hero_sub"))}</p>
          <div class="cp-hero-row">
            <span class="cp-pill cp-pill-saffron">{_esc(_coverage_pill_text())}</span>
          </div>
          <div class="cp-steps">
            <span class="cp-step"><span class="cp-step-num">1</span>
              <span class="cp-step-text"><b>{_esc(t("step_tell"))}</b>
                <span class="cp-step-sub">{_esc(t("step_tell_sub"))}</span></span></span>
            <span class="cp-step-arrow" aria-hidden="true">→</span>
            <span class="cp-step"><span class="cp-step-num">2</span>
              <span class="cp-step-text"><b>{_esc(t("step_match"))}</b>
                <span class="cp-step-sub">{_esc(t("step_match_sub"))}</span></span></span>
            <span class="cp-step-arrow" aria-hidden="true">→</span>
            <span class="cp-step"><span class="cp-step-num">3</span>
              <span class="cp-step-text"><b>{_esc(t("step_verify"))}</b>
                <span class="cp-step-sub">{_esc(t("step_verify_sub"))}</span></span></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_profile_form() -> None:
    ss = st.session_state
    t = _t
    # A loaded profile must be written into the form widgets BEFORE they are
    # instantiated on this run; Streamlit forbids mutating a widget's session
    # state once the widget exists. _load_profile() therefore stages the data
    # here via st.rerun().
    pending = ss.pop("pending_profile", None)
    if pending:
        _sync_form_from_profile(pending)
    if ss.get("states_error"):
        st.markdown(
            f'<div class="cp-notice cp-notice-warn">{_esc(ss["states_error"])}</div>',
            unsafe_allow_html=True,
        )

    states = _load_states()
    state_names = [str(s.get("name") or "") for s in states if s.get("name")]
    state_opts = [t("state_placeholder")] + state_names
    state_index = _index_of(state_opts, ss.get("pf_state"), 0)

    # Raw sentinel values ("" = "none") keep the stored widget value stable
    # when toggling English/Hindi; localized labels are applied only via
    # format_func, mirroring the radio pattern above.
    category_opts = ["", "General", "OBC", "SC", "ST", "EWS"]
    category_index = _index_of(category_opts, ss.get("pf_category"), 0)
    category_labels = {"": t("category_none")}
    if ss.get("lang") == "hi":
        category_labels.update(CATEGORY_LABELS_HI)

    gender_opts = ["", "Female", "Male", "Other"]
    gender_index = _index_of(gender_opts, ss.get("pf_gender"), 0)
    gender_labels = {"": t("gender_none")}
    if ss.get("lang") == "hi":
        gender_labels.update(GENDER_LABELS_HI)

    goal_labels = (
        dict(GOAL_LABELS_HI)
        if ss.get("lang") == "hi"
        else {goal: goal for goal in GOAL_TAGS}
    )
    goal_selected = [g for g in (ss.get("pf_goals") or []) if g in GOAL_TAGS]

    with st.form("profile_form", border=False):
        st.selectbox(t("f_state"), state_opts, index=state_index, key="pf_state")
        st.text_input(
            t("f_name"),
            key="pf_display_name",
            placeholder=t("f_name_placeholder"),
        )
        col_a, col_b = st.columns(2)
        with col_a:
            st.number_input(
                t("f_age"),
                min_value=1,
                max_value=120,
                step=1,
                value=None,
                key="pf_age",
            )
        with col_b:
            st.number_input(
                t("f_income"),
                min_value=0.0,
                step=1000.0,
                format="%.0f",
                value=None,
                key="pf_income",
            )
        st.text_input(
            t("f_occupation"),
            key="pf_occupation",
            placeholder=t("f_occupation_placeholder"),
        )
        st.selectbox(
            t("f_category"),
            category_opts,
            index=category_index,
            format_func=_label_formatter(category_labels),
            key="pf_category",
        )
        st.selectbox(
            t("f_gender"),
            gender_opts,
            index=gender_index,
            format_func=_label_formatter(gender_labels),
            key="pf_gender",
        )
        st.radio(
            t("f_area"),
            ("", "Rural", "Urban"),
            index=_index_of(("", "Rural", "Urban"), ss.get("pf_area")),
            format_func=_label_formatter(
                {"": t("area_none"), "Rural": t("rural"), "Urban": t("urban")}
            ),
            key="pf_area",
            horizontal=True,
        )
        st.radio(
            t("f_disability"),
            ("", "Yes", "No"),
            index=_index_of(("", "Yes", "No"), ss.get("pf_disability")),
            format_func=_label_formatter(
                {"": t("disability_none"), "Yes": t("yes"), "No": t("no")}
            ),
            key="pf_disability",
            horizontal=True,
        )
        st.number_input(
            t("f_family"),
            min_value=1,
            max_value=100,
            step=1,
            value=None,
            key="pf_family_size",
        )
        st.multiselect(
            t("f_goals"),
            GOAL_TAGS,
            default=goal_selected,
            format_func=lambda goal: goal_labels.get(goal, goal),
            key="pf_goals",
        )
        st.caption(t("save_hint"))
        submitted = st.form_submit_button(
            t("save_profile"), type="primary", use_container_width=True
        )
    if submitted:
        _save_or_update_profile()


def _render_profile_section() -> None:
    ss = st.session_state
    t = _t
    st.markdown(
        f'<div class="cp-side-title">{_esc(t("profile_section"))}</div>',
        unsafe_allow_html=True,
    )
    if ss.get("profile_id") and ss.get("access_token"):
        st.markdown(_pill(t("connected_pill"), "mint"), unsafe_allow_html=True)
    elif ss.get("profile"):
        st.markdown(_pill(t("not_connected_pill"), "neutral"), unsafe_allow_html=True)

    if ss.get("last_created"):
        st.markdown(_save_code_card(ss["last_created"]), unsafe_allow_html=True)

    has_profile = bool(ss.get("profile"))
    expander_label = t("edit_profile") if has_profile else t("build_profile")
    with st.expander(expander_label, expanded=not has_profile):
        _render_profile_form()

    with st.expander(t("load_profile"), expanded=False):
        with st.form("load_form", border=False):
            st.text_input(t("profile_id_field"), key="load_pid")
            st.text_input(
                t("save_code_label"),
                type="password",
                key="load_tok",
                help=t("save_code_help"),
            )
            if st.form_submit_button(
                t("load_btn"), type="secondary", use_container_width=True
            ):
                _load_profile()

    if ss.get("profile_id") and ss.get("access_token"):
        st.markdown('<div style="height:0.4rem"></div>', unsafe_allow_html=True)
        confirm = st.checkbox(t("delete_confirm"), key="delete_confirm", value=False)
        if st.button(
            t("delete_profile"),
            key="delete_btn",
            use_container_width=True,
            disabled=not confirm,
        ):
            _delete_profile()


def render_sidebar() -> None:
    ss = st.session_state
    with st.sidebar:
        flash = ss.pop("flash", None)
        if flash:
            st.success(flash)

        st.markdown(
            f'<div class="cp-side-title">{_esc(_t("language_label"))}</div>',
            unsafe_allow_html=True,
        )
        st.radio(
            "lang",
            ("en", "hi"),
            index=0 if ss.get("lang", "en") == "en" else 1,
            format_func=lambda code: "English" if code == "en" else "हिंदी",
            key="lang_selector",
            on_change=_on_lang_change,
            label_visibility="collapsed",
            horizontal=True,
        )
        st.markdown('<hr class="cp-hr">', unsafe_allow_html=True)

        _render_profile_section()

        st.markdown('<hr class="cp-hr">', unsafe_allow_html=True)
        st.markdown(
            f'<div class="cp-card cp-foot"><b>{_esc(_t("privacy_title"))}</b>'
            f'<p>{_esc(_t("privacy_note"))}</p>'
            f'<p>{_esc(_t("mvp_note"))}</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="cp-card cp-foot" style="margin-top:0.5rem">'
            f'<b>{_esc(_t("disclaimer_title"))}</b>'
            f'<p>{_esc(_t("disclaimer_body"))}</p></div>',
            unsafe_allow_html=True,
        )
        if st.button(
            _t("reset_session"), key="reset_btn", use_container_width=True
        ):
            _reset_session()
            st.rerun()


def render_ask_tab() -> None:
    ss = st.session_state
    if not ss.get("messages"):
        st.markdown(
            f'<div class="cp-empty"><b>{_esc(_t("ask_empty_title"))}</b>'
            f'<p>{_esc(_t("ask_empty_body"))}</p></div>',
            unsafe_allow_html=True,
        )
    for msg in ss.get("messages", []):
        _render_message(msg)
    prompt = st.chat_input(_t("ask_placeholder"), key="chat_input")
    if prompt:
        _submit_question(prompt)


def _fetch_matches(question: str | None) -> None:
    ss = st.session_state
    profile = ss.get("profile")
    if not isinstance(profile, dict) or not profile:
        return
    payload = {
        "profile": profile,
        "question": (question or "").strip() or None,
        "language": ss.get("lang", "en"),
    }
    with st.spinner(_t("matching_spinner")):
        try:
            data = _api_json("POST", "/recommendations", json=payload, timeout=60)
        except ApiError as exc:
            st.error(exc.message)
            return
    items = [rec for rec in (data.get("recommendations") or []) if isinstance(rec, dict)]
    ss["matches"] = {
        "items": items,
        "disclaimer": data.get("disclaimer") or "",
        "profile_state": data.get("profile_state"),
    }


def render_matches_tab() -> None:
    ss = st.session_state
    t = _t
    profile = ss.get("profile")
    if not isinstance(profile, dict) or not profile:
        st.markdown(
            f'<div class="cp-empty"><b>{_esc(t("matches_empty_title"))}</b>'
            f'<p>{_esc(t("matches_empty_body"))}</p></div>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(f'<div class="cp-meta">{_esc(t("match_hint"))}</div>', unsafe_allow_html=True)
    priority = st.text_input(t("match_question"), key="match_q")
    if st.button(
        t("find_matches"), key="find_matches_btn", type="primary",
        use_container_width=True,
    ):
        _fetch_matches(priority)

    matches = ss.get("matches")
    if not isinstance(matches, dict):
        return
    items = matches.get("items") or []
    if not items:
        st.markdown(f'<div class="cp-empty">{_esc(t("match_none"))}</div>', unsafe_allow_html=True)
    for rec in items:
        st.markdown(_recommendation_card(rec), unsafe_allow_html=True)
    disclaimer = matches.get("disclaimer") or t("disclaimer_body")
    st.markdown(
        _notice_card(t("disclaimer_title"), disclaimer, "warn"),
        unsafe_allow_html=True,
    )


def render_profile_tab() -> None:
    ss = st.session_state
    t = _t
    if ss.get("last_created"):
        st.markdown(_save_code_card(ss["last_created"]), unsafe_allow_html=True)
        st.markdown('<hr class="cp-hr">', unsafe_allow_html=True)

    profile = ss.get("profile")
    if isinstance(profile, dict) and profile:
        st.markdown(
            f'<div class="cp-sec-heading">{_esc(t("profile_summary_title"))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(_profile_summary_html(profile), unsafe_allow_html=True)
        connected = bool(ss.get("profile_id") and ss.get("access_token"))
        st.markdown(
            _pill(
                t("connected_pill") if connected else t("not_connected_pill"),
                "mint" if connected else "neutral",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p class="cp-foot" style="margin-top:0.7rem">{_esc(t("save_guidance"))}</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="cp-empty"><b>{_esc(t("profile_empty_title"))}</b>'
            f'<p>{_esc(t("profile_empty"))}</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div class="cp-sec-heading">{_esc(t("save_load_guide_title"))}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="cp-foot">{_esc(t("save_load_guide"))}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    _init_session()
    render_sidebar()
    render_hero()
    tab_ask, tab_matches, tab_profile = st.tabs(
        [_t("tab_ask"), _t("tab_matches"), _t("tab_profile")]
    )
    with tab_ask:
        render_ask_tab()
    with tab_matches:
        render_matches_tab()
    with tab_profile:
        render_profile_tab()


st.set_page_config(
    page_title="SchemeGPT",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CSS, unsafe_allow_html=True)

main()



