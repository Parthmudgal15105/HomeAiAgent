# Implementation status and resume guide

## Autonomous expansion — 16 September 2026 (local source, not deployed)

- Added evidence- and topology-gated autonomous start/restart using the existing one-use signed gateway dispatch and persistent `Action`/`AuditEvent` records. Stop remains operator-approved only. Each action receives exact-target verification; the final diagnosis runs full configured application/dependency checks. One target is attempted at most once per incident, with a six-action default budget (five CodeDuel containers plus tunnel if needed).
- Checked-in policy now names the five CodeDuel containers from the last inspected production Compose inventory and `cloudflared`. An exact-unit polkit rule is included for cloudflared start/restart; Docker, SSH and Tailscale unit writes remain blocked. The new frontend exposes a Turn on CodeDuel prompt and recent autonomous operations.
- Local checks: 174 Python tests passed (backend, gateway, evaluation and script tests); after the final bounded verification-poll edit, the 12 focused autonomy/approval tests also passed. Ten frontend tests and the Next.js production build passed, `git diff --check` passed, and the secret scanner found zero findings across 141 tracked/new files. Autonomous tests cover scoped action, verification and retry rejection. These are local results, not host smoke checks.
- Deployment **not completed**. A read-only SSH attempt reached `100.98.193.60` but failed `Permission denied (publickey,password)` with available non-interactive credentials. A read-only HTTP check of `http://100.98.193.60:3080` returned 200, confirming only that the older dashboard endpoint responds. Fresh container names, actual server environment flags, cloudflared polkit behavior, authenticated production smoke and source/image parity are unverified. No CodeDuel production container was altered.
- The previous deployed Gemini 429 quota and measured qwen2.5:3b 0/8 root-cause results remain unresolved model-quality limitations; do not treat this source implementation as an accepted autonomous production system.

The dated material below is historical and describes the last verified deployment, not the new local source.

## 28 September 2026 local reliability update

- **Implemented and locally tested:** named model/tool/infrastructure failure categories; persisted per-step/model/tool/RAG timing; explicit model-call budget; one-decision model deadline; deferred RAG retrieval; capability-gap escalation; compact Ollama prompt context with an 8,192-token preflight guard; exact-target recovery preconditions; and bounded Atlas SRV/DNS/TCP/TLS reachability diagnostics without credentials.
- **Implemented and contract-tested:** production-policy-derived synthetic gateway schemas and a 15-scenario incident/recovery scaffold. The scaffold validates tools, target enums, topology health checks, recovery targets, Atlas support, and the absence of autonomous grants against `config/gateway.json`; it is not a live incident run or a model-accuracy result.
- **Not live verified:** this source was not deployed; the dashboard was observed only at its sign-in boundary. No credentials were entered, no live model request was issued, and no production action or external Atlas probe was performed.
- See `FAILURE_MODES.md` for the runtime taxonomy and escalation semantics. Historical claims below retain their original dates and should not be treated as evidence for this source revision.

Last verified: 13 September 2026, 07:54 UTC. **Overall status: incomplete; the Gemini-enabled deployment is healthy and the integration passes locally, but deployed generations are temporarily blocked by the supplied key's free-tier request quota.**

## Source and deployment identity

- Canonical Mac source: `/Users/parthmudgal/Code/HomeAiAgent`.
- GitHub: private `Parthmudgal15105/HomeAiAgent`, branch `main`; authentication and push work.
- Ubuntu target: `hp@100.98.193.60`, `/home/hp/ai-home-lab-operator`, a Git checkout using a repository-only read-only deploy key.
- The Gemini integration was first deployed as `7e529c9802235154c1ac8d223a9b89d0ec671d3d`; server source and both image revision labels are verified against published `main` after each deployment.
- Dashboard: `http://100.98.193.60:3080` through Tailscale. Credentials are excluded from Git; never copy the server `.env` into source.

## Verified current state

