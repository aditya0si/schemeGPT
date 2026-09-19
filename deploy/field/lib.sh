#!/usr/bin/env bash
# Shared helpers for the SchemeGPT field kit (preflight / bundle / install /
# upgrade / rollback). Sourced, never executed directly.
#
# Conventions this kit holds to, because field work is where conventions die:
#   * Every action writes a JSON record under deploy/field/logs/ with the
#     version it started from, the version it ended at, timings, and the health
#     gate result. If an engagement is ever questioned, that file is the answer.
#   * A readiness gate that cannot prove the service is healthy fails the
#     deploy. "It started" is not "it works".
#   * Nothing here deletes data. Destructive options exist only behind explicit
#     flags and are named as such.

set -euo pipefail

FIELD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The kit runs in two layouts: inside the repository (deploy/field/, compose
# two levels up) and unpacked from a delivery bundle (compose beside it).
if [ -n "${SCHEMEGPT_ROOT:-}" ]; then
  REPO_ROOT="$(cd "${SCHEMEGPT_ROOT}" && pwd)"
elif [ -f "${FIELD_DIR}/../docker-compose.yml" ]; then
  REPO_ROOT="$(cd "${FIELD_DIR}/.." && pwd)"
elif [ -f "${FIELD_DIR}/docker-compose.yml" ]; then
  REPO_ROOT="${FIELD_DIR}"
else
  REPO_ROOT="$(cd "${FIELD_DIR}/../.." && pwd)"
fi

LOG_DIR="${SCHEMEGPT_LOG_DIR:-${FIELD_DIR}/logs}"
STATE_DIR="${SCHEMEGPT_STATE_DIR:-${FIELD_DIR}/state}"
BACKUP_DIR="${SCHEMEGPT_BACKUP_DIR:-${FIELD_DIR}/backups}"
REPORTS_DIR="${SCHEMEGPT_REPORTS_DIR:-${FIELD_DIR}/reports}"

PROJECT_NAME="${SCHEMEGPT_PROJECT:-schemegpt}"
COMPOSE_FILE="${SCHEMEGPT_COMPOSE:-${REPO_ROOT}/docker-compose.yml}"
API_URL="${SCHEMEGPT_API_URL:-http://127.0.0.1:8000}"
DB_SERVICE="db"
API_SERVICE="api"

mkdir -p "${LOG_DIR}" "${STATE_DIR}" "${BACKUP_DIR}" "${REPORTS_DIR}"

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
warn() { printf '[%s] WARN: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
die()  { printf '[%s] FATAL: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; exit 1; }

# The kit is Python-assisted (preflight, JSON records); require a *working* one.
detect_python() {
  # Windows makes this non-obvious: `python3` can resolve to the Microsoft Store
  # alias stub, which exists on PATH, prints "Python was not found" and does not
  # run — so `command -v` is not evidence. Execute each candidate instead, and
  # honour an explicit override (a deployment usually has a venv):
  #   export SCHEMEGPT_PYTHON=./.venv/Scripts/python.exe
  if [ -n "${PYTHON:-}" ] && ${PYTHON} -c 'import sys' >/dev/null 2>&1; then
    return 0
  fi
  local candidate
  for candidate in "${SCHEMEGPT_PYTHON:-}" python3 python "py -3"; do
    [ -n "${candidate}" ] || continue
    if ${candidate} -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PYTHON="${candidate}"
      # Exported so child processes (and any script this one shells out to) see
      # the same interpreter. Note the trap this closes: detect_python called
      # from inside a command substitution sets PYTHON only in that subshell,
      # so a script that later uses ${PYTHON} in its own shell must call
      # detect_python itself first — every script in this kit does.
      export PYTHON
      return 0
    fi
  done
  die "no working Python 3.9+ interpreter found (on Windows 'python3' is often the Microsoft Store alias stub, which exists but does not run). Install Python or set SCHEMEGPT_PYTHON=/path/to/python3."
}

compose() {
  # Two env files, on purpose:
  #   .env                 application settings (and secrets) for the containers,
  #   state/deploy.env     deployment pinning written by this kit (image refs).
  # Keeping them apart means the app never sees deployment plumbing, and this
  # kit never rewrites a file that holds customer secrets.
  # Paths are converted for the native docker CLI (see to_native_path).
  local args=(--project-name "${PROJECT_NAME}" -f "$(to_native_path "${COMPOSE_FILE}")" \
              --env-file "$(to_native_path "${REPO_ROOT}/.env")")
  [ -f "${STATE_DIR}/deploy.env" ] && \
    args+=(--env-file "$(to_native_path "${STATE_DIR}/deploy.env")")
  docker compose "${args[@]}" "$@"
}

compose_up_core() {
  # Bring up the services the field kit owns. The web and streamlit frontends
  # are optional extras (a customer install may not want the demo UI), so they
  # are never required for an install, an upgrade or a rollback to succeed.
  compose up -d --no-build "${DB_SERVICE}" "${API_SERVICE}"
}

compose_up_frontends() {
  # Best-effort: only services whose images are already present.
  for service in web streamlit; do
    if docker image inspect "schemegpt-${service}:latest" >/dev/null 2>&1; then
      compose up -d --no-build "${service}" || warn "could not start ${service}"
    fi
  done
}

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

to_native_path() {
  # A path that bash understands is not always a path that Python understands:
  # git-bash/MSYS hands out /c/Users/... while native Windows Python needs
  # C:/Users/.... cygpath -m converts between them; on Linux cygpath is absent
  # and the path is already native, so the helper is a pass-through there.
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

json_write() {
  # json_write <path> <json-string>
  local path="$1" payload="$2"
  detect_python
  "${PYTHON}" - "$(to_native_path "${path}")" "$payload" <<'PY'
import json, sys, pathlib
path, payload = sys.argv[1], sys.argv[2]
try:
    data = json.loads(payload)
except Exception as exc:
    raise SystemExit(f"invalid JSON payload for {path}: {exc}")
pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
}

# --- service health ----------------------------------------------------------

http_code() {
  # http_code <url> [timeout] -> prints the status code, or 000 on failure
  local url="$1" timeout="${2:-5}"
  detect_python
  "${PYTHON}" - "$url" "$timeout" <<'PY'
import sys, urllib.request, urllib.error
url, timeout = sys.argv[1], float(sys.argv[2])
try:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        print(response.status)
except urllib.error.HTTPError as exc:
    print(exc.code)
except Exception:
    print("000")
PY
}

http_json() {
  # http_json <url> [timeout] -> prints the body, or empty on failure
  local url="$1" timeout="${2:-5}"
  detect_python
  "${PYTHON}" - "$url" "$timeout" <<'PY'
import sys, urllib.request
url, timeout = sys.argv[1], float(sys.argv[2])
try:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        print(response.read().decode("utf-8", "replace"))
except Exception:
    print("")
PY
}

wait_for_health() {
  # wait_for_health <timeout_seconds> -> 0 when the service is actually up.
  #
  # The gate is /health (which proves the API answered *and* its database probe
  # succeeded). /ops/status is checked too, but a 404 is accepted: that is what
  # an older build without the operator control plane returns, and this kit must
  # be able to upgrade *from* one of those. Prints elapsed seconds on success.
  local timeout="${1:-420}" started elapsed body ops_code
  started="$(date +%s)"
  while :; do
    elapsed=$(( $(date +%s) - started ))
    if [ "${elapsed}" -ge "${timeout}" ]; then
      warn "health gate timed out after ${timeout}s"
      return 1
    fi
    body="$(http_json "${API_URL}/health" 5)"
    if printf '%s' "${body}" | grep -q '"status": *"ok"\|"status":"ok"'; then
      ops_code="$(http_code "${API_URL}/ops/status" 5)"
      case "${ops_code}" in
        200) echo "${elapsed}"; return 0 ;;
        404) warn "/ops/status absent (pre-field-layer build); accepting /health only."
             echo "${elapsed}"; return 0 ;;
      esac
    fi
    sleep 5
  done
}

api_smoke() {
  # api_smoke <question> -> prints the mode reported by POST /query, or 000
  detect_python
  "${PYTHON}" - "$API_URL" "${1:-How much income support does PM-KISAN provide?}" <<'PY'
import json, sys, urllib.request
api, question = sys.argv[1], sys.argv[2]
payload = json.dumps({"question": question}).encode()
request = urllib.request.Request(
    f"{api}/query", data=payload, headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode())
        print(f"{response.status}:{body.get('mode')}:{len(body.get('sources') or [])}")
except Exception as exc:
    print(f"000:{type(exc).__name__}:0")
PY
}

vector_count() {
  # vector_count -> row count in the vector store, or -1 when it cannot be read
  local out
  out="$(compose exec -T "${DB_SERVICE}" psql -U scheme -d schemegpt -tAc \
        "select count(*) from langchain_pg_embedding" 2>/dev/null | tr -d '[:space:]')" || out=""
  case "${out}" in
    ''|*[!0-9]*) echo "-1" ;;
    *) echo "${out}" ;;
  esac
}

