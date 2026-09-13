# Deployment and operation

Production target: `hp@100.98.193.60`, `/home/hp/ai-home-lab-operator`. Existing CodeDuel remains in `/opt/codeduel` and is never managed by this Compose project.

## Private access and credentials

Web app: `http://100.98.193.60:3080`, over Tailscale. Next.js binds only the server's Tailscale IP; localhost backend checks use `http://127.0.0.1:18000/health`. Loopback frontend access can use an SSH forward to the Tailscale-bound listener:

```bash
ssh -L 3080:100.98.193.60:3080 hp@100.98.193.60
```

Generated operator password and API credentials are in server `.env` (0600). SSH credentials are not saved in the repository. `AIOPS_ADMIN_PASSWORD` is the browser sign-in password. `SESSION_SECRET` signs an HttpOnly SameSite=Strict eight-hour cookie. HTTP cookies are permitted for the Tailscale-only endpoint; Tailscale encrypts the transport. Configure HTTPS and COOKIE_SECURE=true before exposing outside that network.

Reasoning defaults to local Ollama. To opt into Gemini, add `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=<restricted key>` to the server's private `.env`; keep `GEMINI_MODEL=gemini-3.8-flash` and `GEMINI_THINKING_LEVEL=low` unless a measured evaluation justifies a change. Do not pass keys as CLI arguments or commit them. Gemini sends bounded redacted diagnostic context to Google, so review SECURITY.md first. Ollama still runs when local RAG is enabled because it supplies embeddings.

No public hostname is configured. Existing remote-managed Cloudflare ingress currently contains only codeduel.online/www.codeduel.online -> localhost8085. To add an AI hostname later, use the existing tunnel's dashboard, add a dedicated loopback web listener, authentication/access policy and HTTPS, and preserve both existing CodeDuel routes. Do not publish Ollama, gateway, PostgreSQL or Qdrant.

## Initial installation

Inspect inventory first and choose unused ports. Docker and Compose must already work. With a clean copy of this project:

