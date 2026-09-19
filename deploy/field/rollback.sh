#!/usr/bin/env bash
# Roll a SchemeGPT deployment back to the previously deployed version.
#
#   ./rollback.sh                                    # back to the recorded previous version
#   ./rollback.sh --to-version v1.0.0                # explicit target
#   ./rollback.sh --to-version v1.0.0 --restore-db backups/....sql
#
# The image swap is the fast path and is always safe for the application code.
# The database is separate: a schema migration is *not* undone by running the
# old image, so restoring a dump is a destructive, explicit choice. That is why
# --restore-db takes a file path and prints what it is about to destroy. The
# rule of thumb for a customer deployment: if the failed release changed the
# schema, roll the code back first, confirm the service is healthy, and only
# then decide whether the data needs restoring.
#
# Exit codes: 0 rolled back and healthy, 1 the rollback did not reach health,
# 2 bad input.

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

TO_VERSION=""
TO_IMAGE=""
WAIT_SECONDS=420
RESTORE_DB=""
RESTORE_ENV=""

while [ $# -gt 0 ]; do
  case "$1" in
    --to-version) TO_VERSION="${2:?--to-version needs a value}"; shift 2 ;;
    --to-image) TO_IMAGE="${2:?--to-image needs a value}"; shift 2 ;;
    --wait) WAIT_SECONDS="${2:?--wait needs seconds}"; shift 2 ;;
    --restore-db) RESTORE_DB="${2:?--restore-db needs a file path}"; shift 2 ;;
    --restore-env) RESTORE_ENV="${2:?--restore-env needs a file path}"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

CURRENT_VERSION="$(read_state_field version)"
CURRENT_IMAGE="$(read_state_field image)"

if [ -z "${TO_VERSION}" ]; then
  TO_VERSION="$(read_state_field previous_version)"
  TO_IMAGE="$(read_state_field previous_image)"
fi
if [ -z "${TO_VERSION}" ]; then
  die "no rollback target: pass --to-version (the deploy state has no previous_version)."
fi
[ -n "${TO_IMAGE}" ] || TO_IMAGE="schemegpt-api:${TO_VERSION}"
docker_image_present "${TO_IMAGE}" || \
  die "target image ${TO_IMAGE} is not available to docker (docker said: ${DOCKER_ERROR}); load it before rolling back."

STARTED_AT="$(now_utc)"
log "Rollback: ${CURRENT_VERSION:-unknown} -> ${TO_VERSION} (${TO_IMAGE})"

if [ -n "${RESTORE_DB}" ]; then
  [ -f "${RESTORE_DB}" ] || die "restore file ${RESTORE_DB} not found."
  warn "About to restore the database from ${RESTORE_DB} (destructive: current data is replaced)."
  compose exec -T "${DB_SERVICE}" psql -U scheme -d schemegpt -c \
    "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
  compose exec -T "${DB_SERVICE}" psql -U scheme -d schemegpt < "${RESTORE_DB}" >/dev/null
  log "Database restored from ${RESTORE_DB}"
else
  log "Database left as-is (no --restore-db given)."
fi

if [ -n "${RESTORE_ENV}" ]; then
  [ -f "${RESTORE_ENV}" ] || die "environment snapshot ${RESTORE_ENV} not found."
  cp "${RESTORE_ENV}" "${REPO_ROOT}/.env"
  log "Restored the environment file from ${RESTORE_ENV}"
else
  log "Environment file left as-is (no --restore-env given)."
fi

set_api_image "${TO_IMAGE}"
compose_up_core

if ! HEALTH_SECONDS="$(wait_for_health "${WAIT_SECONDS}")"; then
  RECORD="$(deploy_record rollback_failed "{\"from_version\": \"${CURRENT_VERSION}\", \"to_version\": \"${TO_VERSION}\", \"to_image\": \"${TO_IMAGE}\", \"restored_db\": \"${RESTORE_DB}\", \"started_at\": \"${STARTED_AT}\"}")"
  die "rollback did not reach health within ${WAIT_SECONDS}s. Record: ${RECORD}"
fi

SMOKE_RESULT="$(api_smoke "How much income support does PM-KISAN provide?")"
VECTORS="$(vector_count)"
write_deployed_state "${TO_VERSION}" "${TO_IMAGE}" "${CURRENT_VERSION}" "${CURRENT_IMAGE}"
RECORD="$(deploy_record rollback "{\"from_version\": \"${CURRENT_VERSION}\", \"to_version\": \"${TO_VERSION}\", \"to_image\": \"${TO_IMAGE}\", \"health_seconds\": ${HEALTH_SECONDS}, \"smoke\": \"${SMOKE_RESULT}\", \"vectors\": ${VECTORS}, \"restored_db\": \"${RESTORE_DB}\", \"started_at\": \"${STARTED_AT}\"}")"

cat <<MSG

Rolled back to ${TO_VERSION}.

  health gate : ${HEALTH_SECONDS}s
  smoke       : ${SMOKE_RESULT}
  vectors     : ${VECTORS} rows
  database    : ${RESTORE_DB:+restored from ${RESTORE_DB}}${RESTORE_DB:-left as-is}
  record      : ${RECORD}

MSG