# --- deployment state --------------------------------------------------------

write_deployed_state() {
  # write_deployed_state <version> <image_ref> <previous_version> <previous_image>
  local version="$1" image="$2" prev_version="${3:-}" prev_image="${4:-}"
  json_write "${STATE_DIR}/deployed.json" "$(cat <<JSON
{
  "version": "${version}",
  "image": "${image}",
  "previous_version": "${prev_version}",
  "previous_image": "${prev_image}",
  "updated_at": "$(now_utc)"
}
JSON
)"
}

read_state_field() {
  # read_state_field <field> -> value or empty
  local field="$1" file="${STATE_DIR}/deployed.json"
  [ -f "${file}" ] || { echo ""; return 0; }
  detect_python
  "${PYTHON}" - "$(to_native_path "${file}")" "$field" <<'PY'
import json, sys, pathlib
data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get(sys.argv[2], "")
print("" if value is None else value)
PY
}

docker_image_present() {
  # docker_image_present <image> -> 0 when the daemon has it; otherwise 1 with
  # docker's own message in DOCKER_ERROR.
  #
  # This exists because `docker image inspect X >/dev/null 2>&1 || die "not
  # present"` is a lie when docker never ran: a broken CLI, an unreachable
  # daemon or (on Windows) a bash that cannot see Docker Desktop's pipe all
  # produce the same "not present" verdict. In the field that sends you to
  # rebuild an image that was already there. Keep the tool's own words.
  local image="$1" message
  if message="$(docker image inspect "${image}" 2>&1 >/dev/null)"; then
    DOCKER_ERROR=""
    return 0
  fi
  DOCKER_ERROR="${message:-no output from docker}"
  return 1
}

