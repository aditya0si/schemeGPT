#!/usr/bin/env bash
# Install (or restart) the SchemeGPT stack on this host from a verified bundle.
#
#   ./install.sh                  connected install (registry reachable)
#   ./install.sh --airgap         offline install: egress failures are expected
#   ./install.sh --wait 600       health-gate timeout in seconds (default 420)
#   ./install.sh --skip-preflight do not run the host preflight doctor
#   ./install.sh --skip-smoke     do not run the end-to-end /query smoke
#
# Order of operations, deliberately:
#   1. verify checksums (never load an unverified image),
#   2. load images (no build, no registry),
#   3. refuse to start without a .env (secrets are never generated for you),
#   4. preflight the host and fail on blockers,
#   5. start the stack and wait for a *real* health gate,
#   6. smoke the product path and record what mode answered,
#   7. write the deploy record.
#
# Exit codes: 0 installed and healthy, 1 failed a gate, 2 missing input.

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

AIRGAP=0
RUN_PREFLIGHT=1
RUN_SMOKE=1
WAIT_SECONDS=420
VERSION_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --airgap) AIRGAP=1; shift ;;
    --skip-preflight) RUN_PREFLIGHT=0; shift ;;
    --skip-smoke) RUN_SMOKE=0; shift ;;
    --wait) WAIT_SECONDS="${2:?--wait needs seconds}"; shift 2 ;;
    --version) VERSION_OVERRIDE="${2:?--version needs a value}"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

detect_python
command -v docker >/dev/null 2>&1 || die "docker is required."
started_at="$(now_utc)"

# --- 1. verify ---------------------------------------------------------------
if [ -f "${FIELD_DIR}/verify.sh" ] && [ -f "${FIELD_DIR}/SHA256SUMS" ]; then
  log "Verifying bundle checksums"
  if [ -f "${FIELD_DIR}/SHA256SUMS.sig" ]; then
    bash "${FIELD_DIR}/verify.sh" --signature || die "bundle verification failed; refusing to install."
  else
    bash "${FIELD_DIR}/verify.sh" || die "bundle verification failed; refusing to install."
  fi
else
  warn "No bundle checksums found beside install.sh; assuming a repository install."
fi

# --- 2. manifest / version ---------------------------------------------------
BUNDLE_VERSION="${VERSION_OVERRIDE}"
if [ -z "${BUNDLE_VERSION}" ] && [ -f "${FIELD_DIR}/MANIFEST.json" ]; then
  BUNDLE_VERSION="$("${PYTHON}" - "${FIELD_DIR}/MANIFEST.json" <<'PY'
import json, pathlib, sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")).get("version", ""))
PY
)"
fi
[ -n "${BUNDLE_VERSION}" ] || BUNDLE_VERSION="dev"
API_IMAGE="${SCHEMEGPT_API_IMAGE:-schemegpt-api:${BUNDLE_VERSION}}"
log "Installing version ${BUNDLE_VERSION} (api image: ${API_IMAGE})"