- The guarded deployment completed with a mode-0700 application backup and an additional recoverable pre-Gemini environment backup. All six project containers and the isolated demo are healthy, the gateway is active, backend health is200, and the Tailscale dashboard is200.
- Fresh post-merge verification: **161 Python tests passed**. Nine frontend tests, typecheck and the production build passed before the source merge; no frontend source changed in this integration.
- Previous deployed acceptance: gateway **19/19** live diagnostics; authentication/logout and private component checks passed; backend/frontend image provenance matched Git HEAD. GitHub CI passed for `7b8cbfb`.
- Real local Ollama provider, typed constrained decisions, evidence persistence, evolving hypotheses, approval/replay protection, recovery verification, generic service topology, incident history and bounded server overview are implemented. Fourteen runbooks exist; final ingestion/retrieval recheck is pending.
- **Completed actual qwen2.5:3b eight-case benchmark: 0/8 root-cause accuracy, Top-3 1/8, average 4.125 executed tools and 265.24 seconds per case.** All eight stopped after repeated diagnostic requests; 24 duplicate attempts were rejected. No invalid JSON or unsafe action attempts were recorded. This model is not accepted for production reasoning on these results.
- The original qwen3:4b comparison was stopped after its first case also failed on repeated requests; its partial report is retained. A revised provider now excludes completed finite diagnostic targets from the output grammar and requests a concise evidence assessment before choosing a decision. Its new eight-case Qwen3 benchmark is running; Qwen2.5 must be rerun with this same provider for fair comparison. Earlier standalone Redis success is a development result, not full-suite acceptance. See `reports/model-comparison/` for preserved measurements.
- A real-model mocked Redis approval/recovery/PostgreSQL/RAG acceptance runner now exists in `evals/remediation.py`. Its two security tests pass; its actual-model lifecycle has not yet been run.
- Optional Gemini reasoning uses the Interactions API, structured output, local Pydantic/policy validation, one repair retry, disabled API-side interaction storage, HTTPS/header authentication, and token/latency metrics. Ollama remains the source default and the local embedding provider. Development used a temporary process environment; the deployed key exists only in the private server environment.
- Live Gemini validation: direct structured smoke passed; the synthetic Redis incident passed1/1 in22.4611s across four requests with correct grounded diagnosis, three relevant diagnostics, and zero invalid/retried/failed/rejected/unsafe decisions. This is not a full accuracy benchmark.
- Secret scanning now detects Google key formats; the post-merge scan covered134 source files with zero findings. `.env`, local access files, runtime data, backups and logs remain ignored.
- `scripts/deploy.sh` performs clean-Git checks, fast-forward pull, backup, dedicated gateway update, Compose build/start, component checks and before/after CodeDuel comparison.
- The server uses Gemini as its reasoning provider and retains Ollama for embeddings. Authenticated model health succeeds. A deployed synthetic generation was attempted only after deployment, but Google returned HTTP429 for the key's20-request free-tier quota; no model decision or production diagnostic executed. CodeDuel remained at its pre-deployment baseline: homepage200, problems API500, API container unhealthy and its other four containers healthy.

## Remaining acceptance work (resume here)

1. Wait for or increase the Gemini quota, then rerun the deployed synthetic Redis check. Keep a production fallback decision explicit rather than silently changing providers.
2. Complete identical eight-case benchmarks for the intended production reasoning provider; Gemini currently covers only Redis1/1 locally, while fair reruns for local candidates remain incomplete.
3. Run a real selected-model read-only server investigation and mocked Redis approval/recovery/history retrieval lifecycle. Do not cause a production outage.
4. Re-ingest fourteen runbooks; recheck retrieval, current live diagnostics, dashboard, private ports, resource usage, persistence and CodeDuel health.
5. Preserve exact Git/source/image parity for subsequent changes and record all measured results without treating provider health as generation success.

## Future session procedure

Read this current-state section first, then inspect `git status`, `git log -5`, `git remote -v`, server `git rev-parse HEAD`, `docker compose ps`, gateway status and CodeDuel health. Reuse existing data and architecture. Work only on Mac source; follow edit → tests/secret scan → commit → GitHub push → SSH → `bash scripts/deploy.sh` → verify matching commit. Never store credentials, generated logs or model files in Git. Never reboot or modify CodeDuel/SSH/Tailscale/Cloudflare configuration for operator development.

Every subsequent entry must record date, phase, changed files, decision, tests, deployment commit/result, remaining limitations and next action. Historical entries below describe their own time, not current completion.

---

# Implementation journal

This file records actual progress and validation. Items are not complete until tested.

## Gemini deployment — 13 September 2026, 07:54 UTC