```bash
python3 scripts/init_env.py
mkdir -p data/ollama data/qdrant
# Owner1000 must own these two data directories (the deployed hp user has UID1000).
docker compose pull ollama postgres qdrant
docker compose up -d ollama postgres qdrant
docker compose exec ollama ollama pull qwen2.5:3b
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull all-minilm
sudo bash scripts/install_gateway.sh
docker compose build backend frontend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Gateway installation needs `python3.14-venv` on this Ubuntu26.04 host. It creates `/opt/aiops-gateway`, `/etc/aiops-gateway.env`, `/var/lib/aiops-gateway`, `aiops-gateway` system user and `aiops-gateway.service`. Gateway code/config are root-owned; persistent writes are restricted to its approval ledger directory, with a separate private temporary directory. Its Docker group privilege is a trusted security boundary with host-root-equivalent power; see SECURITY.md.

The checked-in environment example starts with backend writes disabled. The current server `.env` and installed gateway enable writes only for `aiops-demo`; all 22 preexisting containers remain read-only, and no systemd service is writable. `config/gateway.json` is the source policy, while the running gateway reads its installed copy at `/opt/aiops-gateway/config/gateway.json`. Editing the source does not change the installed policy until an intentional gateway update. Enabling production targets requires validation with the actually configured reasoning model on at least three scenarios and a separate scope/verification review; a passing deterministic demo does not satisfy that model-validation gate.

Production services use `unless-stopped`, resource limits, health checks and rotated Docker logs. Gateway is enabled with systemd and restarts on failure. Existing Docker/Tailscale services were already enabled. If the Tailscale interface is late after reboot, the frontend restarts until binding succeeds. No full machine reboot is necessary for installation.

## Operate only this project

From `/home/hp/ai-home-lab-operator`:

```bash
# State and logs
docker compose ps
docker compose logs --tail 100 backend frontend ollama
sudo journalctl -u aiops-gateway -n 100 --no-pager
# Start/restart the new app (never existing production containers)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose restart backend frontend
sudo systemctl restart aiops-gateway
# Stop the new app; volumes remain
docker compose stop
sudo systemctl stop aiops-gateway
# Create local database/config/runbook backup
bash scripts/backup.sh
# Recheck preexisting production baseline
bash scripts/check_production.sh
```

Never use `docker system prune`, reset Docker/networking, or remove existing volumes. Do not run `down -v`. Updates to the gateway must use the installer so root-owned code is replaced intentionally; it backs up this project's gateway environment/config first.

## Migrations, runbooks and evaluations

Backend startup runs `alembic -c backend/alembic.ini upgrade head`; schema is versioned. Runbook ingestion uses authenticated POST `/api/runbooks/ingest` after local embedding model download. It stores vectors in a model-specific Qdrant collection. Resolved incidents are embedded only after configured verification checks succeed. Re-ingesting unchanged runbooks updates deterministic IDs.

```bash
# Tests on a development environment
pip install -r backend/requirements-dev.txt
pytest
# Deterministic synthetic regression (no production tools)
python -m evals.run
# Actual local-model benchmark against mocked infrastructure
python -m evals.run --provider ollama --model qwen2.5:3b
# Actual Gemini benchmark; reads GEMINI_API_KEY from the private environment
python -m evals.run --provider gemini --model gemini-3.8-flash
```

Do not present scripted benchmark accuracy as model accuracy. Evaluation reports identify their provider and fixture hash. Confidence is a model estimate with deterministic ceilings, not empirically calibrated probability.

## Backup and restore

`backup.sh` makes a PostgreSQL plain SQL dump plus the project environment, source configuration and runbooks in a mode-0700 directory. It does **not** back up the installed gateway policy, gateway signing environment, replay ledger, Qdrant storage, model files or application source. Keep copies on trusted local storage and record the application version and model names used with each backup.

For a coordinated application backup, stop only this project's backend/frontend and the gateway, run `scripts/backup.sh` while PostgreSQL remains running, and use the new backup directory for the following additional copies:

```bash
# Set this to the exact directory just reported by scripts/backup.sh.
backup_dir=backups/REPLACE_WITH_REPORTED_TIMESTAMP
sudo cp -a /var/lib/aiops-gateway "$backup_dir/gateway-state"
sudo cp -a /etc/aiops-gateway.env "$backup_dir/gateway-environment"
sudo cp -a /opt/aiops-gateway/config/gateway.json "$backup_dir/installed-gateway-config.json"
# Copy vector storage only while this project's Qdrant is stopped.
docker compose stop qdrant
sudo cp -a data/qdrant "$backup_dir/qdrant"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d qdrant backend frontend
sudo systemctl start aiops-gateway
```

Stop active investigations before this maintenance window. If an approval dispatch has an uncertain outcome, inspect its target before maintenance; do not retry it. Copying SQLite while the gateway is stopped preserves its consumed-action ledger consistently. Preserve the most recent ledger during database rollback: restoring an older ledger could forget a previously used approval. If ledger history is unavailable, keep writes disabled, rotate the approval signing secret in both services, and invalidate restored pending proposals before allowing any new approval.

Restore PostgreSQL into a **new empty database** rather than importing a plain dump over existing tables. With backend/frontend stopped and a fresh current backup retained, the following example leaves the existing `aiops` database untouched:

```bash
# Select the intended backup and an unused restore database name first.
backup_dir=backups/REPLACE_WITH_SELECTED_TIMESTAMP
restore_db=aiops_restore_20260909
gzip -t "$backup_dir/postgres.sql.gz"
docker compose exec -T postgres createdb -U aiops "$restore_db"
gzip -dc "$backup_dir/postgres.sql.gz" | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U aiops -d "$restore_db"
```

Check the command exit status, schema version and incident/action counts. Intentionally update only the database name in the server's `DATABASE_URL` after validation, preserving its credentials and mode 0600, then recreate backend/frontend with the production Compose files. Keep the previous database for rollback. Apply migrations only with an inspected compatible application version. These steps are restore guidance; a full disaster-recovery rehearsal has not been recorded.

Restore Qdrant's matching `data/qdrant` copy with Qdrant stopped, retaining its UID/GID 1000 ownership. Runbooks can also be rebuilt through authenticated `/api/runbooks/ingest`. There is currently no bulk command to rebuild historical incident vectors from PostgreSQL; database rows alone do not automatically repopulate Qdrant after loss. Preserve its coordinated backup when incident search continuity matters. Ollama models reside in `data/ollama`; the original PostgreSQL data volume is `aiops_postgres_data`.

## Limits

CPU investigations may take minutes. One incident runs at a time. Model/token/time/step limits fail safely. Investigation interrupted by backend restart becomes FAILED with a clear message; writes are not replayed. Manual Verify recovery checks administrator-defined service/dependency health, not arbitrary model claims. Service restarts are implemented but excluded from live allowlists until a narrow host authorization policy is deliberately configured.

## Canonical Git workflow (completion checkpoint)

Mac source is `/Users/parthmudgal/Documents/ChatGPT/HomeserverAI`. The private repository is `Parthmudgal15105/HomeAiAgent`, branch `main`. Run tests and `python3 scripts/secret_scan.py --staged` before committing. Push on the Mac, then on the Ubuntu target run:

```bash
cd /home/hp/ai-home-lab-operator
bash scripts/deploy.sh
```

The script requires a clean `main` checkout and an existing private `.env`; it pulls with `--ff-only`, backs up project state, builds only operator containers, updates only the dedicated gateway, waits for health, and compares existing CodeDuel health before/after. Gateway installation requires sudo. No GitHub Action deploys automatically. Final source/deployment parity must be verified by comparing Mac, GitHub `main` and server `git rev-parse HEAD`. Archive-to-Git conversion completed on10 September2026, preserving runtime state. Backend/frontend image revision labels are also verified against Git HEAD. Consult IMPLEMENTATION.md for the latest deployed commit and acceptance state.

Service definitions are in `config/topology.json`. Each entry supports name, type, description, public_urls, local_health_urls, containers, systemd_services, depends_on, tags and explicit health_checks. Set overview:true to sample up to two declared checks in the overview. Add every target separately to `config/gateway.json`; service metadata does not grant gateway permissions. Validate the JSON with backend tests and update the root-owned gateway through the deployment script. No agent-code change is required to add a workload.
