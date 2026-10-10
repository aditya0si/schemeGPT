#!/usr/bin/env python3
"""SchemeGPT field preflight: prove the target environment can run this stack.

Run this *before* an install, on the machine (or the network segment) that will
host the deployment. It exists because the things that kill a pilot are almost
never the application:

* an egress policy that blocks the registry or the model provider,
* a corporate TLS-inspection proxy whose root CA is not in the trust store,
* a clock that is minutes off (TLS and JWT both fail mysteriously),
* ports already bound by something else,
* a disk that cannot hold the images plus the database,
* no key / no vector store / no admin token,
* a Docker that is installed but whose daemon is not running.

Every check prints a stable code (``PF-040``), a severity, what was observed,
and what to do about it. The JSON report (``--json``) is a record you can hand
to the customer and attach to the engagement: it names the host, the versions,
and the blockers at a point in time.

Severities
    OK       - checked, healthy
    INFO     - observation worth recording (includes intentional air-gap)
    WARN     - go, but this will bite later
    BLOCKER  - do not proceed until resolved

Exit codes: 0 = go, 1 = blockers found, 2 = warnings only.

Stdlib only, by design: this must run on a bare customer box with no venv, no
pip, and possibly no internet. It never writes to the deployment, never needs
credentials, and never prints secret values (key *presence* only).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

OK = "OK"
INFO = "INFO"
WARN = "WARN"
BLOCKER = "BLOCKER"

SEVERITY_ORDER = {OK: 0, INFO: 1, WARN: 2, BLOCKER: 3}

# Thresholds (documented so the numbers in the report are not a mystery).
DISK_MIN_GB = 12.0      # images (~2.5 GB) + Postgres growth + model cache
DISK_WARN_GB = 25.0
MEM_MIN_GB = 3.5        # API with the baked embedding model under load
MEM_WARN_GB = 7.0
CPU_MIN = 2
CLOCK_SKEW_WARN_S = 120
CLOCK_SKEW_BLOCKER_S = 900
REQUIRED_PORTS = (8000, 8501, 3000)

DEFAULT_PROVIDER_HOST = "api.groq.com"
DEFAULT_REGISTRY_HOST = "registry-1.docker.io"


@dataclass
class Finding:
    code: str
    title: str
    severity: str
    detail: str
    remediation: str = ""

    @property
    def ok(self) -> bool:
        return self.severity in (OK, INFO)


@dataclass
class Probe:
    """Everything the checks are allowed to touch, injectable for tests."""

    repo_root: Path
    airgap: bool = False
    resolve: object = socket.getaddrinfo
    tcp_connect: object = None  # (host, port, timeout) -> (bool, str)
    https_head: object = None   # (url, timeout) -> (status, issuer, error)
    which: object = shutil.which
    run: object = None          # (argv, timeout) -> (rc, stdout, stderr)
    env: dict = field(default_factory=dict)


# --- pure helpers (unit-tested) ----------------------------------------------


def disk_severity(free_gb: float) -> str:
    if free_gb < DISK_MIN_GB:
        return BLOCKER
    if free_gb < DISK_WARN_GB:
        return WARN
    return OK


def memory_severity(total_gb: float) -> str:
    if total_gb < MEM_MIN_GB:
        return BLOCKER
    if total_gb < MEM_WARN_GB:
        return WARN
    return OK


def clock_skew_severity(skew_seconds: float) -> str:
    magnitude = abs(skew_seconds)
    if magnitude >= CLOCK_SKEW_BLOCKER_S:
        return BLOCKER
    if magnitude >= CLOCK_SKEW_WARN_S:
        return WARN
    return OK


def egress_severity(airgap: bool) -> str:
    """An unreachable registry/provider is fatal on a connected box, expected
    on an air-gapped one (where images arrive as a bundle)."""
    return INFO if airgap else BLOCKER


def mask_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[-1]
    return f"{parts.scheme}://{host}{parts.path.rstrip('/')}"


def proxy_env(env: dict) -> list[str]:
    """Names of proxy variables that are set (values are never printed)."""
    keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    )
    return [key for key in keys if str(env.get(key, "")).strip()]


def tls_error_classification(error: str) -> tuple[str, str]:
    """Map an HTTPS failure to (severity, remediation)."""
    text = (error or "").lower()
    if "certificate verify failed" in text or "self-signed" in text or "self signed" in text:
        return (
            BLOCKER,
            "TLS interception or a private CA: install the organisation's root "
            "CA into the trust store and set SSL_CERT_FILE / REQUESTS_CA_BUNDLE, "
            "or pin the provider's CA. Do not disable verification.",
        )
    if "timed out" in text or "timeout" in text:
        return (WARN, "TLS handshake timed out: suspect an egress filter.")
    return (WARN, "HTTPS probe failed for an unclassified reason; see detail.")


def missing_env_keys(env: dict) -> list[str]:
    """Keys the deployment needs before go-live (presence only, never values)."""
    missing = []
    if not str(env.get("GROQ_API_KEY", "")).strip():
        missing.append("GROQ_API_KEY (absent: instance runs in labelled demo mode)")
    for key in ("DATABASE_URL",):
        if not str(env.get(key, "")).strip():
            missing.append(f"{key} (required)")
    if not str(env.get("ADMIN_TOKEN", "")).strip():
        missing.append("ADMIN_TOKEN (absent: operator endpoints return 503)")
    return missing


def verdict(findings: Iterable[Finding]) -> tuple[int, str]:
    severities = [f.severity for f in findings]
    if BLOCKER in severities:
        return 1, "NO-GO"
    if WARN in severities:
        return 2, "GO (with warnings)"
    return 0, "GO"


# --- real probes -------------------------------------------------------------


def _run(argv: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{argv[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"


def _tcp_connect(host: str, port: int, timeout: float = 6.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "connected"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _https_probe(url: str, timeout: float = 8.0) -> dict:
    """HEAD request returning status, leaf issuer, server date and any error.

    The server's ``Date`` header is the cheapest trustworthy reference clock
    available without extra dependencies: comparing it to the local clock
    catches the clock skew that makes TLS and JWT fail for no visible reason.
    """
    import http.client

    result = {"status": None, "issuer": "", "server_date": None, "error": ""}
    parts = urlsplit(url)
    context = ssl.create_default_context()
    try:
        conn = http.client.HTTPSConnection(parts.netloc, timeout=timeout, context=context)
        conn.request("HEAD", parts.path or "/")
        response = conn.getresponse()
        result["status"] = response.status
        date_header = response.getheader("Date")
        if date_header:
            from email.utils import parsedate_to_datetime

            try:
                result["server_date"] = parsedate_to_datetime(date_header).timestamp()
            except Exception:
                result["server_date"] = None
        cert = conn.sock.getpeercert() if conn.sock else {}
        for rdn in (cert or {}).get("issuer", ()):
            for key, value in rdn:
                if key == "commonName":
                    result["issuer"] = value
        conn.close()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


# --- checks ------------------------------------------------------------------


def check_platform(probe: Probe) -> list[Finding]:
    findings: list[Finding] = []
    py = sys.version_info
    findings.append(
        Finding(
            "PF-001",
            "Python runtime",
            OK if py >= (3, 9) else BLOCKER,
            f"{platform.python_version()} on {platform.system()} {platform.release()}",
            "" if py >= (3, 9) else "Install Python 3.9+ (3.12 matches CI).",
        )
    )
    findings.append(
        Finding(
            "PF-002",
            "Host identity",
            INFO,
            f"hostname={socket.gethostname()} arch={platform.machine()}",
        )
    )
    try:
        tempfile.NamedTemporaryFile(dir=probe.repo_root, delete=True)
        write_ok, write_detail = True, str(probe.repo_root)
    except Exception as exc:
        write_ok, write_detail = False, f"{type(exc).__name__}"
    findings.append(
        Finding(
            "PF-003",
            "Working directory writable",
            OK if write_ok else BLOCKER,
            write_detail,
            "" if write_ok else "Run from a directory the service account owns.",
        )
    )
    return findings


def check_docker(probe: Probe) -> list[Finding]:
    findings: list[Finding] = []
    docker_path = probe.which("docker")
    if not docker_path:
        return [
            Finding(
                "PF-010",
                "Docker CLI",
                BLOCKER,
                "docker not found on PATH",
                "Install Docker Engine/Desktop (the stack ships as compose).",
            )
        ]
    findings.append(Finding("PF-010", "Docker CLI", OK, docker_path))

    rc, out, err = probe.run(["docker", "version", "--format", "{{.Server.Version}}"])
    findings.append(
        Finding(
            "PF-011",
            "Docker daemon",
            OK if rc == 0 else BLOCKER,
            out if rc == 0 else (err or "daemon unreachable"),
            "" if rc == 0 else "Start the daemon (`sudo systemctl start docker`).",
        )
    )
    rc, out, err = probe.run(["docker", "compose", "version"])
    findings.append(
        Finding(
            "PF-012",
            "Docker Compose",
            OK if rc == 0 else BLOCKER,
            out or err,
            "" if rc == 0 else "Install the compose v2 plugin.",
        )
    )
    return findings


def check_resources(probe: Probe) -> list[Finding]:
    findings: list[Finding] = []
    # Disk
    try:
        usage = shutil.disk_usage(str(probe.repo_root))
        free_gb = usage.free / (1024 ** 3)
        findings.append(
            Finding(
                "PF-020",
                "Free disk space",
                disk_severity(free_gb),
                f"{free_gb:.1f} GB free (min {DISK_MIN_GB} GB, warn under "
                f"{DISK_WARN_GB} GB)",
                "" if free_gb >= DISK_MIN_GB else "Free space or relocate the data volume.",
            )
        )
    except Exception as exc:
        findings.append(
            Finding("PF-020", "Free disk space", WARN, f"unavailable: {type(exc).__name__}")
        )
    # Memory
    total_gb = None
    try:
        if platform.system() == "Linux":
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
            match = re.search(r"MemTotal:\s+(\d+) kB", meminfo)
            if match:
                total_gb = int(match.group(1)) / (1024 ** 2)
        elif platform.system() == "Windows":
            # wmic is gone on recent Windows builds; fall back to CIM via
            # PowerShell, which is present everywhere this runs in practice.
            for argv in (
                ["wmic", "computersystem", "get", "TotalPhysicalMemory"],
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                ],
            ):
                rc, out, _err = probe.run(argv, timeout=15)
                if rc != 0:
                    continue
                digits = re.findall(r"(\d{6,})", out or "")
                if digits:
                    total_gb = int(digits[0]) / (1024 ** 3)
                    break
    except Exception:
        total_gb = None
    if total_gb is None:
        findings.append(
            Finding(
                "PF-021",
                "Memory",
                INFO,
                "could not be determined on this platform (check the host spec manually)",
            )
        )
    else:
        findings.append(
            Finding(
                "PF-021",
                "Memory",
                memory_severity(total_gb),
                f"{total_gb:.1f} GB total (min {MEM_MIN_GB} GB, warn under {MEM_WARN_GB} GB)",
                "" if total_gb >= MEM_MIN_GB else "Add memory; the API holds a 470 MB model.",
            )
        )
    # CPU
    cpu_count = os.cpu_count() or 0
    findings.append(
        Finding(
            "PF-022",
            "CPU count",
            OK if cpu_count >= CPU_MIN else WARN,
            f"{cpu_count} logical cores",
            "" if cpu_count >= CPU_MIN else "Embedding/retrieval latency will suffer.",
        )
    )
    return findings


def check_ports(probe: Probe, ports: Iterable[int] = REQUIRED_PORTS) -> list[Finding]:
    findings: list[Finding] = []
    for index, port in enumerate(ports):
        free = True
        detail = "free"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError as exc:
                    free = False
                    detail = f"already bound ({type(exc).__name__})"
        except Exception as exc:
            detail = f"could not test ({type(exc).__name__})"
            free = False
        findings.append(
            Finding(
                f"PF-03{index}",
                f"Port {port}",
                OK if free else WARN,
                detail,
                ""
                if free
                else "Stop the conflicting service or remap the port in "
                "docker-compose.yml -- a bound port turns into a failed install "
                "in front of the customer.",
            )
        )
    return findings


def check_network(probe: Probe) -> list[Finding]:
    findings: list[Finding] = []
    proxies = proxy_env(probe.env)
    findings.append(
        Finding(
            "PF-043",
            "Proxy environment",
            INFO if not proxies else WARN,
            ", ".join(proxies) if proxies else "no proxy variables set",
            ""
            if not proxies
            else "Corporate egress proxy in play: confirm NO_PROXY covers the "
            "database and host.docker.internal, and that the proxy allows CONNECT.",
        )
    )

    for code, host, purpose in (
        ("PF-040", DEFAULT_REGISTRY_HOST, "container image pulls"),
        ("PF-041", DEFAULT_PROVIDER_HOST, "LLM provider API"),
    ):
        try:
            infos = probe.resolve(host, 443)
            addrs = sorted({info[4][0] for info in infos})
            findings.append(
                Finding(code, f"DNS: {host}", OK, f"{purpose}; resolves to {', '.join(addrs[:3])}")
            )
        except Exception as exc:
            findings.append(
                Finding(
                    code,
                    f"DNS: {host}",
                    egress_severity(probe.airgap),
                    f"{purpose}; resolution failed ({type(exc).__name__})",
                    "Expected in an air-gapped install (images come from the "
                    "bundle). On a connected box this blocks install or answers.",
                )
            )
            continue
        connected, detail = probe.tcp_connect(host, 443)
        findings.append(
            Finding(
                ("PF-042" if code == "PF-040" else "PF-044"),
                f"TCP 443: {host}",
                OK if connected else egress_severity(probe.airgap),
                f"{purpose}; {detail}",
                "" if connected else "Open egress to this host:port in the firewall policy.",
            )
        )

    probe_result = probe.https_head(f"https://{DEFAULT_PROVIDER_HOST}/")
    error = probe_result.get("error") or ""
    if error:
        severity, remediation = tls_error_classification(error)
        findings.append(
            Finding(
                "PF-045",
                "TLS trust chain (provider)",
                severity,
                f"HTTPS probe failed: {error}",
                remediation,
            )
        )
    else:
        findings.append(
            Finding(
                "PF-045",
                "TLS trust chain (provider)",
                OK,
                f"HTTPS {probe_result.get('status')}, leaf issuer="
                f"{probe_result.get('issuer') or 'unknown'}",
            )
        )

    # Clock skew, measured against the provider's own Date header.
    server_date = probe_result.get("server_date")
    if not server_date:
        findings.append(
            Finding(
                "PF-046",
                "Clock skew",
                INFO,
                "no reference clock available (provider unreachable or no Date header)",
                "Verify NTP/chrony is active: skew breaks TLS and JWT validation.",
            )
        )
    else:
        import time as _time

        skew = _time.time() - float(server_date)
        findings.append(
            Finding(
                "PF-046",
                "Clock skew",
                clock_skew_severity(skew),
                f"local clock is {skew:+.1f}s from the provider's Date header "
                f"(warn >= {CLOCK_SKEW_WARN_S}s, blocker >= {CLOCK_SKEW_BLOCKER_S}s)",
                ""
                if clock_skew_severity(skew) == OK
                else "Enable NTP/chrony on this host before deploying.",
            )
        )
    return findings


def check_env_file(probe: Probe) -> list[Finding]:
    findings: list[Finding] = []
    env_path = probe.repo_root / ".env"
    if not env_path.exists():
        findings.append(
            Finding(
                "PF-050",
                "Environment file",
                BLOCKER,
                f"{env_path} not found",
                "Copy .env.example to .env and fill it in (never commit it).",
            )
        )
        return findings
    values: dict[str, str] = {}
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    except Exception as exc:
        findings.append(
            Finding(
                "PF-050",
                "Environment file",
                WARN,
                f"{env_path} unreadable ({type(exc).__name__})",
            )
        )
        return findings

    findings.append(
        Finding(
            "PF-050",
            "Environment file",
            OK,
            f"{env_path} present with {len(values)} keys (values never printed)",
        )
    )
    issues = missing_env_keys(values)
    hard = [issue for issue in issues if "required" in issue]
    soft = [issue for issue in issues if "required" not in issue]
    findings.append(
        Finding(
            "PF-051",
            "Required settings",
            BLOCKER if hard else OK,
            "; ".join(hard) if hard else "DATABASE_URL present",
        )
    )
    findings.append(
        Finding(
            "PF-052",
            "Optional settings",
            WARN if soft else OK,
            "; ".join(soft) if soft else "GROQ_API_KEY and ADMIN_TOKEN present",
        )
    )
    state_dir = values.get("OPS_STATE_FILE", "var/ops_state.json")
    state_path = Path(state_dir)
    if not state_path.is_absolute():
        state_path = probe.repo_root / state_path
    findings.append(
        Finding(
            "PF-053",
            "Operator state path",
            OK if state_path.parent.exists() else INFO,
            f"{state_path} (parent exists: {state_path.parent.exists()})",
            ""
            if state_path.parent.exists()
            else "Created on first start. On a container install, mount this path "
            "on a volume so the kill switch survives container replacement.",
        )
    )
    return findings


def check_artifacts(probe: Probe) -> list[Finding]:
    """Images and corpus: what is already on this box vs what must be fetched."""
    findings: list[Finding] = []
    rc, out, _err = probe.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]
    )
    images = out.splitlines() if rc == 0 else []
    api_image = [image for image in images if image.startswith("schemegpt")]
    findings.append(
        Finding(
            "PF-060",
            "Stack images present",
            OK if api_image else (INFO if probe.airgap else WARN),
            ", ".join(api_image) if api_image else "no schemegpt image loaded yet",
            ""
            if api_image
            else "Run `deploy/field/bundle.sh --load` (air-gap) or let compose build.",
        )
    )
    corpus = probe.repo_root / "data" / "schemes"
    md_files = list(corpus.glob("*.md")) if corpus.exists() else []
    findings.append(
        Finding(
            "PF-061",
            "Corpus present",
            OK if md_files else WARN,
            f"{len(md_files)} markdown scheme records in {corpus}",
            "" if md_files else "Populate data/schemes before ingesting.",
        )
    )
    return findings


CHECKS = (
    check_platform,
    check_docker,
    check_resources,
    check_ports,
    check_network,
    check_env_file,
    check_artifacts,
)


def build_probe(repo_root: Path, airgap: bool) -> Probe:
    return Probe(
        repo_root=repo_root,
        airgap=airgap,
        resolve=socket.getaddrinfo,
        tcp_connect=_tcp_connect,
        https_head=_https_probe,
        which=shutil.which,
        run=_run,
        env=dict(os.environ),
    )


# --- reporting ---------------------------------------------------------------

_MARK = {OK: "[ok]  ", INFO: "[info]", WARN: "[warn]", BLOCKER: "[FAIL]"}


def print_report(
    findings: list[Finding], report: dict, verbose: bool = False
) -> None:
    print("SchemeGPT field preflight")
    print(f"  host      : {report['host']}")
    print(f"  repo      : {report['repo_root']}")
    print(f"  started   : {report['started_at']}")
    print(f"  mode      : {'air-gap (offline install)' if report['airgap'] else 'connected'}")
    print("")
    for finding in findings:
        print(f"{_MARK[finding.severity]} {finding.code} {finding.title}: {finding.detail}")
        if finding.remediation and (verbose or not finding.ok):
            print(f"         -> {finding.remediation}")
    counts = report["counts"]
    print("")
    print(
        f"{counts[BLOCKER]} blocker(s), {counts[WARN]} warning(s), "
        f"{counts[OK]} ok, {counts[INFO]} info"
    )
    print(f"verdict: {report['verdict']}")
    blockers = [f for f in findings if f.severity == BLOCKER]
    if blockers:
        print("")
        print("Resolve these before installing:")
        for finding in blockers:
            hint = f" -> {finding.remediation}" if finding.remediation else ""
            print(f"  {finding.code} {finding.title}: {finding.detail}{hint}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preflight a host for a SchemeGPT deployment."
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Deployment directory (defaults to the repository root).",
    )
    parser.add_argument(
        "--airgap",
        action="store_true",
        help="Offline install: unreachable registry/provider is expected, "
        "not a blocker.",
    )
    parser.add_argument("--json", default=None, help="Write the report as JSON here.")
    parser.add_argument(
        "--label",
        default="",
        help="Engagement/customer label recorded in the report.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    probe = build_probe(repo_root, airgap=args.airgap)

    findings: list[Finding] = []
    for check in CHECKS:
        try:
            findings.extend(check(probe))
        except Exception as exc:  # a broken check must not hide the rest
            findings.append(
                Finding(
                    "PF-999",
                    f"Internal check error ({check.__name__})",
                    WARN,
                    f"{type(exc).__name__}: {exc}",
                    "Report this as a tool bug; the remaining checks still ran.",
                )
            )

    counts = {
        severity: sum(1 for finding in findings if finding.severity == severity)
        for severity in (OK, INFO, WARN, BLOCKER)
    }
    code, verdict_text = verdict(findings)
    report = {
        "schema": 1,
        "tool": "schemegpt-preflight",
        "label": args.label,
        "host": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "repo_root": str(repo_root),
        "airgap": bool(args.airgap),
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "thresholds": {
            "disk_min_gb": DISK_MIN_GB,
            "disk_warn_gb": DISK_WARN_GB,
            "mem_min_gb": MEM_MIN_GB,
            "mem_warn_gb": MEM_WARN_GB,
            "clock_skew_warn_s": CLOCK_SKEW_WARN_S,
            "clock_skew_blocker_s": CLOCK_SKEW_BLOCKER_S,
        },
        "counts": counts,
        "verdict": verdict_text,
        "exit_code": code,
        "findings": [asdict(finding) for finding in findings],
    }

    print_report(findings, report, verbose=args.verbose)
    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport: {out_path}")
    return code


if __name__ == "__main__":
    sys.exit(main())
