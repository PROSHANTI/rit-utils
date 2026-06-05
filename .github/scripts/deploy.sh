#!/usr/bin/env bash
set -euo pipefail

DEPLOY_MODE="${DEPLOY_MODE:-ssh}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_TAG="${IMAGE_TAG:0:12}"
DEPLOY_DIR="${DEPLOY_DIR:-${HOME}/rit-utils}"

run_compose() {
  cd "${DEPLOY_DIR}"
  export IMAGE_TAG
  if command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
  else
    DC="docker compose"
  fi
  ${DC} -f docker-compose.production.yml pull
  ${DC} -f docker-compose.production.yml down
  ${DC} -f docker-compose.production.yml up -d
  ${DC} -f docker-compose.production.yml ps
}

sync_configs() {
  mkdir -p "${DEPLOY_DIR}/nginx/conf.d"
  cp docker-compose.production.yml "${DEPLOY_DIR}/"
  cp -r nginx "${DEPLOY_DIR}/"
}

deploy_local() {
  echo "Local deploy to ${DEPLOY_DIR} with IMAGE_TAG=${IMAGE_TAG}"
  sync_configs
  run_compose
}

deploy_ssh() {
  if [ -z "${DEPLOY_HOST:-}" ] || [ -z "${DEPLOY_USER:-}" ]; then
    echo "::error::DEPLOY_HOST and DEPLOY_USER must be configured in repository secrets"
    exit 1
  fi

  mkdir -p ~/.ssh
  printf '%s\n' "$SSH_KEY" > ~/.ssh/deploy_key
  chmod 600 ~/.ssh/deploy_key

  eval "$(ssh-agent -s)"
  if [ -n "${SSH_PASSPHRASE:-}" ]; then
    echo "$SSH_PASSPHRASE" | ssh-add ~/.ssh/deploy_key
  else
    ssh-add ~/.ssh/deploy_key
  fi

  SSH_PORT="${SSH_PORT:-22}"
  REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"
  REMOTE_DIR="/home/${DEPLOY_USER}/rit-utils"
  SSH_OPTS="-p ${SSH_PORT} -o ConnectTimeout=60 -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new -o BatchMode=yes"

  echo "SSH deploy to ${REMOTE}:${REMOTE_DIR} with IMAGE_TAG=${IMAGE_TAG}"

  ssh-keyscan -T 15 -p "${SSH_PORT}" -H "${DEPLOY_HOST}" >> ~/.ssh/known_hosts 2>/dev/null \
    || echo "Warning: ssh-keyscan could not fetch host key, continuing with accept-new"

  echo "Creating remote directories..."
  ssh ${SSH_OPTS} "${REMOTE}" "mkdir -p ${REMOTE_DIR}/nginx/conf.d"

  echo "Copying docker-compose.production.yml..."
  scp ${SSH_OPTS} docker-compose.production.yml "${REMOTE}:${REMOTE_DIR}/"

  echo "Copying nginx config..."
  scp ${SSH_OPTS} -r nginx "${REMOTE}:${REMOTE_DIR}/"

  echo "Running docker-compose on remote server..."
  ssh ${SSH_OPTS} "${REMOTE}" bash -s <<EOF
set -euo pipefail
cd "${REMOTE_DIR}"
export IMAGE_TAG="${IMAGE_TAG}"
if command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  DC="docker compose"
fi
\$DC -f docker-compose.production.yml pull
\$DC -f docker-compose.production.yml down
\$DC -f docker-compose.production.yml up -d
\$DC -f docker-compose.production.yml ps
EOF
}

case "${DEPLOY_MODE}" in
  local) deploy_local ;;
  ssh) deploy_ssh ;;
  *)
    echo "::error::Unknown DEPLOY_MODE=${DEPLOY_MODE}. Use 'ssh' or 'local'."
    exit 1
    ;;
esac
