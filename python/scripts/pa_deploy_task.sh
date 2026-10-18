#!/usr/bin/env bash
# One-shot PythonAnywhere scheduled task: extract, install, boot-check, mark.
# Invoked by the GitHub Actions deploy script via the Schedule API:
#   bash pa_deploy_task.sh <sha> <tarball-name>
set -euo pipefail

SHA="${1:?usage: pa_deploy_task.sh <sha> <tarball-name>}"
TARBALL_NAME="${2:?usage: pa_deploy_task.sh <sha> <tarball-name>}"

DEPLOY_DIR="${HOME}/skillet-data/deploy"
APP_DIR="${HOME}/skillet"
VENV_DIR="${HOME}/skillet-venv"
TARBALL="${DEPLOY_DIR}/${TARBALL_NAME}"
MARKER="${HOME}/skillet-data/last-deploy-${SHA}"
LOG="${HOME}/skillet-data/deploy-task.log"

exec >>"${LOG}" 2>&1
echo "==== deploy ${SHA} starting $(date -u +%FT%TZ)"

if [ ! -f "${TARBALL}" ]; then
  echo "ERROR: tarball not found: ${TARBALL}"
  exit 1
fi

mkdir -p "${APP_DIR}"
tar -xzf "${TARBALL}" -C "${APP_DIR}" --strip-components=1

if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

# Boot the app once: applies Alembic migrations and proves imports work.
(
  cd "${APP_DIR}"
  "${VENV_DIR}/bin/python" -c "from wsgi import app; print('boot ok', app.name)"
)

date -u +%FT%TZ >"${HOME}/skillet-data/last-deploy"
echo "${SHA}" >"${MARKER}"
echo "==== deploy ${SHA} done $(date -u +%FT%TZ)"
