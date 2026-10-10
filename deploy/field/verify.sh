#!/usr/bin/env bash
# Verify a SchemeGPT bundle before loading anything.
#
#   ./verify.sh                        checksums only
#   ./verify.sh --signature            checksums + detached signature
#
# Exit codes: 0 verified, 1 verification failed, 2 usage/inputs missing.
#
# This runs on the customer's side of the air gap, where the only thing you can
# trust is the checksum you were given out of band — and, when a signature is
# present, the public key you pinned.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SIGNATURE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --signature) CHECK_SIGNATURE=1; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

cd "${DIR}"

[ -f SHA256SUMS ] || { echo "FATAL: SHA256SUMS is missing; this is not a bundle." >&2; exit 2; }
[ -f MANIFEST.json ] || { echo "FATAL: MANIFEST.json is missing; this is not a bundle." >&2; exit 2; }

if ! sha256sum -c SHA256SUMS; then
  echo "FATAL: checksum verification failed. Do not load these images." >&2
  exit 1
fi
echo "checksums: verified"

if [ "${CHECK_SIGNATURE}" -eq 1 ]; then
  if [ ! -f SHA256SUMS.sig ] || [ ! -f signing-key.pub.pem ]; then
    echo "FATAL: --signature asked for, but SHA256SUMS.sig / signing-key.pub.pem are not in this bundle." >&2
    exit 2
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    echo "FATAL: openssl is required to verify the signature." >&2
    exit 2
  fi
  if ! openssl dgst -sha256 -verify signing-key.pub.pem -signature SHA256SUMS.sig SHA256SUMS >/dev/null; then
    echo "FATAL: signature verification failed." >&2
    exit 1
  fi
  echo "signature: verified (key: signing-key.pub.pem; see SIGNING.md for what this proves)"
fi

python3 - <<'PY' || true
import json, pathlib
manifest = json.loads(pathlib.Path("MANIFEST.json").read_text(encoding="utf-8"))
print(f"bundle : {manifest['bundle']}")
print(f"version: {manifest['version']} (git {manifest['git_sha'][:12]}{'-dirty' if manifest.get('git_dirty') else ''})")
for image in manifest["images"]:
    print(f"  {image['role']:>3}: {image['image']} ({image['artifact_sha256'][:12]}...)")
PY

echo "OK: bundle verified"
