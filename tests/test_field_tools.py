"""Tests for the field tooling: preflight classification + report contract.

These tests exercise the *decision* logic of the preflight doctor (which is
where the judgement lives) with injected probes, so they need no Docker, no
network, and no customer environment. The end-to-end preflight run against a
real host is part of the field evidence, not of CI.
"""

import json
import socket
from pathlib import Path

import pytest

from deploy.field import preflight as pf


# --- severity classification -------------------------------------------------


def test_disk_severity_bands():
    assert pf.disk_severity(100.0) == pf.OK
    assert pf.disk_severity(pf.DISK_WARN_GB - 1) == pf.WARN
    assert pf.disk_severity(pf.DISK_MIN_GB - 1) == pf.BLOCKER


def test_memory_severity_bands():
    assert pf.memory_severity(16.0) == pf.OK
    assert pf.memory_severity(pf.MEM_WARN_GB - 1) == pf.WARN
    assert pf.memory_severity(pf.MEM_MIN_GB - 1) == pf.BLOCKER


def test_clock_skew_severity_is_symmetric():
    assert pf.clock_skew_severity(5) == pf.OK
    assert pf.clock_skew_severity(-5) == pf.OK
    assert pf.clock_skew_severity(pf.CLOCK_SKEW_WARN_S + 1) == pf.WARN
    assert pf.clock_skew_severity(-(pf.CLOCK_SKEW_BLOCKER_S + 1)) == pf.BLOCKER


def test_egress_failure_is_expected_in_airgap_only():
    assert pf.egress_severity(airgap=True) == pf.INFO
    assert pf.egress_severity(airgap=False) == pf.BLOCKER


def test_tls_interception_is_a_blocker_with_ca_advice():
    severity, remediation = pf.tls_error_classification(
        "SSLCertVerificationError: certificate verify failed: self-signed certificate"
    )
    assert severity == pf.BLOCKER
    assert "root CA" in remediation
    assert "Do not disable verification" in remediation


def test_unclassified_tls_error_is_a_warning():
    severity, _remediation = pf.tls_error_classification("ConnectionResetError: reset")
    assert severity == pf.WARN


# --- env parsing -------------------------------------------------------------


def test_missing_env_keys_flags_presence_only():
    issues = pf.missing_env_keys({"DATABASE_URL": "postgresql://x"})
    joined = " ".join(issues)
    assert "GROQ_API_KEY" in joined and "demo mode" in joined
    assert "ADMIN_TOKEN" in joined
    assert "postgresql://x" not in joined  # values never echoed


def test_missing_env_keys_clean_when_complete():
    assert (
        pf.missing_env_keys(
            {
                "DATABASE_URL": "postgresql://x",
                "GROQ_API_KEY": "k",
                "ADMIN_TOKEN": "t",
            }
        )
        == []
    )


def test_proxy_env_lists_names_not_values():
    names = pf.proxy_env({"HTTPS_PROXY": "http://user:pass@proxy:8080", "PATH": "/usr/bin"})
    assert names == ["HTTPS_PROXY"]
    assert "user:pass" not in " ".join(names)


def test_mask_url_strips_credentials():
    assert (
        pf.mask_url("https://user:secret@gw.internal/v1?token=abc")
        == "https://gw.internal/v1"
    )


# --- probes + verdict --------------------------------------------------------


class FakeProbe(pf.Probe):
    """A Probe whose external effects are scripted by the test."""

    def __init__(self, repo_root: Path, **kwargs):
        super().__init__(repo_root=repo_root)
        self.airgap = kwargs.pop("airgap", False)
        self.resolve = kwargs.pop("resolve", lambda host, port: [(2, 1, 6, "", ("10.0.0.1", port))])
        self.tcp_connect = kwargs.pop("tcp_connect", lambda host, port: (True, "connected"))
        self.https_head = kwargs.pop(
            "https_head",
            lambda url: {"status": 200, "issuer": "R3", "server_date": None, "error": ""},
        )
        self.which = kwargs.pop("which", lambda name: f"/usr/bin/{name}")
        self.run = kwargs.pop("run", lambda argv: (0, "ok", ""))
        self.env = kwargs.pop("env", {})


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "data" / "schemes").mkdir(parents=True)
    (tmp_path / "data" / "schemes" / "pm-kisan.md").write_text("# PM-KISAN\n", encoding="utf-8")
    return tmp_path


def test_verdict_is_blocker_driven():
    findings = [
        pf.Finding("A", "a", pf.OK, "x"),
        pf.Finding("B", "b", pf.WARN, "x"),
    ]
    assert pf.verdict(findings) == (2, "GO (with warnings)")
    findings.append(pf.Finding("C", "c", pf.BLOCKER, "x"))
    assert pf.verdict(findings) == (1, "NO-GO")
    assert pf.verdict([pf.Finding("A", "a", pf.OK, "x")]) == (0, "GO")


