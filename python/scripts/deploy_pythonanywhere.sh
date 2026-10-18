#!/usr/bin/env bash
# Deploy a packaged Skillet app to PythonAnywhere headlessly.
#
# The broken-by-design Console API means we can't run shell commands on a
# console directly; instead we:
#   1. upload a tarball of the app via the Files API
#   2. upload this repo's deploy task script alongside it
#   3. create a one-shot scheduled task that extracts + installs + boots
#   4. poll for the completion marker the task writes
#   5. reload the webapp and smoke-check it
#
# Required env: PA_USERNAME, PA_API_TOKEN, PA_APP_NAME (webapp domain, e.g.
# "yourname.pythonanywhere.com"). Optional: PA_HOST (www|eu, default www).
#
# Usage: deploy_pythonanywhere.sh <tarball> <sha>

set -euo pipefail

TARBALL="${1:?usage: deploy_pythonanywhere.sh <tarball> <sha>}"
SHA="${2:?usage: deploy_pythonanywhere.sh <tarball> <sha>}"

: "${PA_USERNAME:?PA_USERNAME is required}"
: "${PA_API_TOKEN:?PA_API_TOKEN is required}"
: "${PA_APP_NAME:?PA_APP_NAME is required}"

HOST="${PA_HOST:-www}"
API="https://${HOST}.pythonanywhere.com/api/v0/user/${PA_USERNAME}"
AUTH=(-H "Authorization: Bearer ${PA_API_TOKEN}")
REMOTE_DIR="/home/${PA_USERNAME}/skillet-data/deploy"
TARBALL_NAME="$(basename "${TARBALL}")"

echo "==> Uploading ${TARBALL_NAME} (${SHA:0:7})"
curl -sf "${AUTH[@]}" -F "content=@${TARBALL}" \
  "${API}/files/path${REMOTE_DIR}/${TARBALL_NAME}" >/dev/null

echo "==> Uploading task script"
curl -sf "${AUTH[@]}" -F "content=@python/scripts/pa_deploy_task.sh" \
  "${API}/files/path${REMOTE_DIR}/pa_deploy_task.sh" >/dev/null

echo "==> Scheduling one-shot deploy task"
STARTED_AT="$(date -u -d '+15 seconds' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v+15S +%Y-%m-%dT%H:%M:%SZ)"
curl -sf -X POST "${AUTH[@]}" -H "Content-Type: application/json" \
  -d "{\"command\": \"bash ${REMOTE_DIR}/pa_deploy_task.sh ${SHA} ${TARBALL_NAME}\", \"label\": \"skillet-deploy-${SHA:0:7}\", \"enabled\": true, \"started_at\": \"${STARTED_AT}\", \"repeat\": \"daily\"}" \
  "${API}/schedule/" >/dev/null

echo "==> Waiting for deploy marker (timeout 15 min)"
DEADLINE=$(( $(date +%s) + 900 ))
MARKER="/home/${PA_USERNAME}/skillet-data/last-deploy-${SHA}"
while true; do
  if curl -sf "${AUTH[@]}" "${API}/files/path${MARKER}" >/dev/null 2>&1; then
    echo "    deploy task finished"
    break
  fi
  if [ "$(date +%s)" -ge "${DEADLINE}" ]; then
    echo "ERROR: timed out waiting for ${MARKER}" >&2
    exit 1
  fi
  sleep 15
done

echo "==> Reloading webapp ${PA_APP_NAME}"
curl -sf -X POST "${AUTH[@]}" "${API}/webapps/${PA_APP_NAME}/reload/" >/dev/null

echo "==> Smoke check https://${PA_APP_NAME}/"
for attempt in $(seq 1 10); do
  if curl -sf "https://${PA_APP_NAME}/" | grep -qi "skillet"; then
    echo "    OK"
    exit 0
  fi
  sleep 6
done
echo "ERROR: site did not respond with expected content" >&2
exit 1
