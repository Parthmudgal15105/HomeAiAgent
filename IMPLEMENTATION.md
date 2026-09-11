# Implementation status and resume guide

Last verified: 11 September 2026, 15:24 UTC. **Overall status: incomplete — deployment works, but actual-model acceptance has not passed.**

## Source and deployment identity

- Canonical Mac source: `/Users/parthmudgal/Documents/ChatGPT/HomeserverAI`.
- GitHub: private `Parthmudgal15105/HomeAiAgent`, branch `main`; authentication and push work.
- Ubuntu: `hp@100.98.193.60`, `/home/hp/ai-home-lab-operator`, now a Git checkout using a repository-only read-only deploy key.
- Last verified deployed source and backend/frontend image revision: `7b8cbfb68b7d63b580473fd37f9c3cbb9bd16b9f`, matching published main before this checkpoint.
- Dashboard: `http://100.98.193.60:3080` through Tailscale. Password handoff is in the Git-excluded local `.local-access.txt`; server secrets remain in server `.env`.

## Verified current state

- SSH reconnected today. All six platform containers and isolated demo are healthy. No unrelated production changes or reboot performed.
- Fresh complete Python suite: **152 passed** (backend, gateway, agent, fixtures, mocked recovery approval guards and deployment scanner). Last frontend validation: **9 tests passed**, typecheck and production build passed.
- Previous deployed acceptance: gateway **19/19** live diagnostics; authentication/logout and private component checks passed; backend/frontend image provenance matched Git HEAD. GitHub CI passed for `7b8cbfb`.
- Real local Ollama provider, typed constrained decisions, evidence persistence, evolving hypotheses, approval/replay protection, recovery verification, generic service topology, incident history and bounded server overview are implemented. Fourteen runbooks exist; final ingestion/retrieval recheck is pending.
- **Completed actual qwen2.5:3b eight-case benchmark: 0/8 root-cause accuracy, Top-3 1/8, average 4.125 executed tools and 265.24 seconds per case.** All eight stopped after repeated diagnostic requests; 24 duplicate attempts were rejected. No invalid JSON or unsafe action attempts were recorded. This model is not accepted for production reasoning on these results.
- Actual qwen3:4b comparison is running against the same eight fixtures/settings. Earlier standalone Redis success is a development result, not full-suite acceptance. See `reports/model-comparison/` for preserved measurements.
- A real-model mocked Redis approval/recovery/PostgreSQL/RAG acceptance runner now exists in `evals/remediation.py`. Its two security tests pass; its actual-model lifecycle has not yet been run.

## Remaining acceptance work (resume here)

1. Complete qwen3 eight-case evaluation; inspect failure causes, improve general model reliability if necessary, and repeat fair comparisons after any agent changes. Do not select a model based on JSON validity alone.
2. Run actual selected-model read-only server investigation and mocked Redis approval/recovery/history retrieval lifecycle. Do not cause a production outage.
3. Re-ingest fourteen runbooks; recheck retrieval, current live diagnostics, dashboard, private ports, resource usage and CodeDuel health.
4. Update all final evaluation/deployment docs with measured results, scan secrets, push and deploy the final exact Git commit; verify both checkout and image revision parity.

## Future session procedure

Read this current-state section first, then inspect `git status`, `git log -5`, `git remote -v`, server `git rev-parse HEAD`, `docker compose ps`, gateway status and CodeDuel health. Reuse existing data and architecture. Work only on Mac source; follow edit → tests/secret scan → commit → GitHub push → SSH → `bash scripts/deploy.sh` → verify matching commit. Never store credentials, generated logs or model files in Git. Never reboot or modify CodeDuel/SSH/Tailscale/Cloudflare configuration for operator development.

Every subsequent entry must record date, phase, changed files, decision, tests, deployment commit/result, remaining limitations and next action. Historical entries below describe their own time, not current completion.

---

# Implementation journal

This file records actual progress and validation. Items are not complete until tested.

## Phase 1 — inventory (complete)

Read the supplied full project brief and inspected hardware, OS, services, networking, firewalls, Docker containers, repository, production Compose, safe log samples and Cloudflare/Tailscale configuration. Recorded SERVER_INVENTORY.md. No production configuration changed. Important baseline: CodeDuel API and worker already fail to connect to external MongoDB Atlas; homepage works. Do not claim that deployment caused this incident or that CodeDuel is fully healthy.