def test_network_checks_degrade_in_airgap(repo):
    def exploding_resolve(host, port):
        raise socket.gaierror("Name or service not known")

    connected = pf.check_network(FakeProbe(repo, resolve=exploding_resolve))
    assert any(f.severity == pf.BLOCKER and f.code == "PF-040" for f in connected)

    offline = pf.check_network(FakeProbe(repo, airgap=True, resolve=exploding_resolve))
    assert all(f.severity != pf.BLOCKER for f in offline)


def test_network_checks_report_tls_interception(repo):
    probe = FakeProbe(
        repo,
        https_head=lambda url: {
            "status": None,
            "issuer": "",
            "server_date": None,
            "error": "SSLCertVerificationError: certificate verify failed: self-signed",
        },
    )
    findings = pf.check_network(probe)
    tls = [f for f in findings if f.code == "PF-045"][0]
    assert tls.severity == pf.BLOCKER


def test_network_checks_detect_clock_skew(repo):
    import time as _time

    skewed = FakeProbe(
        repo,
        https_head=lambda url: {
            "status": 200,
            "issuer": "R3",
            "server_date": _time.time() + pf.CLOCK_SKEW_BLOCKER_S + 60,
            "error": "",
        },
    )
    finding = [f for f in pf.check_network(skewed) if f.code == "PF-046"][0]
    assert finding.severity == pf.BLOCKER
    assert "NTP" in finding.remediation

    aligned = FakeProbe(
        repo,
        https_head=lambda url: {
            "status": 200,
            "issuer": "R3",
            "server_date": _time.time(),
            "error": "",
        },
    )
    finding = [f for f in pf.check_network(aligned) if f.code == "PF-046"][0]
    assert finding.severity == pf.OK


def test_network_checks_note_missing_reference_clock(repo):
    finding = [f for f in pf.check_network(FakeProbe(repo)) if f.code == "PF-046"][0]
    assert finding.severity == pf.INFO


def test_env_file_checks(repo):
    missing = pf.check_env_file(FakeProbe(repo))
    assert any(f.code == "PF-050" and f.severity == pf.BLOCKER for f in missing)

    (repo / ".env").write_text(
        "GROQ_API_KEY=secret-value-should-never-print\n"
        "DATABASE_URL=postgresql+psycopg://scheme:scheme@db:5432/schemegpt\n"
        "ADMIN_TOKEN=another-secret\n",
        encoding="utf-8",
    )
    findings = pf.check_env_file(FakeProbe(repo))
    blob = json.dumps([f.__dict__ for f in findings])
    assert "secret-value-should-never-print" not in blob
    assert any(f.code == "PF-051" and f.severity == pf.OK for f in findings)
    assert any(f.code == "PF-052" and f.severity == pf.OK for f in findings)


def test_artifacts_check_warns_when_nothing_is_loaded(repo):
    probe = FakeProbe(repo, run=lambda argv: (0, "", ""))
    findings = pf.check_artifacts(probe)
    image = [f for f in findings if f.code == "PF-060"][0]
    assert image.severity == pf.WARN
    corpus = [f for f in findings if f.code == "PF-061"][0]
    assert corpus.severity == pf.OK and "1 markdown" in corpus.detail

    airgap_probe = FakeProbe(repo, airgap=True, run=lambda argv: (0, "", ""))
    airgap_image = [f for f in pf.check_artifacts(airgap_probe) if f.code == "PF-060"][0]
    assert airgap_image.severity == pf.INFO


def test_main_writes_json_report_and_exit_code(repo, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pf, "build_probe", lambda root, airgap: FakeProbe(root, airgap=airgap))
    report_path = tmp_path / "reports" / "preflight.json"
    code = pf.main(
        ["--repo-root", str(repo), "--json", str(report_path), "--label", "state-gov"]
    )
    captured = capsys.readouterr().out
    assert "SchemeGPT field preflight" in captured
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["label"] == "state-gov"
    assert payload["schema"] == 1
    assert payload["exit_code"] == code
    assert set(payload["counts"]) == {pf.OK, pf.INFO, pf.WARN, pf.BLOCKER}
    assert payload["verdict"] in ("GO", "GO (with warnings)", "NO-GO")


def test_a_broken_check_does_not_hide_the_others(repo, monkeypatch, tmp_path):
    def exploding_check(probe):
        raise RuntimeError("boom")

    monkeypatch.setattr(pf, "CHECKS", (exploding_check, pf.check_platform))
    monkeypatch.setattr(pf, "build_probe", lambda root, airgap: FakeProbe(root))
    report_path = tmp_path / "preflight.json"
    pf.main(["--repo-root", str(repo), "--json", str(report_path)])
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    codes = {finding["code"] for finding in payload["findings"]}
    assert "PF-999" in codes  # the broken check is reported
    assert "PF-001" in codes  # and the healthy checks still ran