- Rebased the Gemini integration over upstream model-reliability changes, preserving finite-target duplicate prevention and the evidence-reasoning prompt. Post-merge verification passed161 Python tests, `git diff --check`, and a134-file secret scan with zero findings.
- Published and deployed `7e529c9802235154c1ac8d223a9b89d0ec671d3d` through `scripts/deploy.sh`. The script created `backups/20260913T074811Z`, refreshed the gateway, built both images and reported gateway, database, Qdrant, Ollama, Gemini model authentication and frontend healthy. Checkout and backend/frontend labels matched the commit.
- Stored the supplied Gemini key only in the Git-excluded server `.env` with mode0600 and retained a pre-change environment backup. The backend loaded provider `gemini`, model `gemini-3.8-flash`, and a non-empty secret without printing it.
- Deployed synthetic generation attempts were rate-limited by Google's HTTP429 free-tier20-request quota after the earlier development calls. No decision or diagnostic executed in those attempts. The earlier local production-loop Redis result remains the completed generation test; deployed generation must be rerun after quota availability.
- CodeDuel was unchanged and retained its pre-deployment state: homepage200, problems API500, API container unhealthy, remaining four containers healthy.

## Gemini provider integration — 13 September 2026, 07:38 UTC

- Added configurable `LLM_PROVIDER=ollama|gemini`; Ollama remains the default and local embedding provider. Gemini targets stable `gemini-3.8-flash` through the Interactions API with low thinking, bounded output, request storage disabled and no SDK dependency.
- Added provider selection to the backend, authenticated Gemini health reporting, evaluation CLI support, latency/token metrics, safe API errors, Google key redaction/scanning, documentation and tests. The key is a Pydantic secret and is sent only in the `x-goog-api-key` header to the validated Google endpoint.
- Live development exposed Gemini rejecting a conditional nested hypothesis schema and repeated dynamic observation-ID enums. The final provider uses Gemini-compatible schema constraints while the controller remains authoritative for evidence ownership and exact tool targets. Invalid hypothesis metadata is audited and ignored independently; it cannot authorize or block a separately valid read-only diagnostic.
- Verification:156 Python tests,9 frontend tests, TypeScript, Next.js production build, diff check and128-file secret scan passed. Live direct structured smoke passed in6.7394s. Production-loop synthetic Redis diagnosis passed1/1 in22.4611s with zero invalid/retried/failed/rejected/unsafe decisions. Full eight-case quality evaluation remains pending.
- Deployment status at this checkpoint: server checkout and running images still match clean commit `7b8cbfb`; Gemini environment variables are absent. All project containers and the gateway are healthy. CodeDuel homepage is200 and its problems API is500 before deployment. No server change has yet been made.

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

## 11 September2026 — reliability and live inventory fixes

- Files: `backend/app/llm.py`, `backend/tests/test_model_reliability.py`, `diagnostic_gateway/tools.py`, `diagnostic_gateway/tests/test_gateway.py`, `backend/app/overview.py`, `backend/tests/test_topology_overview.py`, evaluation/deployment docs.
- Decision: preserve failed baselines, narrow completed diagnostic target choices without widening tool access or forcing a fixed diagnostic order, and require a short evidence assessment before decision selection. Raw current observations still determine model conclusions.
- Live browser finding: Docker's full JSON rows included bulky labels and exhausted the capture budget; only seven of23 configured containers were shown. Project only necessary fields before capture, and classify truncated inventories as incomplete rather than claiming containers are missing.
- Tests:154 Python tests passed before the inventory fix; inventory-specific gateway suite71 passed; full follow-up155 passed. Nine frontend tests, typecheck/build and published checkpoint CI passed. Browser sign-in, overview and historical incident reopening verified.
- Deployment: new fixes remain on Mac while the actual-model comparison runs. Server remains on7b8cbfb. Fresh gateway19/19, auth/logout and private-port checks passed. CodeDuel API500/unhealthy with MongoDB TLS errors existed before this deployment cycle; other four CodeDuel containers healthy, no modifications performed.
- Remaining: complete revised actual-model benchmarks, live model investigation, modeled mocked recovery/RAG, and exact final Git deployment.

## 18 September 2026 — exact policy and local verification

