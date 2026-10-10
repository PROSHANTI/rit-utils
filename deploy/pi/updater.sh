#!/bin/sh
# Only the fixed rit-utils app service is updated. State contains image IDs,
# not private environment values. The original Compose supplies all env/mounts.
set -eu
umask 077

DEPLOY_DIR=${DEPLOY_DIR:-/home/umbrel/rit-utils}
PROJECT=${PROJECT:-rit-utils-pi}
SERVICE=${SERVICE:-app}
APP_CONTAINER=${APP_CONTAINER:-rit-utils-pi-app}
IMAGE_REPOSITORY=${IMAGE_REPOSITORY:-proshanti/rit-utils}
CHANNEL=${CHANNEL:-pi}
STATE_DIR=${STATE_DIR:-/state}
POLL_SECONDS=${POLL_SECONDS:-300}
WAIT_SECONDS=${WAIT_SECONDS:-180}
STABLE_SECONDS=${STABLE_SECONDS:-20}
export DOCKER_HOST=unix:///var/run/docker.sock
unset DOCKER_CONTEXT DOCKER_API_VERSION

log() { printf '%s\n' "$*"; }
atomic_write() {
    path=$1
    shift
    printf '%s\n' "$@" > "$path.tmp" || return 1
    sync || return 1
    mv -f "$path.tmp" "$path" || return 1
    sync
}
valid_id() {
    case "$1" in sha256:*) ;; *) return 1 ;; esac
    hash=${1#sha256:}
    [ "${#hash}" = 64 ] || return 1
    case "$hash" in *[!0-9a-f]*) return 1 ;; esac
}
current_id() { docker inspect --format '{{.Image}}' "$APP_CONTAINER" 2>/dev/null; }
healthy() {
    [ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$APP_CONTAINER" 2>/dev/null)" = healthy ] || return 1
    docker exec "$APP_CONTAINER" python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3).close()" >/dev/null 2>&1
}
pause_updates() {
    atomic_write "$STATE_DIR/blocked" "$1" || return 1
    log "Updates paused: $1"
}
write_override() {
    valid_id "$1" || return 1
    printf 'services:\n  %s:\n    image: "%s"\n    pull_policy: never\n' "$SERVICE" "$1" > "$STATE_DIR/image.yml.tmp" || return 1
    mv -f "$STATE_DIR/image.yml.tmp" "$STATE_DIR/image.yml"
}
deploy_image() {
    image=$1
    valid_id "$image" || return 1
    docker image inspect "$image" >/dev/null 2>&1 || return 1
    write_override "$image" || return 1
    docker compose --env-file "$DEPLOY_DIR/deployment.env" \
      --project-directory "$DEPLOY_DIR" --project-name "$PROJECT" \
      -f "$DEPLOY_DIR/compose.yml" -f "$STATE_DIR/image.yml" \
      up --detach --no-deps --no-build --pull never \
      --wait --wait-timeout "$WAIT_SECONDS" "$SERVICE" >/dev/null 2>&1 || return 1
    [ "$(current_id)" = "$image" ] && healthy || return 1
    sleep "$STABLE_SECONDS"
    [ "$(current_id)" = "$image" ] && healthy
}
reject_id() {
    valid_id "$1" || return 1
    # Rejected releases remain rejected across restarts. No automatic retries.
    if ! grep -Fxq "$1" "$STATE_DIR/rejected" 2>/dev/null; then
        printf '%s\n' "$1" >> "$STATE_DIR/rejected" || return 1
        sync || return 1
    fi
}
rollback_pending() {
    previous=$(sed -n '1p' "$STATE_DIR/pending")
    candidate=$(sed -n '2p' "$STATE_DIR/pending")
    if ! valid_id "$previous" || ! valid_id "$candidate"; then
        pause_updates 'invalid pending journal'
        return 1
    fi
    actual=$(current_id || true)
    if [ -n "$actual" ] && [ "$actual" != "$previous" ] && [ "$actual" != "$candidate" ]; then
        pause_updates 'app image was changed outside the updater'
        return 1
    fi
    log 'Restoring the previous local image.'
    if ! deploy_image "$previous"; then
        pause_updates 'rollback failed; journal retained'
        return 1
    fi
    atomic_write "$STATE_DIR/last-good" "$previous" || return 1
    reject_id "$candidate" || return 1
    rm -f "$STATE_DIR/pending" || return 1
    sync || return 1
    log 'Previous image restored and healthy.'
}
poll_once() {
    [ ! -e "$STATE_DIR/blocked" ] || return 0
    if [ -e "$STATE_DIR/pending" ]; then
        rollback_pending || return 0
    fi
    if [ ! -e "$STATE_DIR/last-good" ]; then
        previous=$(current_id || true)
        if ! valid_id "$previous" || ! healthy; then
            pause_updates 'initial app must exist and be healthy'
            return 0
        fi
        atomic_write "$STATE_DIR/last-good" "$previous"
    fi
    previous=$(cat "$STATE_DIR/last-good")
    if ! valid_id "$previous"; then
        pause_updates 'invalid last-good image'
        return 0
    fi
    actual=$(current_id || true)
    if [ "$actual" != "$previous" ]; then
        pause_updates 'app image was changed outside the updater'
        return 0
    fi
    # A manually stopped or unhealthy app is left for an operator to inspect.
    healthy || return 0
    if ! docker pull --quiet "$IMAGE_REPOSITORY:$CHANNEL" >/dev/null 2>&1; then
        log 'Pi channel pull failed; current app is unchanged.'
        return 0
    fi
    candidate=$(docker image inspect --format '{{.Id}}' "$IMAGE_REPOSITORY:$CHANNEL" 2>/dev/null) || return 0
    valid_id "$candidate" || return 0
    [ "$candidate" != "$previous" ] || return 0
    if grep -Fxq "$candidate" "$STATE_DIR/rejected" 2>/dev/null; then
        return 0
    fi
    arch=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$candidate" 2>/dev/null) || return 0
    source=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$candidate" 2>/dev/null) || return 0
    revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$candidate" 2>/dev/null) || return 0
    if [ "$arch" != linux/arm64 ] || [ "$source" != https://github.com/PROSHANTI/rit-utils ] || [ "${#revision}" != 40 ]; then
        reject_id "$candidate"
        log 'Pi channel metadata rejected; current app is unchanged.'
        return 0
    fi
    case "$revision" in *[!0-9a-f]*) reject_id "$candidate"; return 0 ;; esac
    # Check local rollback availability before changing the app.
    docker image inspect "$previous" >/dev/null 2>&1 || {
        pause_updates 'previous image is missing locally'
        return 0
    }
    atomic_write "$STATE_DIR/pending" "$previous" "$candidate" || return 1
    log "Installing Pi commit $revision."
    if deploy_image "$candidate"; then
        atomic_write "$STATE_DIR/last-good" "$candidate" || return 1
        rm -f "$STATE_DIR/pending" || return 1
        sync || return 1
        log "Pi commit $revision is healthy."
    else
        log 'Candidate failed its health check.'
        rollback_pending || true
    fi
}

for tool in docker flock sync grep sed; do
    command -v "$tool" >/dev/null 2>&1 || { log "Required utility missing: $tool"; exit 1; }
done
case "$SERVICE" in ''|*[!a-zA-Z0-9_-]*) log 'Invalid app service'; exit 1 ;; esac
for number in "$POLL_SECONDS" "$WAIT_SECONDS" "$STABLE_SECONDS"; do
    case "$number" in ''|*[!0-9]*) log 'Invalid polling/health interval'; exit 1 ;; esac
done
[ -f "$DEPLOY_DIR/compose.yml" ] && [ -f "$DEPLOY_DIR/deployment.env" ] || { log 'Deployment files missing'; exit 1; }
mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/controller.lock"
flock -n 9 || { log 'Another rit-utils updater owns the state'; exit 1; }
docker version >/dev/null 2>&1 || { log 'Docker API/socket check failed'; exit 1; }
docker compose version >/dev/null 2>&1 || { log 'Docker Compose unavailable'; exit 1; }
log 'RIT Utils Pi updater started.'
if [ "${1:-}" = --once ]; then
    poll_once
else
    while :; do
        poll_once
        sleep "$POLL_SECONDS"
    done
fi
