#!/usr/bin/env bash
set -eu
# Read-only, no credentials or environment emitted.
for url in https://codeduel.online https://codeduel.online/api/explore/problems http://127.0.0.1:8085/healthz; do
  curl --max-time 15 -sS -o /dev/null -w "$url %{http_code} %{time_total}s\n" "$url" || true
done
docker ps -a --filter label=com.docker.compose.project=codeduel --format '{{.Names}} {{.Status}}'
systemctl is-active docker cloudflared tailscaled ssh
