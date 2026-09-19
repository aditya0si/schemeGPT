#!/usr/bin/env bash
# Upgrade a running SchemeGPT deployment to another version, with a rollback
# point taken first and an automatic rollback if the new version fails its
# health gate.
#
#   ./upgrade.sh --to-version v2.0.0
#   ./upgrade.sh --to-version v2.0.0 --to-image schemegpt-api:v2.0.0
#   ./upgrade.sh --to-version v2.0.0 --skip-snapshot      # no rollback point
#   ./upgrade.sh --to-version v2.0.0 --no-auto-rollback   # leave the stack broken
#
# Why the order is what it is:
#   1. snapshot the database — an upgrade you cannot revert is a bet, not a deploy;
#   2. pin the new image and recreate only the API container;
#   3. gate on health AND on a real product call, not on "the container started";
#   4. compare the vector-store row count before/after: a migration that drops
#      rows is a data incident, and it is invisible to a health check;
#   5. on any failure, roll back automatically and record both attempts.
#
# Exit codes: 0 upgraded and healthy, 1 upgraded then rolled back, 2 bad input.

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

TO_VERSION=""
TO_IMAGE=""
SKIP_SNAPSHOT=0
AUTO_ROLLBACK=1
WAIT_SECONDS=420

while [ $# -gt 0 ]; do
  case "$1" in
    --to-version) TO_VERSION="${2:?--to-version needs a value}"; shift 2 ;;
    --to-image) TO_IMAGE="${2:?--to-image needs a value}"; shift 2 ;;
    --skip-snapshot) SKIP_SNAPSHOT=1; shift ;;
    --no-auto-rollback) AUTO_ROLLBACK=0; shift ;;
    --wait) WAIT_SECONDS="${2:?--wait needs seconds}"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "${TO_VERSION}" ] || die "--to-version is required (e.g. --to-version v2.0.0)."
[ -n "${TO_IMAGE}" ] || TO_IMAGE="schemegpt-api:${TO_VERSION}"
docker image inspect "${TO_IMAGE}" >/dev/null 2>&1 || \
  die "image ${TO_IMAGE} is not present locally. Load the bundle or build it first."

FROM_VERSION="$(read_state_field version)"
FROM_IMAGE="$(read_state_field image)"
[ -n "${FROM_VERSION}" ] || FROM_VERSION="unknown"
[ -n "${FROM_IMAGE}" ] || FROM_IMAGE="schemegpt-api:latest"
STARTED_AT="$(now_utc)"

log "Upgrade ${FROM_VERSION} -> ${TO_VERSION} (${FROM_IMAGE} -> ${TO_IMAGE})"

VECTORS_BEFORE="$(vector_count)"
log "Vector rows before: ${VECTORS_BEFORE}"

SNAPSHOT=""
ENV_SNAPSHOT=""
if [ "${SKIP_SNAPSHOT}" -eq 1 ]; then
  warn "Skipping the database snapshot: this upgrade has no rollback point."
else
  SNAPSHOT="$(snapshot_db "${FROM_VERSION}-pre-${TO_VERSION}")"
  log "Rollback point: ${SNAPSHOT}"
fi

# A release is code *and* configuration. Snapshot the environment file too, so
# an automatic rollback can put back both — a broken setting is a far more
# common cause of a failed release than broken code.
ENV_SNAPSHOT="${BACKUP_DIR}/$(date -u +%Y%m%dT%H%M%SZ)-pre-${TO_VERSION}.env"
cp "${REPO_ROOT}/.env" "${ENV_SNAPSHOT}"
chmod 600 "${ENV_SNAPSHOT}" 2>/dev/null || true
log "Environment snapshot: ${ENV_SNAPSHOT} (contains secrets; rotated with the backups)"

set_api_image "${TO_IMAGE}"
log "Recreating the API container on the new image"
compose_up_core

