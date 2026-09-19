#!/usr/bin/env bash
# Build an installable, verifiable SchemeGPT bundle for a customer environment.
#
# Output: deploy/field/bundles/schemegpt-bundle-<version>/
#           images/*.tar.gz        docker save output, one per image
#           MANIFEST.json          what is inside, by immutable image ID + digest
#           SHA256SUMS             checksum of every artifact
#           SHA256SUMS.sig         detached signature (with --sign)
#           signing-key.pub.pem    verification key (with --sign)
#           install.sh verify.sh preflight.py lib.sh docker-compose.yml .env.example
#           README-INSTALL.md
#         deploy/field/bundles/schemegpt-bundle-<version>.tar.gz
#
# The bundle is the air-gapped delivery format: the customer's network blocks
# the registry, so images travel as files, are checksummed, and are verified on
# the far side before anything is loaded.
#
# Usage:
#   bundle.sh [--version V] [--out DIR] [--no-build] [--sign] [--no-web] [--keep-dir]

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

VERSION=""
OUT_DIR="${FIELD_DIR}/bundles"
DO_BUILD=1
DO_SIGN=0
WITH_WEB=1
KEEP_DIR=0

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
    --out) OUT_DIR="${2:?--out needs a value}"; shift 2 ;;
    --no-build) DO_BUILD=0; shift ;;
    --sign) DO_SIGN=1; shift ;;
    --no-web) WITH_WEB=0; shift ;;
    --keep-dir) KEEP_DIR=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

detect_python
command -v docker >/dev/null 2>&1 || die "docker is required to build a bundle."

if [ -z "${VERSION}" ]; then
  VERSION="$(git -C "${REPO_ROOT}" describe --tags --always --dirty 2>/dev/null || echo dev)"
fi
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="$(git -C "${REPO_ROOT}" status --porcelain 2>/dev/null | head -c 200 || true)"

BUNDLE_NAME="schemegpt-bundle-${VERSION}"
BUNDLE_DIR="${OUT_DIR}/${BUNDLE_NAME}"
API_IMAGE="schemegpt-api:${VERSION}"
WEB_IMAGE="schemegpt-web:${VERSION}"
DB_IMAGE_SOURCE="pgvector/pgvector:pg16"
DB_IMAGE="schemegpt-db:${VERSION}"

log "Building bundle ${BUNDLE_NAME} (git ${GIT_SHA:0:12})"
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}/images"

if [ "${DO_BUILD}" -eq 1 ]; then
  log "Building API image ${API_IMAGE} (GIT_SHA=${GIT_SHA:0:12})"
  docker build \
    --build-arg "GIT_SHA=${GIT_SHA}" \
    -t "${API_IMAGE}" "${REPO_ROOT}"
  if [ "${WITH_WEB}" -eq 1 ]; then
    log "Building web image ${WEB_IMAGE}"
    docker build -t "${WEB_IMAGE}" "${REPO_ROOT}/web"
  fi
fi

log "Ensuring database image ${DB_IMAGE_SOURCE}"
docker image inspect "${DB_IMAGE_SOURCE}" >/dev/null 2>&1 || docker pull "${DB_IMAGE_SOURCE}"
docker tag "${DB_IMAGE_SOURCE}" "${DB_IMAGE}"

save_image() {
  # save_image <image> <basename>
  local image="$1" name="$2"
  docker image inspect "${image}" >/dev/null 2>&1 || die "image ${image} is not available locally."
  log "Saving ${image} -> images/${name}.tar.gz"
  docker save "${image}" | gzip -9 > "${BUNDLE_DIR}/images/${name}.tar.gz"
}

save_image "${API_IMAGE}" "api"
[ "${WITH_WEB}" -eq 1 ] && save_image "${WEB_IMAGE}" "web"
save_image "${DB_IMAGE}" "db"

log "Writing MANIFEST.json"
MANIFEST_IMAGES=""
for pair in "api:${API_IMAGE}" "db:${DB_IMAGE}"; do
  name="${pair%%:*}"; image="${pair#*:}"
  MANIFEST_IMAGES="${MANIFEST_IMAGES} ${name}=${image}"
done
[ "${WITH_WEB}" -eq 1 ] && MANIFEST_IMAGES="${MANIFEST_IMAGES} web=${WEB_IMAGE}"

detect_python
"${PYTHON}" - "${BUNDLE_DIR}" "${VERSION}" "${GIT_SHA}" "${GIT_DIRTY}" ${MANIFEST_IMAGES} <<'PY'
import hashlib, json, pathlib, subprocess, sys, datetime

bundle = pathlib.Path(sys.argv[1])
version, git_sha, git_dirty = sys.argv[2], sys.argv[3], sys.argv[4]
pairs = dict(item.split("=", 1) for item in sys.argv[5:])

