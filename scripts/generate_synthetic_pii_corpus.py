"""Generate a deterministic, entirely synthetic Indian-PII corpus.

The corpus is the frozen input for the offline PII benchmark
(``eval/pii_benchmark.py``). It is built here -- never by running the
recognizers -- so the benchmark is not circular:

* every positive record is assembled from a **known-good value** constructed by
  this script, and its labelled span is recorded at construction time (the
  string is concatenated and the slice ``[start:end]`` is known by construction,
  not by scanning);
* a valid Aadhaar is built from a seeded payload plus a Verhoeff check digit
  computed by this script's own, independent Verhoeff implementation -- not the
  recognizer's -- so a bug in the recognizer cannot be masked by the generator
  sharing it;
* negatives are near-misses that must not match: Aadhaar-shaped values whose
  checksum fails, malformed PANs, ten-digit numbers starting 0-5, an Aadhaar
  embedded in a longer digit run, and alternating high-entropy tokens.

Everything is synthetic. Digits come from a seeded ``random.Random``; no real
person's identifier is generated, emitted, or committed. The output is
byte-stable for a fixed seed: no timestamp or environment value is written.

Run::

    python scripts/generate_synthetic_pii_corpus.py
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = ROOT / "eval" / "fixtures" / "pii_synthetic_corpus.jsonl"

SEED = 20261005
GENERATOR = "scripts/generate_synthetic_pii_corpus.py"

KIND_AADHAAR = "aadhaar"
KIND_PAN = "pan"
KIND_GSTIN = "gstin"
KIND_IFSC = "ifsc"
KIND_UPI = "upi"
KIND_MOBILE = "mobile"
KIND_DEVANAGARI_DIGITS = "devanagari_digits"

_UPI_HANDLES = ("okhdfcbank", "okaxis", "paytm", "ybl", "okicici", "upi")
_UPI_LOCALS = ("priya.sharma", "9876543210", "ravi", "field.ops", "citizen1")

_ASCII_TO_DEVANAGARI = {
    str(index): chr(0x0966 + index) for index in range(10)
}


# --------------------------------------------------------------------------
# Independent Verhoeff implementation (deliberately not the recognizer's)
# --------------------------------------------------------------------------

_VP = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VD = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VINV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def _check_digit(payload: str) -> int:
    checksum = 0
    for index, char in enumerate(reversed(payload)):
        checksum = _VD[checksum][_VP[(index + 1) % 8][int(char)]]
    return _VINV[checksum]


def _verhoeff_ok(digits: str) -> bool:
    checksum = 0
    for index, char in enumerate(reversed(digits)):
        checksum = _VD[checksum][_VP[index % 8][int(char)]]
    return checksum == 0


def _to_devanagari(value: str) -> str:
    return "".join(_ASCII_TO_DEVANAGARI.get(char, char) for char in value)


# --------------------------------------------------------------------------
# Seeded value builders
# --------------------------------------------------------------------------


def _digits(rng: random.Random, count: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(count))


def _letters(rng: random.Random, count: int) -> str:
    return "".join(rng.choice(string.ascii_uppercase) for _ in range(count))


def build_aadhaar(rng: random.Random) -> str:
    """A valid 12-digit Aadhaar: 11-digit payload (2-9 lead) + check digit."""
    payload = rng.choice("23456789") + _digits(rng, 10)
    return payload + str(_check_digit(payload))


def build_aadhaar_near_miss(rng: random.Random) -> str:
    """A 12-digit value that is guaranteed to fail its Verhoeff checksum."""
    payload = rng.choice("23456789") + _digits(rng, 10)
    wrong = (_check_digit(payload) + 1) % 10
    value = payload + str(wrong)
    assert not _verhoeff_ok(value)  # there is exactly one valid check digit
    return value


def build_pan(rng: random.Random) -> str:
    return _letters(rng, 5) + _digits(rng, 4) + _letters(rng, 1)


def build_gstin(rng: random.Random) -> str:
    # 2 state digits + PAN (10) + 3-character entity code = 15.
    return _digits(rng, 2) + build_pan(rng) + _letters(rng, 3)


def build_ifsc(rng: random.Random) -> str:
    return _letters(rng, 4) + "0" + _letters(rng, 3) + _digits(rng, 3)


def build_upi(rng: random.Random) -> str:
    return f"{rng.choice(_UPI_LOCALS)}@{rng.choice(_UPI_HANDLES)}"


def build_mobile(rng: random.Random) -> str:
    return rng.choice("6789") + _digits(rng, 9)


def build_non_mobile(rng: random.Random) -> str:
    return rng.choice("012345") + _digits(rng, 9)


def build_malformed_pan(rng: random.Random) -> str:
    # Four leading letters: one short of a PAN, so it must not match.
    return _letters(rng, 4) + _digits(rng, 4) + _letters(rng, 1)


def build_high_entropy(rng: random.Random) -> str:
    # Alternating letter/digit: can never contain five consecutive letters, so
    # it cannot be a PAN, IFSC, or GSTIN fragment.
    token = []
    for index in range(13):
        pool = string.ascii_uppercase if index % 2 == 0 else string.digits
        token.append(rng.choice(pool))
    return "".join(token)


# --------------------------------------------------------------------------
# Corpus assembly
# --------------------------------------------------------------------------


def _compose(parts: list) -> tuple[str, list[dict]]:
    """Concatenate literal strings and ``(value, kind)`` idents, labelling spans."""
    text = ""
    labels: list[dict] = []
    for part in parts:
        if isinstance(part, tuple):
            value, kind = part
            start = len(text)
            text += value
            labels.append(
                {"start": start, "end": len(text), "kind": kind, "text": value}
            )
        else:
            text += part
    return text, labels


def build_records(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    records: list[dict] = []

    def add(record_id: str, language: str, parts: list, negative: bool = False) -> None:
        text, labels = _compose(parts)
        records.append(
            {
                "id": record_id,
                "language": language,
                "text": text,
                "labels": labels,
                "negative": negative,
            }
        )

    # --- English positives -------------------------------------------------
    add("en-aadhaar", "en", ["My Aadhaar number is ", (build_aadhaar(rng), KIND_AADHAAR), " for the application."])
    add("en-aadhaar-spaced", "en", ["Aadhaar ", (build_aadhaar(rng), KIND_AADHAAR), " was linked to the account."])
    add("en-pan", "en", ["The PAN ", (build_pan(rng), KIND_PAN), " is required for KYC."])
    add("en-gstin", "en", ["GSTIN ", (build_gstin(rng), KIND_GSTIN), " is printed on the tax invoice."])
    add("en-ifsc", "en", ["Transfer the amount to IFSC ", (build_ifsc(rng), KIND_IFSC), " at the branch."])
    add("en-upi", "en", ["Pay the application fee to ", (build_upi(rng), KIND_UPI), " before the deadline."])
    add("en-mobile-prefixed", "en", ["Call ", ("+91 " + build_mobile(rng), KIND_MOBILE), " for the helpline."])
    add("en-mobile-bare", "en", ["Send an SMS to ", (build_mobile(rng), KIND_MOBILE), " to check the status."])

    # --- Hinglish (Roman-script Hindi) positives ---------------------------
    add("hi-Latn-aadhaar", "hi-Latn", ["Mera Aadhaar ", (build_aadhaar(rng), KIND_AADHAAR), " hai, isko update karo."])
    add("hi-Latn-pan", "hi-Latn", ["PAN card ", (build_pan(rng), KIND_PAN), " ka number form me daal do."])
    add("hi-Latn-gstin", "hi-Latn", ["Dukaandaar ka GSTIN ", (build_gstin(rng), KIND_GSTIN), " verify karo."])
    add("hi-Latn-ifsc", "hi-Latn", ["IFSC ", (build_ifsc(rng), KIND_IFSC), " se paisa transfer hoga."])
    add("hi-Latn-upi", "hi-Latn", ["Paisa ", (build_upi(rng), KIND_UPI), " par bhej do."])
    add("hi-Latn-mobile", "hi-Latn", ["Apna mobile ", (build_mobile(rng), KIND_MOBILE), " confirm karo."])

    # --- Devanagari positives ---------------------------------------------
    add("hi-Deva-aadhaar", "hi-Deva", ["\u0906\u0927\u093e\u0930 \u0938\u0902\u0916\u094d\u092f\u093e ", (_to_devanagari(build_aadhaar(rng)), KIND_AADHAAR), " \u0926\u0930\u094d\u091c \u0939\u0948\u0964"])
    add("hi-Deva-mobile", "hi-Deva", ["\u092e\u094b\u092c\u093e\u0907\u0932 ", (_to_devanagari(build_mobile(rng)), KIND_MOBILE), " \u092a\u0930 \u0938\u0902\u092a\u0930\u094d\u0915 \u0915\u0930\u0947\u0902\u0964"])
    add("hi-Deva-ref-5", "hi-Deva", ["\u0938\u0902\u0926\u0930\u094d\u092d \u0915\u094d\u0930\u092e\u093e\u0902\u0915 ", (_to_devanagari(_digits(rng, 5)), KIND_DEVANAGARI_DIGITS), " \u0909\u092a\u0932\u092c\u094d\u0927 \u0939\u0948\u0964"])
    add("hi-Deva-ref-6", "hi-Deva", ["\u092a\u093f\u0928 \u0915\u094b\u0921 ", (_to_devanagari(_digits(rng, 6)), KIND_DEVANAGARI_DIGITS), " \u0926\u0930\u094d\u091c \u0939\u0948\u0964"])
    add("hi-Deva-ref-7", "hi-Deva", ["\u0916\u093e\u0924\u093e \u0915\u094d\u0930\u092e\u093e\u0902\u0915 ", (_to_devanagari(_digits(rng, 7)), KIND_DEVANAGARI_DIGITS), " \u0938\u0915\u094d\u0930\u093f\u092f \u0939\u0948\u0964"])

    # --- Multi-identifier positives ---------------------------------------
    add("en-aadhaar-mobile", "en", ["Aadhaar ", (build_aadhaar(rng), KIND_AADHAAR), " is linked to mobile ", (build_mobile(rng), KIND_MOBILE), "."])
    add("en-gstin-pan", "en", ["GSTIN ", (build_gstin(rng), KIND_GSTIN), " references PAN ", (build_pan(rng), KIND_PAN), "."])
    add("hi-Latn-upi-mobile", "hi-Latn", ["UPI ", (build_upi(rng), KIND_UPI), " ya phone ", (build_mobile(rng), KIND_MOBILE), " use karo."])

    # --- Negatives (no labels; must not match) ----------------------------
    add("neg-aadhaar-verhoeff", "en", [f"The number {build_aadhaar_near_miss(rng)} looks like Aadhaar but the checksum fails."], negative=True)
    add("neg-pan-malformed", "en", [f"Reference {build_malformed_pan(rng)} is not a valid PAN."], negative=True)
    add("neg-non-mobile-zero", "en", [f"Account {build_non_mobile(rng)} is a ledger number, not a phone."], negative=True)
    add("neg-non-mobile-five", "hi-Latn", [f"Code {build_non_mobile(rng)} mobile number nahi hai."], negative=True)
    add("neg-high-entropy", "en", [f"Session token {build_high_entropy(rng)} was generated."], negative=True)
    add("neg-aadhaar-in-run", "en", [f"9{build_aadhaar(rng)}9 is part of a longer identifier run."], negative=True)
    add("neg-eleven-digit", "en", [f"Reference {_digits(rng, 11)} is an eleven-digit code."], negative=True)
    add("neg-email", "en", ["Write to field.ops@example.com for support."], negative=True)

    return records


def _labelled_counts(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for label in record["labels"]:
            counts[label["kind"]] = counts.get(label["kind"], 0) + 1
    return dict(sorted(counts.items()))


def build_corpus(seed: int = SEED) -> tuple[dict, list[dict]]:
    records = build_records(seed)
    labels = sum(len(record["labels"]) for record in records)
    negatives = sum(1 for record in records if record["negative"])
    header = {
        "type": "header",
        "seed": seed,
        "generator": GENERATOR,
        "synthetic": True,
        "statement": (
            "Entirely synthetic corpus generated from a seeded RNG; no real "
            "person's identifier is included."
        ),
        "records": len(records),
        "labelled_spans": labels,
        "negative_records": negatives,
        "counts": _labelled_counts(records),
    }
    return header, records


def write_corpus(header: dict, records: list[dict], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    lines += [
        json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records
    ]
    # Write LF explicitly so the fixture is byte-identical on every platform,
    # independent of core.autocrlf; the CI job diffs a fresh generation against
    # the committed bytes.
    output.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    header, records = build_corpus(args.seed)
    count = write_corpus(header, records, args.output)
    print(
        f"Wrote {count} synthetic record(s) "
        f"({header['labelled_spans']} labelled span(s), "
        f"{header['negative_records']} negative record(s)) to "
        f"{args.output.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