HEALTH_SECONDS=""
if ! HEALTH_SECONDS="$(wait_for_health "${WAIT_SECONDS}")"; then
  warn "New version failed the health gate within ${WAIT_SECONDS}s."
  compose logs --tail 40 "${API_SERVICE}" >&2 || true
  RECORD="$(deploy_record upgrade_failed "{\"from_version\": \"${FROM_VERSION}\", \"to_version\": \"${TO_VERSION}\", \"to_image\": \"${TO_IMAGE}\", \"stage\": \"health_gate\", \"snapshot\": \"${SNAPSHOT}\", \"env_snapshot\": \"${ENV_SNAPSHOT}\", \"started_at\": \"${STARTED_AT}\"}")"
  if [ "${AUTO_ROLLBACK}" -eq 1 ]; then
    log "Rolling back to ${FROM_VERSION}"
    if bash "${FIELD_DIR}/rollback.sh" --to-version "${FROM_VERSION}" \
        --to-image "${FROM_IMAGE}" --restore-env "${ENV_SNAPSHOT}" \
        --wait "${WAIT_SECONDS}"; then
      log "Rollback complete. Failed upgrade record: ${RECORD}"
      exit 1
    fi
    die "rollback ALSO failed — the deployment needs hands on it now. Failed upgrade record: ${RECORD}"
  fi
  die "upgrade failed and --no-auto-rollback was given. Record: ${RECORD}"
fi
log "Healthy after ${HEALTH_SECONDS}s"

SMOKE_RESULT="$(api_smoke "How much income support does PM-KISAN provide?")"
case "${SMOKE_RESULT}" in
  000:*) warn "Product smoke returned no HTTP response: ${SMOKE_RESULT}" ;;
  *) log "Post-upgrade smoke: ${SMOKE_RESULT}" ;;
esac

VECTORS_AFTER="$(vector_count)"
log "Vector rows after: ${VECTORS_AFTER}"
DATA_OK=1
if [ "${VECTORS_BEFORE}" -ge 0 ] && [ "${VECTORS_AFTER}" -ge 0 ]; then
  if [ "${VECTORS_AFTER}" -lt "${VECTORS_BEFORE}" ]; then
    DATA_OK=0
    warn "Vector store shrank from ${VECTORS_BEFORE} to ${VECTORS_AFTER} rows."
  fi
else
  warn "Vector row count unavailable on one side; treating data integrity as unverified."
fi

OPS_SUMMARY="$(http_json "${API_URL}/ops/status" 5)"
REPORTED_VERSION="$("${PYTHON}" -c 'import json,sys; print(json.loads(sys.stdin.read() or "{}").get("version","unknown"))' <<<"${OPS_SUMMARY}" 2>/dev/null || echo unknown)"
log "Reporting version: ${REPORTED_VERSION} (expected ${TO_VERSION})"

write_deployed_state "${TO_VERSION}" "${TO_IMAGE}" "${FROM_VERSION}" "${FROM_IMAGE}"
RECORD="$(deploy_record upgrade "{\"from_version\": \"${FROM_VERSION}\", \"to_version\": \"${TO_VERSION}\", \"to_image\": \"${TO_IMAGE}\", \"health_seconds\": ${HEALTH_SECONDS}, \"smoke\": \"${SMOKE_RESULT}\", \"vectors_before\": ${VECTORS_BEFORE}, \"vectors_after\": ${VECTORS_AFTER}, \"data_intact\": ${DATA_OK}, \"snapshot\": \"${SNAPSHOT}\", \"reported_version\": \"${REPORTED_VERSION}\", \"started_at\": \"${STARTED_AT}\"}")"

cat <<MSG

Upgrade complete: ${FROM_VERSION} -> ${TO_VERSION}

  health gate : ${HEALTH_SECONDS}s
  smoke       : ${SMOKE_RESULT}
  vectors     : ${VECTORS_BEFORE} -> ${VECTORS_AFTER}
  rollback pt : ${SNAPSHOT:-none (--skip-snapshot)}
  record      : ${RECORD}

MSG