## Foundation and model work (in progress)

Selected separate project namespace and CPU inference, no GPU driver installation. Backend and safe gateway are being implemented independently against explicit contracts. User-requested Next.js + local FastAPI/Postgres/Qdrant/Ollama supersedes cloud Sites runtime. Local-only deployment retains all data on server. Model selection will follow measured CPU latency and structured tool choice benchmarks.

## Foundation and diagnostic implementation

Implemented custom FastAPI/SQLAlchemy models, Alembic migration, typed bounded Ollama agent, persisted observations/hypotheses/audits and human approval state. Added eight synthetic scenarios using the production loop and fixture providers. Local tests currently pass; final test counts will be recorded after integration.

Implemented separate host gateway: 19 read-only tools, allowlists, schema validation, bounded subprocess pipes, HTTP address pinning/no redirects, secret redaction and HMAC-expiring one-use SQLite approval ledger. Installed only Python venv support packages (three new packages, no upgrades/removals; apt reported no service/container restarts needed). New dedicated gateway deployed under `/opt/aiops-gateway`, user aiops-gateway, loopback18081. Existing production service configs remain unchanged.

New PostgreSQL and Qdrant created in aiops Compose namespace with separate storage and loopback ports15432/16333. CPU Ollama image still downloading. Backend build encountered transient PyPI download timeouts; increased download retries/timeouts. Next.js dashboard with authentication, incident creation/history, timeline, hypotheses, report/approvals/topology passes production build and local HTTP200. Browser preview opened; WebMCP read-only current-investigation tool added with feature detection but no supported invocation validation yet.

## Integration validation —09 September07:40UTC

- Combined Python test environment aligned; **121 tests passed**, dependency check clean. Includes backend, gateway, fixture regressions and context-budget stress tests. Large log lists now compact structurally to24,863/26,000chars while preserving all18 tested observation IDs, error excerpts and tool constraints.
- New backend migration initially encountered AppleDouble metadata from macOS archive; excluded `._*` from image build. Migration and app then started successfully. Source transfer now uses Git-aware file enumeration, excluding local secrets and caches.
- PostgreSQL needed container initialization capabilities for ownership/drop-to-postgres; Qdrant needed a writable snapshots path. Corrected only new project config. Both healthy; Qdrant telemetry disabled.
- Next frontend on Tailscale3080 and backend loopback18000 healthy. Server-side checks passed: login200, unauthenticated API401, incorrect password401, cross-origin mutation403, arbitrary proxy path404, authenticated history200. User explicitly approved copying only the generated dashboard password to the private Git-excluded local handoff file (0600).
- Gateway live smoke **19/19** diagnostic operations executed successfully. Latest gateway safety code deployed root-owned under /opt; only aiops-demo is currently writable.
- Indexed **11 runbooks** with all-minilm local embeddings,384-dimensional vectors. Authored11-query retrieval benchmark **Recall@4=11/11** at threshold0.45; this small benchmark is not a broad retrieval-quality claim.
- Full real demo lifecycle passed: unsigned write denied; deterministic diagnosis persisted current stopped-container evidence; exact approval persisted; gateway dispatched start once; Docker and HTTP recovery checks passed; incident RESOLVED; history embedding persisted and returned by similarity search. Both backend and gateway rejected replay. A first intentionally restrictive demo CPU budget caused health timeouts and correctly prevented resolution; giving only demo0.5CPU/96MB allowed the successful rerun in8.86s. No production container changed.
- Ollama0.33.3 running non-root, CPU-limited3cores/7GB, private loopback11434, cloud features disabled. all-minilm installed; reasoning model downloads/benchmarks underway.
- CodeDuel recovered around07:19UTC without this project changing or restarting it. Verified actual public `/api/explore/problems` HTTP200 plus all five CodeDuel containers healthy. Replaced nonexistent `/api/health` path in configured checks with the discovered route. Generic host symptoms have no blanket auto-resolution checks to avoid certifying recovery from SSH liveness alone.

## Resumed audit — 10 September 2026 IST (9 September 19:48 UTC)

The Mac workspace remains the canonical source. Inspection found an initialized `main` branch with **no commits and no remote**; the server directory is currently an archive deployment, not a Git checkout. No GitHub deployment provenance exists yet. MODEL_EVALUATION.md, CI and scripts/deploy.sh are missing. These are outstanding work, not completed deliverables.

