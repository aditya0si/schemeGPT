"""End-to-end check of the bundle verification path.

Builds a miniature bundle (dummy artifacts, real checksums, real signature when
`openssl` is available) and runs the shipped `verify.sh` against it: an
unverified bundle must not be loadable, and a tampered one must be rejected.
This is the one part of the field kit that runs inside CI, because it is the
part that decides whether a customer's host will load our images.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIELD_DIR = REPO_ROOT / "deploy" / "field"
VERIFY = FIELD_DIR / "verify.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" and not shutil.which("bash"),
    reason="verify.sh needs a POSIX shell",
)


def make_bundle(tmp_path: Path, *, sign: bool = False) -> Path:
    """Create a bundle directory shaped like the real one."""
    bundle = tmp_path / "schemegpt-bundle-test"
    (bundle / "images").mkdir(parents=True)
    for name in ("api", "db"):
        (bundle / "images" / f"{name}.tar.gz").write_bytes(f"{name}-image-bytes".encode())
    manifest = {
        "schema": 1,
        "bundle": bundle.name,
        "version": "test",
        "git_sha": "0" * 40,
        "git_dirty": False,
        "images": [
            {
                "role": name,
                "image": f"schemegpt-{name}:test",
                "artifact": f"images/{name}.tar.gz",
                "artifact_sha256": "0" * 64,
            }
            for name in ("api", "db")
        ],
    }
    (bundle / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    shutil.copy(VERIFY, bundle / "verify.sh")

    subprocess.run(
        "sha256sum images/*.tar.gz > SHA256SUMS",
        shell=True,
        cwd=bundle,
        check=True,
        capture_output=True,
    )
    if sign:
        subprocess.run(
            "openssl genrsa -out key.pem 2048 && "
            "openssl rsa -in key.pem -pubout -out signing-key.pub.pem && "
            "openssl dgst -sha256 -sign key.pem -out SHA256SUMS.sig SHA256SUMS && "
            "rm -f key.pem",
            shell=True,
            cwd=bundle,
            check=True,
            capture_output=True,
        )
    return bundle


def run_verify(bundle: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "verify.sh", *args],
        cwd=bundle,
        capture_output=True,
        text=True,
        check=False,
    )


def test_valid_bundle_verifies(tmp_path):
    bundle = make_bundle(tmp_path)
    result = run_verify(bundle)
    assert result.returncode == 0, result.stderr
    assert "checksums: verified" in result.stdout
    assert "OK: bundle verified" in result.stdout


def test_tampered_artifact_is_rejected(tmp_path):
    bundle = make_bundle(tmp_path)
    with (bundle / "images" / "api.tar.gz").open("wb") as handle:
        handle.write(b"tampered")
    result = run_verify(bundle)
    assert result.returncode == 1
    assert "checksum verification failed" in result.stderr


def test_missing_checksums_is_not_a_bundle(tmp_path):
    bundle = make_bundle(tmp_path)
    (bundle / "SHA256SUMS").unlink()
    result = run_verify(bundle)
    assert result.returncode == 2
    assert "not a bundle" in result.stderr


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is not installed")
def test_signature_roundtrip_and_detection(tmp_path):
    bundle = make_bundle(tmp_path, sign=True)
    ok = run_verify(bundle, "--signature")
    assert ok.returncode == 0, ok.stderr
    assert "signature: verified" in ok.stdout

    # A tampered checksum file must fail signature verification even though the
    # artifacts themselves still match their (rewritten) checksums.
    sums = bundle / "SHA256SUMS"
    sums.write_text(sums.read_text() + "\n", encoding="utf-8")
    bad = run_verify(bundle, "--signature")
    assert bad.returncode == 1
    assert "signature verification failed" in bad.stderr


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is not installed")
def test_signature_requested_without_signature_files(tmp_path):
    bundle = make_bundle(tmp_path)
    result = run_verify(bundle, "--signature")
    assert result.returncode == 2
    assert "signature" in result.stderr.lower()
