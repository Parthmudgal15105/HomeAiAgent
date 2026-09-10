#!/usr/bin/env bash
# New AI project only. Run from its directory. Secrets/backups stay on the server.
set -euo pipefail
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="backups/$stamp"
mkdir -p "$backup_dir"
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$backup_dir/postgres.sql.gz"
cp .env "$backup_dir/environment"
cp -R config runbooks "$backup_dir/"
# Qdrant runbooks are reproducible; resolved incident text is preserved in Postgres.
printf 'Backup created at %s\n' "$backup_dir"