images = []
for name, image in pairs.items():
    inspect = subprocess.run(
        ["docker", "image", "inspect", image, "--format",
         "{{.Id}}|{{.Size}}|{{join .RepoDigests \",\"}}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    image_id, size, digests = (inspect.split("|") + ["", ""])[:3]
    artifact = bundle / "images" / f"{name}.tar.gz"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    images.append({
        "role": name,
        "image": image,
        "image_id": image_id,
        "repo_digests": [d for d in digests.split(",") if d],
        "size_bytes": int(size or 0),
        "artifact": f"images/{artifact.name}",
        "artifact_bytes": artifact.stat().st_size,
        "artifact_sha256": digest,
    })

manifest = {
    "schema": 1,
    "bundle": bundle.name,
    "version": version,
    "git_sha": git_sha,
    "git_dirty": bool(git_dirty.strip()),
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "images": images,
    "install": {
        "entrypoint": "./install.sh",
        "airgap_flag": "--airgap",
        "verify_first": "./verify.sh",
    },
}
(bundle / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"manifest: {len(images)} image(s), version {version}")
PY

log "Writing checksums"
( cd "${BUNDLE_DIR}" && sha256sum images/*.tar.gz > SHA256SUMS )

if [ "${DO_SIGN}" -eq 1 ]; then
  log "Signing SHA256SUMS (ephemeral key: see SIGNING.md in the bundle)"
  ( cd "${BUNDLE_DIR}" && \
    openssl genrsa -out signing-key.ephemeral.pem 3072 2>/dev/null && \
    openssl rsa -in signing-key.ephemeral.pem -pubout -out signing-key.pub.pem 2>/dev/null && \
    openssl dgst -sha256 -sign signing-key.ephemeral.pem -out SHA256SUMS.sig SHA256SUMS && \
    rm -f signing-key.ephemeral.pem )
  cat > "${BUNDLE_DIR}/SIGNING.md" <<'MD'
# Bundle signing (what this signature does and does not prove)

`SHA256SUMS.sig` is a detached RSA-3072/SHA-256 signature over `SHA256SUMS`,
verifiable with the bundled `signing-key.pub.pem`:

    openssl dgst -sha256 -verify signing-key.pub.pem -signature SHA256SUMS.sig SHA256SUMS

It proves the checksums have not changed since signing. It does **not** prove
who signed them: the private key was generated for this build and deleted
immediately after signing, so there is no durable identity behind it.

In a customer engagement the durable version of this is a key you hold (or a
hardware/KMS key, or `cosign` with an OIDC identity) so the customer can pin
your public key out of band. Treat this as the mechanism, demonstrated, not as
a chain of trust.
MD
fi

log "Copying field kit into the bundle"
cp "${FIELD_DIR}/install.sh" "${FIELD_DIR}/verify.sh" "${FIELD_DIR}/lib.sh" \
   "${FIELD_DIR}/preflight.py" "${FIELD_DIR}/stub_provider.py" "${BUNDLE_DIR}/"
cp "${REPO_ROOT}/docker-compose.yml" "${BUNDLE_DIR}/docker-compose.yml"
cp "${REPO_ROOT}/.env.example" "${BUNDLE_DIR}/.env.example"
# .gitattributes pins LF for these files, but a bundle built from a Windows
# working copy must not ship CRLF: the target is a Linux host and a CRLF
# shebang fails there with "bad interpreter: ...^M".
for script in "${BUNDLE_DIR}"/*.sh; do
  [ -e "${script}" ] || continue
  sed -i 's/\r$//' "${script}"
done
[ -f "${REPO_ROOT}/docs/FIELD-DEPLOY.md" ] && \
  install -D "${REPO_ROOT}/docs/FIELD-DEPLOY.md" "${BUNDLE_DIR}/docs/FIELD-DEPLOY.md"
chmod +x "${BUNDLE_DIR}/install.sh" "${BUNDLE_DIR}/verify.sh"

cat > "${BUNDLE_DIR}/README-INSTALL.md" <<MD
# SchemeGPT ${VERSION} — install bundle

Artifacts were built from commit \`${GIT_SHA}\`.

## On the target host (no internet required)

    tar xzf $(basename "${BUNDLE_DIR}").tar.gz
    cd ${BUNDLE_NAME}
    ./verify.sh --signature        # checksums (+ signature when present)
    ./install.sh --airgap          # loads images, preflights, starts, health-gates

\`install.sh\` will stop and ask you to create \`.env\` from \`.env.example\`
before it starts anything: secrets are never guessed or generated silently.

Operator endpoints after install:

    curl -s http://127.0.0.1:8000/ops/status          # AI state, circuit, counters
    curl -s -X POST http://127.0.0.1:8000/ops/ai \\
         -H "X-Admin-Token: \$ADMIN_TOKEN" -H 'Content-Type: application/json' \\
         -d '{"enabled": false, "reason": "pilot review", "actor": "field-eng"}'

Full runbook: \`docs/FIELD-DEPLOY.md\`.
MD

log "Packing tarball"
( cd "${OUT_DIR}" && tar czf "${BUNDLE_NAME}.tar.gz" "${BUNDLE_NAME}" )
TARBALL="${OUT_DIR}/${BUNDLE_NAME}.tar.gz"
TARBALL_SHA="$(sha256sum "${TARBALL}" | cut -d' ' -f1)"

RECORD="$(deploy_record bundle "{\"version\": \"${VERSION}\", \"git_sha\": \"${GIT_SHA}\", \"signed\": ${DO_SIGN}, \"tarball\": \"${TARBALL}\", \"tarball_sha256\": \"${TARBALL_SHA}\", \"airgap_ready\": true}")"
log "Deploy record: ${RECORD}"

if [ "${KEEP_DIR}" -eq 0 ]; then
  log "Keeping both the directory and the tarball (remove the directory manually if space is tight)."
fi

log "Bundle ready:"
log "  dir     : ${BUNDLE_DIR}"
log "  tarball : ${TARBALL}"
log "  sha256  : ${TARBALL_SHA}"
