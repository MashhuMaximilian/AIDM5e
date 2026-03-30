#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/aidm}"
BRANCH="${2:-main}"

echo "Deploying AIDM from branch '${BRANCH}' into '${APP_DIR}'"

cd "${APP_DIR}"

mkdir -p audio_files voice_context offline_test_outputs
touch transcript.txt transcript_manifest.json transcript_archive.txt

git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

docker compose up -d --build --force-recreate
docker compose ps
docker image prune -f >/dev/null 2>&1 || true

echo "Deployment finished."
