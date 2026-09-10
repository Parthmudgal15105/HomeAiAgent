#!/usr/bin/env bash
# Run on Ubuntu from the canonical Git checkout. Never touches other Compose projects.
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
[[ $(git branch --show-current) == main ]] || { echo 'Deploy only main'; exit 1; }
[[ -z $(git status --porcelain) ]] || { echo 'Commit or preserve local changes before deployment'; exit 1; }
[[ -f .env ]] || { echo 'Server .env is required; deployment never creates or replaces it'; exit 1; }
[[ -z $(git ls-files .env .local-access.txt) ]] || { echo 'Credential files must not be tracked'; exit 1; }
git remote get-url origin >/dev/null
previous_commit=$(git rev-parse HEAD)
environment_hash=$(sha256sum .env | cut -d' ' -f1)
mkdir -p reports/private
python3 scripts/deployment_health.py --production-only > reports/private/production-before.json
git pull --ff-only origin main
if [[ $previous_commit != $(git rev-parse HEAD) ]]; then
  # Run the fetched script from its beginning rather than continue stale logic.
  exec bash scripts/deploy.sh
fi
[[ $(git rev-parse HEAD) == $(git rev-parse origin/main) ]] || { echo 'HEAD differs from origin/main'; exit 1; }
python3 scripts/secret_scan.py --tracked
export APP_REVISION=$(git rev-parse HEAD)
bash scripts/backup.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml build backend frontend
# Installer updates only the dedicated gateway, preserving its replay ledger.
sudo bash scripts/install_gateway.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --wait --wait-timeout 180 postgres qdrant ollama backend frontend
[[ $environment_hash == $(sha256sum .env | cut -d' ' -f1) ]] || { echo 'Environment unexpectedly changed'; exit 1; }
python3 scripts/deployment_health.py --baseline reports/private/production-before.json
git rev-parse HEAD > reports/private/deployed-commit.txt
printf 'Deployed %s (previous source %s)\n' "$(git rev-parse HEAD)" "$previous_commit"