All six core Docker services and the isolated demo remain healthy after twelve hours; gateway systemd is active. CodeDuel homepage, public problems API and local proxy health return HTTP200; all five existing CodeDuel containers are healthy. No production workload was changed during this audit. Both qwen2.5:3b (1.9GB) and qwen3:4b (2.5GB) are fully downloaded alongside all-minilm. There is **no completed actual-model benchmark report**. Previous eight-case scores use scripted decisions and cannot establish LLM accuracy; the approval/RAG demonstration likewise uses an authored diagnosis.

Code inspection confirms a real Ollama provider in production, a bounded agent loop, persisted evidence/hypotheses/actions, explicit approval and replay enforcement, and local RAG. Remaining product work includes actual-model evaluation and live investigation, stronger structured-response/retry metrics and confidence guidance, typed generic service profiles, server overview/health experience, expanded runbooks, authentication lifecycle checks, GitHub CI and deployment from the exact published commit. Previous test/retrieval/security claims are being rerun before final acceptance. Development continues in the existing architecture; server changes will follow Mac → GitHub → server.

## 10 September 2026 — GitHub checkpoint and safe deployment

- Published initial commit `a7c6adb` to private GitHub `Parthmudgal15105/HomeAiAgent:main`; all three GitHub Actions jobs passed (run34501665140).
- Added a repository-only, read-only deploy key on the server. Its private key remains on Ubuntu. GitHub host keys were obtained over verified HTTPS and are scoped to this repository's SSH command; existing SSH configuration was untouched.
- Backed up PostgreSQL/environment/config/runbooks and prior source under server `backups/`, then initialized the existing deployment directory as Git without deleting `.env`, model files, volumes or replay ledger. Server source now tracks GitHub `main`.
- First deployment from GitHub is executing through scripts/deploy.sh. Exact running-image provenance is being added through OCI revision labels and deployment checks so a Git checkout alone cannot be mistaken for a deployed build.
- Follow-up fixes: overview marks unhealthy/inactive states correctly, frontend smoke verifies logout and stores runtime reports in Git-excluded storage, retrieval benchmark covers all14 runbooks. Targeted tests10/10, secret scan clean; previous full150 Python and9 frontend tests and production build passed.
- Remaining: actual-model benchmark outcome, final live investigation/approval/RAG acceptance, resource/private-port/persistence verification and final commit parity. Do not mark the project complete from this checkpoint alone.

## CPU inference finding — 10 September16:28UTC

A real Qwen3 Redis investigation exposed expensive prompt reprocessing: one measured step spent109s evaluating1,455 prompt tokens and19.6s producing60 output tokens while deployment compilation also competed for CPU. The agent context previously placed changing observations before the static tool registry/topology, preventing reuse of that stable prefix. Reordered context to put unchanged tools/topology/history first and changing observations last. This preserves decision inputs and security validation; it is a performance change requiring a fresh measured run. Baseline investigation remains separately labeled. Avoid building images during final performance measurements.

## Deployment permission correction — 10 September16:32UTC

Live runbook ingestion caught a deployment issue: the initial Git conversion used umask077, creating newly tracked runbooks mode0600; the non-root backend could not read its mounted files. Added a deployment step granting read/traverse permissions only to tracked non-secret config/runbook/script mounts, and set the gateway installer's source/package umask022 while keeping its explicit secret files0600 and backups0700. Server `.env` remains untouched. The failure is an acceptance finding; retrieval success is not claimed until the corrected deployment is rechecked. Synthetic evaluations now write a progress checkpoint after every completed case so interrupted sessions retain measurable progress.

## 11 September 2026 — resumed acceptance audit

- Files: `IMPLEMENTATION.md`, `evals/remediation.py`, `evals/test_remediation.py`, `.github/workflows/ci.yml`, `scripts/deployment_health.py`, `reports/model-comparison/`.
- Decision: preserve and report the failed actual Qwen 2.5 evaluation; compare Qwen 3 using identical fixtures and limits. Added isolated actual-model recovery acceptance tooling and CI coverage. Public production health checks use fixed-argument curl to match the working baseline probe.
- Tests: full Python suite152 passed; one dependency deprecation warning.
- Deployment: server remains healthy on7b8cbfb; new changes not deployed yet.
- Limitation: actual-model root-cause acceptance remains unfulfilled. Next action: finish Qwen3 measurements and live acceptance.