- Preserved the pre-existing uncommitted implementation while adding per-target `allowed_actions` and `autonomous_actions` at the gateway, with an exact gateway scope check. CodeDuel and cloudflared source grants contain start/restart only; the demo alone retains manual stop. Backend autonomous dispatch reads the gateway's autonomous-target metadata. Changed the installation default to `ENABLE_AUTONOMOUS_ACTIONS=false` because the recorded model acceptance gate remains unmet.
- Added gateway tests for exact action scope and invalid grants. Fixed compacted context so a critical log marker survives a tight budget.
- Local validation: ten frontend tests passed; Next.js 16.3.4 production build and TypeScript passed; secret scan found zero findings across 141 files; 82 focused Python tests passed with four host-dependent tests deselected. A full Python run produced 169 passes, two failures and three errors before the context fix; the context failure then passed in isolation. The remaining failures/errors were macOS sandbox restrictions on loopback socket binding and a psutil swap-memory call. These are environmental, not acceptance passes.
- Initial sandboxed Tailscale HTTP and SSH checks could not connect. A later read-only check with network access confirmed HTTP 200 and an unauthenticated session, while SSH authentication was rejected. No server deployment, live authenticated login, real service-state, production action, boot persistence or revision-parity claim can be made. No CodeDuel service was changed.
- Optional Cloudflare Access steps are documented; the second frontend instance and account-side route remain unimplemented. Real-model eight-case evaluation and deployed RAG/incident acceptance remain outstanding.

### Final local gate correction — 18 September 2026

The complete Python suite was rerun with local loopback and host-memory access permitted: **177 passed, 2 deprecation warnings**. The earlier sandbox-only socket/psutil failures were environmental. Ten frontend tests passed; the Next.js production build and TypeScript check passed. The scripted eight-case orchestration fixture passed 8/8 but did not call a reasoning model and is not a model-accuracy result. Secret scan: 141 files, zero findings. `git diff --check` passed.

Read-only Tailscale checks from this Mac returned HTTP 200 at port 3080 and `{"authenticated":false}` from `/api/session`; ports 18000, 18081, 15432, 16333 and 11434 did not accept connections over the Tailscale IP. This demonstrates endpoint response and unauthenticated session status, not authenticated remote use. SSH to `hp@100.98.193.60` reached the host but was rejected (`Permission denied (publickey,password)`), so server revision, installed gateway policy, live service states, action execution, boot persistence, RAG ingestion and image parity remain unverified. The source has not been committed, pushed or deployed.

## 18 September 2026 — authorized SSH restored, pre-deployment inventory

The operator supplied working interactive SSH credentials. A read-only session reached `hp@100.98.193.60`; the server checkout is clean on `main` at `db368bbbf5726d3d78bbb5ae43bb38ae0d669280`. Backend and frontend running image labels also report this revision. The six core Compose services and demo are running and healthy; `aiops-gateway`, Docker, Tailscale and cloudflared are active and enabled. The live CodeDuel names match the recorded policy: `codeduel-proxy-1`, `codeduel-frontend-1`, `codeduel-api-1`, `codeduel-worker-1`, `codeduel-redis-1`. Before deployment, CodeDuel API is unhealthy, the other four are healthy, the public homepage returns 200, and the public problems endpoint timed out after eight seconds. This is the deployment baseline; no CodeDuel action was taken. The installed gateway remains demo-only, while the source policy includes exact production grants. The server environment has `ENABLE_WRITE_ACTIONS=true`, `ENABLE_AUTONOMOUS_ACTIONS` unset and `LLM_PROVIDER=gemini`; the new source default keeps autonomy off.

Fresh local validation before deployment: 177 Python tests passed, 10 frontend tests passed, TypeScript and Next.js production build passed, secret scan reported zero findings across 142 files, diff check passed and the eight scripted controller fixtures passed. These do not establish Gemini root-cause accuracy.

## 18 September 2026 — deployed acceptance and startup-verification correction

Release `aad5bc5ffd949710e1afc16ccf18cd6ff9c0e8d5` was committed on the Mac, pushed to GitHub main and deployed by `scripts/deploy.sh`, with backup `backups/20260918T113541Z`. Mac, GitHub, server source and backend/frontend image revision labels matched. Gateway, PostgreSQL, Qdrant, Ollama, Gemini authentication and frontend health passed. CodeDuel retained homepage200, problems API500, API unhealthy and four other containers healthy.

Live frontend HTTP acceptance passed login, authenticated overview/history/topology and logout; unauthenticated overview returned401. Live overview returned15 signals and14 profiles; CodeDuel application health returned UNHEALTHY. The approved stateless `codeduel-frontend-1` restart executed once through frontend→backend→gateway, with persistent before-state, action and audit events. Its immediate container health was still starting, so verification correctly failed and the incident remained OPEN. The container became healthy shortly afterward. Unknown targets and a forbidden production stop returned409; replaying the approved action returned409 without another execution. Follow-up source adds bounded target-health polling and lets explicit Verify finish the same action without re-executing it; two regression tests cover those cases.

