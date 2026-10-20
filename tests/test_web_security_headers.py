"""Guard the web tier's response-header policy (security finding F1).

``web/next.config.ts`` is the only place the browser-facing security headers are
declared, and a deleted line there fails silently: pages keep rendering, so
nothing in the product notices that clickjacking, MIME-sniffing and referrer
protections have quietly gone away. These are the source-level guards.

What a Python test can and cannot prove, stated plainly:

* it **can** prove the policy is still exactly the reviewed directive set, that
  the unsupported/aspirational headers have not crept in, that the header set is
  wired to every route shape rather than only dynamic ones, and that the
  ``connect-src 'self'`` precondition (no browser code reaches a third-party
  origin) still holds;
* it **cannot** prove a browser accepts the policy. That is
  ``web/e2e/csp.mjs``, which drives a real Next production build and asserts
  zero ``securitypolicyviolation`` events on /, /evidence and /coverage plus a
  working stream, feedback POST, fonts and styles. Test
  ``test_browser_probe_covers_every_required_surface`` keeps that execution
  proof from being deleted or weakened to nothing.

The policy deliberately ships **without** a nonce or ``'strict-dynamic'``: that
variant forces every rendered route to be dynamic, which would break the
prerendered /evidence page. It also omits HSTS (already served by the host and
extended only by the domain owner), COEP, CORP, Trusted-Types and
``X-XSS-Protection``. Those omissions are asserted, not merely intended.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
NEXT_CONFIG = WEB / "next.config.ts"
CSP_PROBE = WEB / "e2e" / "csp.mjs"

# The reviewed policy (t_0bbdef85 policy #32, section 1.2). Literal on purpose:
# widening or narrowing it must be a deliberate edit to this table.
EXPECTED_CSP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("default-src", ("'self'",)),
    # Next's App Router ships the RSC flight payload as an inline script; a bare
    # 'self' blanks every page. Keeping this assertion makes the accompanying
    # claim in next.config.ts ("script-src does not mitigate XSS here") true.
    ("script-src", ("'self'", "'unsafe-inline'")),
    ("style-src", ("'self'", "'unsafe-inline'")),
    ("img-src", ("'self'", "data:")),
    ("font-src", ("'self'", "data:")),
    ("connect-src", ("'self'",)),
    ("frame-ancestors", ("'none'",)),
    ("base-uri", ("'self'",)),
    ("form-action", ("'self'",)),
    ("object-src", ("'none'",)),
    ("upgrade-insecure-requests", ()),
)

EXPECTED_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Rejected on purpose (policy #32 section 1.3). Each would either break a
# subresource, be ignored by browsers, or belong to the domain owner.
REJECTED_HEADERS = (
    "Cross-Origin-Embedder-Policy",
    "Cross-Origin-Resource-Policy",
    "X-XSS-Protection",
    "Strict-Transport-Security",
    "Report-To",
    "Expect-CT",
)

_HEADER_PAIR_RE = re.compile(
    r'\{\s*key:\s*"(?P<key>[^"]+)",\s*value:\s*(?P<value>"[^"]*"|CONTENT_SECURITY_POLICY)\s*,?\s*\}'
)


def _config_text() -> str:
    return NEXT_CONFIG.read_text(encoding="utf-8")


def _csp_literals(text: str) -> list[str]:
    """Return the string literals of the CONTENT_SECURITY_POLICY array, in order."""
    start = text.index("const CONTENT_SECURITY_POLICY = [")
    end = text.index("].join(", start)
    block = text[start:end]
    literals: list[str] = []
    for line in block.splitlines()[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        match = re.match(r'"([^"]*)"\s*,?\s*$', stripped)
        if match:
            literals.append(match.group(1))
    return literals


def _csp_pairs() -> list[tuple[str, tuple[str, ...]]]:
    pairs: list[tuple[str, tuple[str, ...]]] = []
    for entry in _csp_literals(_config_text()):
        directive, *sources = entry.split()
        pairs.append((directive, tuple(sources)))
    return pairs


def _header_map() -> dict[str, str]:
    """Read the SECURITY_HEADERS table from the config source.

    Values may be a quoted literal or the CONTENT_SECURITY_POLICY constant; the
    latter is substituted with the joined policy so the map is comparable.
    """
    text = _config_text()
    start = text.index("const SECURITY_HEADERS = [")
    end = text.index("];", start)
    block = text[start:end]
    headers: dict[str, str] = {}
    for match in _HEADER_PAIR_RE.finditer(block):
        key = match.group("key")
        raw_value = match.group("value").strip()
        if raw_value == "CONTENT_SECURITY_POLICY":
            headers[key] = "; ".join(_csp_literals(text))
        else:
            literal = re.fullmatch(r'"([^"]*)"', raw_value)
            if literal is None:
                pytest.fail(f"unexpected value for {key} in next.config.ts: {raw_value}")
            headers[key] = literal.group(1)
    return headers


def _source_files() -> list[Path]:
    return [
        path
        for path in (WEB / "app").rglob("*")
        if path.suffix in {".ts", ".tsx"}
    ] + [
        path
        for path in (WEB / "components").rglob("*")
        if path.suffix in {".ts", ".tsx"}
    ] + [
        path
        for path in (WEB / "lib").rglob("*")
        if path.suffix in {".ts", ".tsx"}
    ]


def test_csp_is_exactly_the_reviewed_directive_set() -> None:
    """The policy may not widen or narrow without editing this table."""
    assert _csp_pairs() == list(EXPECTED_CSP)


def test_csp_rejects_nonce_strict_dynamic_and_wildcard_sources() -> None:
    """Nonce/strict-dynamic is a deferred decision, not an accident of editing.

    It would force every rendered route to be dynamic and blank the prerendered
    /evidence page; wildcards and plain-http sources would undo the policy's
    whole point. ``'unsafe-eval'`` is never needed by a production build.
    """
    policy = "; ".join(_csp_literals(_config_text()))
    for forbidden in ("nonce-", "strict-dynamic", "unsafe-eval", "http:", "*", "wasm-unsafe-eval"):
        assert forbidden not in policy, f"{forbidden!r} must not appear in the CSP: {policy}"


def test_required_response_headers_are_configured() -> None:
    headers = _header_map()
    for key, value in EXPECTED_HEADERS.items():
        assert headers.get(key) == value, f"{key} is {headers.get(key)!r}, expected {value!r}"


def test_clickjacking_is_covered_by_both_controls() -> None:
    """frame-ancestors is the modern control; X-Frame-Options covers legacy engines."""
    headers = _header_map()
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"


def test_mime_and_referrer_protections_are_present() -> None:
    headers = _header_map()
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_aspirational_or_out_of_scope_headers_are_not_configured() -> None:
    """Do not add headers this app cannot honour or does not own.

    COEP/CORP would break cross-origin subresources and buy nothing here;
    Trusted-Types has no sink and thin support; X-XSS-Protection is deprecated
    and harmful in some engines; HSTS is already served by the host and
    extending it is the domain owner's decision.
    """
    text = _config_text()
    headers = _header_map()
    for rejected in REJECTED_HEADERS:
        assert rejected not in headers, f"{rejected} must not be set from this config"
        assert f'key: "{rejected}"' not in text


def test_policy_applies_to_every_route_shape_and_is_config_level() -> None:
    """A config-level catch-all, not middleware: static routes must be covered.

    Middleware would leave the prerendered /evidence page to whatever headers
    its static handler emits, and would drag in per-request cost and nonce
    plumbing this slice deliberately avoids.
    """
    text = _config_text()
    assert "async headers()" in text
    assert 'source: "/(.*)"' in text
    assert not (WEB / "middleware.ts").exists()
    assert not (WEB / "proxy.ts").exists()


def test_powered_by_header_is_disabled() -> None:
    assert re.search(r"poweredByHeader:\s*false", _config_text()), (
        "poweredByHeader must stay false so responses stop advertising the framework"
    )


def test_connect_src_self_precondition_still_holds() -> None:
    """``connect-src 'self'`` is only safe while no browser code talks off-origin.

    The API URL is read server-side from ``process.env.API_URL``. If a client
    component ever fetches the Render origin directly, every such request would
    be blocked and the policy would be wrong, so fail here with an explanation
    instead of silently weakening the policy.
    """
    offenders: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        if '"use client"' not in text:
            continue
        if "NEXT_PUBLIC_" in text:
            offenders.append(f"{path.relative_to(ROOT)} exposes a public env var")
        for match in re.finditer(r"fetch\(\s*[`'\"]([^`'\"]+)", text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "//")):
                offenders.append(f"{path.relative_to(ROOT)} fetches {target}")
    assert not offenders, (
        "a client component reaches an off-origin URL, so connect-src 'self' "
        "would block it: " + "; ".join(offenders)
    )


def test_browser_probe_covers_every_required_surface() -> None:
    """The executable proof must keep covering what the card requires.

    ``web/e2e/csp.mjs`` is where 'the browser accepts this policy' is actually
    established: prerendered /evidence, dynamic pages, both API route handlers,
    resource loads, the clickjacking control and the permissions policy. This
    guard fails if that coverage is deleted, so a green source-level suite can
    never stand in for a probe that no longer exists.
    """
    assert CSP_PROBE.exists(), "web/e2e/csp.mjs (the production-build header probe) is missing"
    probe = CSP_PROBE.read_text(encoding="utf-8")
    for required in (
        "/evidence",
        "/coverage",
        "/api/chat/stream",
        "/api/chat/feedback",
        "securitypolicyviolation",
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
        "frame-ancestors",
        "text/event-stream",
    ):
        assert required in probe, f"csp.mjs no longer asserts {required!r}"


def test_probe_policy_matches_the_configured_policy() -> None:
    """The probe's independent copy of the policy must not drift from the config.

    csp.mjs intentionally asserts a literal expected value instead of importing
    the config; that only has value if the two literals agree.
    """
    probe = CSP_PROBE.read_text(encoding="utf-8")
    block = probe[probe.index("const EXPECTED_CSP = ["): probe.index("].join(\"; \"", 0)]
    literals = [m.group(1) for m in re.finditer(r'^\s*"([^"]*)",?\s*$', block, re.MULTILINE)]
    assert literals, "could not read EXPECTED_CSP from csp.mjs"
    configured = [entry for entry in _csp_literals(_config_text())]
    assert literals == configured, (
        "csp.mjs EXPECTED_CSP has drifted from web/next.config.ts: "
        f"probe={literals} config={configured}"
    )