set_api_image() {
  # set_api_image <image_ref> — pin the API image for compose substitution.
  # Written to state/deploy.env (not .env): deployment pinning is this kit's
  # business, the application's env file is not.
  local image="$1" deploy_env="${STATE_DIR}/deploy.env" tmp
  mkdir -p "${STATE_DIR}"
  tmp="$(mktemp)"
  [ -f "${deploy_env}" ] && grep -v '^SCHEMEGPT_API_IMAGE=' "${deploy_env}" > "${tmp}" || true
  printf '# written by the field kit (%s); compose reads this file after .env\nSCHEMEGPT_API_IMAGE=%s\n' \
    "$(now_utc)" "${image}" >> "${tmp}"
  cat "${tmp}" > "${deploy_env}"
  rm -f "${tmp}"
  log "Pinned SCHEMEGPT_API_IMAGE=${image} in deploy/field/state/deploy.env"
}

snapshot_db() {
  # snapshot_db <label> -> prints the backup path
  local label="$1" path
  path="${BACKUP_DIR}/$(date -u +%Y%m%dT%H%M%SZ)-${label}.sql"
  log "Snapshotting the database to ${path}"
  if ! compose exec -T "${DB_SERVICE}" pg_dump -U scheme -d schemegpt > "${path}"; then
    rm -f "${path}"
    die "database snapshot failed; refusing to upgrade without a rollback point."
  fi
  local size
  size="$(wc -c < "${path}" | tr -d ' ')"
  [ "${size}" -gt 1000 ] || die "database snapshot looks empty (${size} bytes); aborting."
  echo "${path}"
}

deploy_record() {
  # deploy_record <action> <json_extra_object>
  local action="$1" extra="${2:-\{\}}" path
  path="${LOG_DIR}/$(date -u +%Y%m%dT%H%M%SZ)-${action}.json"
  json_write "${path}" "$(cat <<JSON
{
  "schema": 1,
  "action": "${action}",
  "at": "$(now_utc)",
  "host": "$(hostname)",
  "project": "${PROJECT_NAME}",
  "compose_file": "${COMPOSE_FILE}",
  "extra": ${extra}
}
JSON
)"
  echo "${path}"
}