All14 runbooks were ingested; the first retrieval rerun scored13/14 at the unchanged threshold0.45/top4. The generic application runbook title/symptom wording was clarified; the query and threshold were not changed. Gemini's intended-setting benchmark produced two failed cases with no diagnostic calls and approximately240s latency each before the overall600s command limit stopped it. This is provider failure evidence, not a passed model evaluation. Autonomous recovery remains disabled and its gateway grants are cleared pending acceptance. Cloudflare/systemd writes are removed from the production policy and the installer retires only this project's exact earlier polkit grant.

## Final acceptance — 18 September 2026

Source release `47ac1c3d18a2cf8e32f517ea3236d2a57523e722` passed the canonical deployment health gate. The following documentation-only release preserves this implementation. The deployed commit is recorded privately by `scripts/deploy.sh` in `reports/private/deployed-commit.txt`; image labels must match it.

| Feature | Status | Evidence |
|---|---|---|
| Source validation | COMPLETED | 179 Python tests, 10 frontend tests, TypeScript and Next.js production build passed; secret scan zero findings. |
| GitHub push | COMPLETED | Source and acceptance corrections pushed to main. |
| Server deployment | COMPLETED | Canonical script completed; backup preserved; core components healthy. |
| Revision parity | COMPLETED | Source release matched server and backend/frontend image labels; final documentation release rechecked during deployment. |
| Tailscale remote access | COMPLETED | Mac reached 100.98.193.60:3080 and used authenticated dashboard endpoints. |
| Authentication | COMPLETED | Unauthenticated overview401; login, overview/history/topology200; logout returned unauthenticated session. |
| Private port isolation | COMPLETED | Mac could not connect to Tailscale ports18000,18081,15432,16333,11434. |
| Server overview | COMPLETED | Authenticated overview returned15 signals and14 profiles. |
| Live service status | COMPLETED | CodeDuel health correctly UNHEALTHY; five real container names matched policy. |
| Live read-only investigation | NOT COMPLETED | Incident22ac1b79-3396-4ae4-a3a2-8f006bf3abd8 ended FAILED with ReadTimeout after240.389s, zero observations/actions. Direct gateway smoke separately passed25 checks, skipped2 requiring targets. |
| RAG ingestion/retrieval | PARTIALLY COMPLETED | 14 chunks ingested; Recall@4=13/14 at0.45. Verified incident indexed, but tested history query missed. |
| Manual production action | COMPLETED | One approved codeduel-frontend-1 restart, action e1857980-ce82-4084-b484-2e4900501aa0. |
| Action verification | COMPLETED | Initial starting state failed safely; later explicit Verify returned PASSED and RESOLVED without another restart. |
| Audit persistence | COMPLETED | Incident c8a6d4f7-a1a8-473c-9412-7a6ae715cf7c and five audit events survived deployment. |
| Replay protection | COMPLETED | Reapproving the consumed action returned409; signed gateway ledger retained. |
| Policy enforcement | COMPLETED | Unknown target and production stop rejected409. Installed write_services=[] and autonomous_actions={}; earlier exact polkit grant absent. |
| Model evaluation | PARTIALLY COMPLETED | Full bounded availability run0/8: one timeout, seven429; intended-timeout suite stopped after two failed cases. Real reasoning acceptance unmet. |
| Autonomous production recovery | NOT COMPLETED | Deliberately disabled in backend and gateway; no production autonomous experiment. |
| Reboot/startup persistence | PARTIALLY COMPLETED | Gateway/Docker/Tailscale/cloudflared enabled and active; core containers unless-stopped; records survived redeployment. Host reboot not performed. |
| CodeDuel regression check | COMPLETED | Homepage200, proxy health200, API500/unhealthy and other four healthy matched baseline. Existing API fault remains. |
| Documentation | COMPLETED | README, implementation, deployment, security, architecture, model evaluation and interview reflect measured evidence and limitations. |

**Overall production acceptance is not granted:** provider inference and full model acceptance remain blocked, retrieval has measured misses, and autonomous recovery remains disabled. The verified manual dashboard and constrained operations are available. No reboot, destructive storage operation, environment replacement or Cloudflare route change was performed.
