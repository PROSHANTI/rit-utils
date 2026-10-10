RIT Utils: branch pi, native ARM64 CI, outgoing Pi updates

Branch pi starts from the tested production commit
e18ba71c1ad606a0809768f7f6ff7492e1e74471 and builds native ARM64 images for
Raspberry Pi. Automatic legacy main/test workflows are paused while those
servers are unavailable: main.yml accepts workflow_dispatch only. Manual runs
execute CI without publishing or SSH deployment. Restore its push/pull_request
triggers for main/test when those targets return; Pi uses a separate pi.yml.

Repository file mapping
  pi.yml                -> .github/workflows/pi.yml
  arm64_pdf_smoke.py     -> .github/scripts/arm64_pdf_smoke.py
  notify_pi.py           -> .github/scripts/notify_pi.py
  test_notify_pi.py      -> .github/scripts/test_notify_pi.py
  updater.sh            -> deploy/pi/updater.sh
  compose.updater.yml   -> deploy/pi/compose.updater.yml
  test_updater.py        -> deploy/pi/test_updater.py
  README.txt             -> deploy/pi/README.txt
Local validation caches and source archives must not be copied into Git or
onto Pi.

Development flow
  Work in feature branches and open PRs with base pi. PRs run checks without
  publishing. A merge/push into pi runs native ARM64 checks, existing pytest,
  updater failure/recovery tests, image build and actual LibreOffice PDF smoke.
  The tested image is published once as proshanti/rit-utils:pi-<full-commit-SHA>.
  A rerun verifies/reuses an existing commit image; it never overwrites it.
  Only the current pi branch head moves proshanti/rit-utils:pi. No latest/main/
  test/buildcache tags are changed. Main changes enter pi through a manual PR.

Telegram notifications
  Pi push builds reuse TELEGRAM_TO and TELEGRAM_TOKEN from the existing repo
  secrets. A successful notification requires the Pi channel push to finish;
  stale commits skipped by the publish step send no success notification.
  The message confirms ARM64 tests and publication, with the commit description
  and Actions link. Actual Pi deployment happens later via its controller.
  Failed Pi push builds send an error notification with the Actions link.
  Pull requests and cancelled jobs do not send notifications or publish images.

The public repository uses the standard ubuntu-24.04-arm runner: native ARM64,
4 CPU and 16 GB RAM, currently free for public repositories. Private repository
runners use included minutes and differ in size. DockerHub publication reuses
DOCKER_USERNAME and DOCKER_PASSWORD from the existing workflow. Their values
were not inspected. The successful main push workflow for e18ba71 is evidence
they worked on 2026-10-01; the first Pi pipeline confirms current validity.

Pi controller installation
  App directory: /home/umbrel/rit-utils
  Base config: compose.yml and deployment.env
  Project/service/container: rit-utils-pi / app / rit-utils-pi-app
  Private inputs: private/.env plus the three existing read-only file binds.

  Copy updater.sh and compose.updater.yml to /home/umbrel/rit-utils/updater/.
  Then, using the existing Docker group access:
    docker compose -f /home/umbrel/rit-utils/updater/compose.updater.yml up -d updater
    docker logs --tail 30 rit-utils-pi-updater

The official docker:29.9.0-cli image is pinned by its verified index digest;
it has ARM64, flock and Compose 5.6.0. Pi Engine 28.5.0/API1.51 supports CLI
negotiation. Docker API version is not forced. The controller uses the local
Unix socket and polls the public DockerHub channel every five minutes. It adds
no listening ports and needs no remote SSH login or new registry credential.

Update behavior
  Pull finishes before the app is changed. Architecture, source and revision
  labels are checked. A release is deployed by its immutable local content ID.
  A persistent named volume stores last-good, pending journal and rejected IDs;
  flock excludes duplicate controllers. The base configuration is mounted at
  the same absolute host path, so Compose retains env, file mounts and network.
  Compose recreates only app, with --no-deps --no-build --pull never --wait.
  Healthy plus a live HTTP check are required, followed by 20 seconds stability.
  On failure the old local image is restored, checked, and that failed content
  ID is rejected across restarts. Pending journal after a crash is conservatively
  rolled back before registry polling. Images and private data are retained.
  An unexpected manual image change or failed rollback pauses future updates.

Operator controls
    docker stop rit-utils-pi-updater       # pause automatic updates
    docker start rit-utils-pi-updater      # resume when state still matches app
    docker logs --tail 30 rit-utils-pi-updater
    docker exec rit-utils-pi-updater cat /state/last-good
  A paused/blocked controller requires inspecting the running image and journal
  before reconciling state. Deployment/env/proxy changes are applied explicitly;
  the automatic controller changes the app image only.

Validation completed
  actionlint v1.7.12: PASS
  Python3.13.16, full e18ba71 checkout with the six draft files:
  Black26.5.1 --check .: PASS (29 files); Ruff0.16.9 check .: PASS
  mypy2.3.1 configured src/tests scope: PASS (27 files); explicit new
  .github/scripts/arm64_pdf_smoke.py and deploy/pi/test_updater.py: PASS (2 files)
  Existing pytest suite with public test credentials/SMTP mocks: 200 PASS
  Shell syntax and updater Compose config: PASS
  Seven actual-script tests against fake Docker: failed pull, successful update,
  health failure+rollback, pending crash recovery, missing-app recovery,
  repeated rejected image, unexpected manual image: PASS
  Exact Docker CI PDF command on native ARM64 runtime: PASS (20,800-byte PDF,
  real substitutions and LibreOffice, no private templates/network/SMTP)
  Official pinned CLI image read-only probe: ARM64, flock, Docker29.9.0,
  Compose5.6.0: PASS

Before installing the controller, require a successful Pi GitHub Actions run and
verify that its public image revision label matches the commit. After the first
automatic update, verify the running app image and repeat the HTTPS/login/static/
PDF/doctor-PPTX checks. Application deployments preserve private inputs.

Sources verified 2026-10-11
  https://docs.github.com/en/actions/reference/runners/github-hosted-runners
  https://docs.docker.com/reference/cli/docker/compose/up/
  https://docs.docker.com/engine/containers/start-containers-automatically/
  https://docs.docker.com/reference/cli/docker/image/pull/
  https://docs.docker.com/reference/api/engine/
  https://github.com/docker-library/docker/blob/623f4fd9a5abae2e72bda5c5d983bf9ff04a5a62/29/cli/Dockerfile
  https://github.com/PROSHANTI/rit-utils/actions/runs/36913194181
  https://github.com/PROSHANTI/rit-utils/blob/e18ba71c1ad606a0809768f7f6ff7492e1e74471/.github/workflows/main.yml

The original containrrr/watchtower repository was archived on 2025-12-17; this
draft uses official Docker CLI rather than selecting an unreviewed fork.
  https://github.com/containrrr/watchtower/discussions/2135