# --- 3. load images ----------------------------------------------------------
if [ -d "${FIELD_DIR}/images" ]; then
  for artifact in "${FIELD_DIR}"/images/*.tar.gz; do
    [ -e "${artifact}" ] || continue
    log "Loading $(basename "${artifact}")"
    gunzip -c "${artifact}" | docker load
  done
  # Bundles carry versioned tags; make the compose defaults point at them.
  if docker image inspect "${API_IMAGE}" >/dev/null 2>&1; then
    docker tag "${API_IMAGE}" "schemegpt-api:latest"
  fi
  if docker image inspect "schemegpt-web:${BUNDLE_VERSION}" >/dev/null 2>&1; then
    docker tag "schemegpt-web:${BUNDLE_VERSION}" "schemegpt-web:latest"
  fi
  if docker image inspect "schemegpt-db:${BUNDLE_VERSION}" >/dev/null 2>&1; then
    docker tag "schemegpt-db:${BUNDLE_VERSION}" "pgvector/pgvector:pg16"
  fi
else
  log "No images/ directory: compose will build or pull what it needs."
fi

# --- 4. environment ----------------------------------------------------------
ENV_FILE="${REPO_ROOT}/.env"
if [ ! -f "${ENV_FILE}" ]; then
  if [ -f "${FIELD_ROOT_TEMPLATE:-${FIELD_DIR}/.env.example}" ]; then
    cp "${FIELD_DIR}/.env.example" "${ENV_FILE}"
    warn "Created ${ENV_FILE} from the example template."
  fi
  cat >&2 <<'MSG'

STOP: no .env found for this deployment.

Fill in at least DATABASE_URL and (for live answers) GROQ_API_KEY, then re-run.
An ADMIN_TOKEN is strongly recommended: without it the operator endpoints
(/ops/ai, /ops/provider, /ops/audit, /ingest) return 503 by design.

    $EDITOR .env
    ./install.sh --airgap

MSG
  exit 2
fi
log "Using environment file ${ENV_FILE}"

# --- 5. preflight ------------------------------------------------------------
PREFLIGHT_ARGS=(--repo-root "${REPO_ROOT}" --label "install-${BUNDLE_VERSION}")
[ "${AIRGAP}" -eq 1 ] && PREFLIGHT_ARGS+=(--airgap)
PREFLIGHT_ARGS+=(--json "${REPORTS_DIR}/preflight-install-$(date -u +%Y%m%dT%H%M%SZ).json")
PREFLIGHT_EXIT=0
if [ "${RUN_PREFLIGHT}" -eq 1 ]; then
  log "Running host preflight"
  "${PYTHON}" "${FIELD_DIR}/preflight.py" "${PREFLIGHT_ARGS[@]}" || PREFLIGHT_EXIT=$?
  if [ "${PREFLIGHT_EXIT}" -eq 1 ]; then
    die "preflight found blockers; fix them or re-run with --skip-preflight (not recommended)."
  fi
else
  log "Preflight skipped by request"
fi

# --- 6. start ----------------------------------------------------------------
log "Starting the stack (docker compose up -d --no-build db api)"
compose_up_core
compose_up_frontends

log "Waiting up to ${WAIT_SECONDS}s for the health gate (/health + /ops/status)"
HEALTH_SECONDS="$(wait_for_health "${WAIT_SECONDS}")" || {
  RECORD="$(deploy_record install_failed "{\"version\": \"${BUNDLE_VERSION}\", \"airgap\": ${AIRGAP}, \"stage\": \"health_gate\"}")"
  die "health gate failed after ${WAIT_SECONDS}s. Diagnostics: docker compose ps / logs. Record: ${RECORD}"
}
log "Healthy after ${HEALTH_SECONDS}s"

# --- 7. smoke ----------------------------------------------------------------
SMOKE_RESULT="000:none:0"
VECTORS="-1"
if [ "${RUN_SMOKE}" -eq 1 ]; then
  log "Smoke: POST /query"
  SMOKE_RESULT="$(api_smoke "How much income support does PM-KISAN provide?")"
  case "${SMOKE_RESULT}" in
    000:*) die "product smoke test failed (no HTTP response): ${SMOKE_RESULT}" ;;
    *) log "Smoke answered: ${SMOKE_RESULT}" ;;
  esac
  VECTORS="$(vector_count)"
  log "Vector store rows: ${VECTORS}"
  case "${SMOKE_RESULT}" in
    200:live:*) : ;;
    200:degraded:*)
      warn "Answers are in degraded (retrieval-only) mode — expected if the AI kill switch is engaged."
      ;;
    200:demo:*)
      warn "Answers are in demo mode: no GROQ_API_KEY configured for this instance."
      ;;
    *) warn "Unexpected smoke result: ${SMOKE_RESULT}" ;;
  esac
fi

# --- 8. record ---------------------------------------------------------------
write_deployed_state "${BUNDLE_VERSION}" "${API_IMAGE}" "" ""
OPS_SUMMARY="$(http_json "${API_URL}/ops/status" 5)"
OPS_AI_STATE="$("${PYTHON}" -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("ai",{}).get("state","unknown"))' <<<"${OPS_SUMMARY}" 2>/dev/null || echo unknown)"
RECORD="$(deploy_record install "{\"version\": \"${BUNDLE_VERSION}\", \"airgap\": ${AIRGAP}, \"health_seconds\": ${HEALTH_SECONDS}, \"smoke\": \"${SMOKE_RESULT}\", \"vectors\": ${VECTORS}, \"ai_state\": \"${OPS_AI_STATE}\", \"preflight_exit\": ${PREFLIGHT_EXIT}, \"started_at\": \"${started_at}\"}")"

cat <<MSG

SchemeGPT ${BUNDLE_VERSION} is up.

  API       : ${API_URL}          (docs at ${API_URL}/docs)
  Web UI    : http://127.0.0.1:3000
  Streamlit : http://127.0.0.1:8501
  Operator  : ${API_URL}/ops/status
  AI state  : ${OPS_AI_STATE}
  Vectors   : ${VECTORS} rows
  Record    : ${RECORD}

Next: run docs/FIELD-DEPLOY.md §Verify, and keep ADMIN_TOKEN out of shell history
(export it from a file with \`set -a; . ./ops.env; set +a\`).
MSG
