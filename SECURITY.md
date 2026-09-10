# Security boundaries and operating policy

The local model chooses from named diagnostic tools. Python validation, configured target allowlists, a separate gateway, persisted approvals, and deterministic recovery checks enforce the boundary. Prompts guide reasoning but do not authorize operating-system access.

## Access and network exposure

The configured web listener is the Tailscale address `100.98.193.60:3080`. FastAPI (`18000`), the gateway (`18081`), Ollama (`11434`), PostgreSQL (`15432`), and Qdrant (`16333`) bind to host loopback. The Next.js and FastAPI containers use host networking with explicit bind addresses. Loopback access is private to the host's networking context, not isolation from other compromised host processes.

The web application requires a generated operator password and issues a signed, HttpOnly, SameSite=Strict session cookie with an eight-hour expiry. Its server-side proxy supplies the separate backend bearer token; the backend denies API access when its token is missing. Authentication is a single-operator model with no role separation or per-user attribution. Keep the application inside the authorized tailnet. The HTTP deployment relies on Tailscale's encrypted peer transport; public use requires reviewed HTTPS/access configuration and secure-cookie settings. Do not add a public hostname merely to make internal components reachable.

Gateway tool endpoints require a separate strong bearer token. Its minimal liveness endpoint contains no diagnostic output. Existing SSH, Tailscale configuration, and the token-bearing remote-managed Cloudflare service are preserved. The application does not expose a Docker socket, terminal, arbitrary proxy, or unrestricted command endpoint.

## Gateway privileges and tool scope

The gateway runs as the dedicated `aiops-gateway` account from root-owned code/configuration under `/opt/aiops-gateway`. Its systemd unit applies filesystem, privilege, process, CPU, memory and connection-concurrency restrictions. A private state directory holds the approval replay ledger.

**Docker group membership provides effectively host-root power.** The gateway can communicate with the host daemon and therefore belongs to the trusted computing base. Non-root execution and systemd hardening do not remove that Docker authority. The backend has no Docker group/socket access. Keep gateway source, executable environment, and policy unwritable by the service account; compromise of those files would undermine all diagnostic restrictions.

`config/gateway.json` supplies exact container names, systemd services, hostnames, HTTP URLs/aliases, TCP host/port pairs, and filesystem paths. The current read-only container scope covers all 22 discovered preexisting containers, including the five CodeDuel containers, plus the separate `aiops-demo` container. Only `aiops-demo` is writable. Arbitrary names and extra argument fields fail validation. Commands use a fixed executable allowlist, argument arrays, a sanitized environment, bounded output, and hard timeouts. There is no `shell=True` command executor or generic shell tool.

HTTP probes use exact configured URLs or fixed container aliases. They reject redirects, validate resolved addresses, and pin the checked address for the connection while retaining HTTPS certificate/SNI checks. Public URL targets reject private/link-local/reserved destinations; configured localhost targets stay loopback. Container aliases use only their configured container, network, port, and path. TCP checks require a configured pair. These controls prevent model-supplied metadata URLs and arbitrary internal network probing.

## Model output, evidence, and sensitive data

Pydantic validates structured model decisions. Invalid output receives at most one constrained JSON repair retry; it is never interpreted as code. The backend independently checks tool identity, risk, arguments, duplicate calls, current observation ownership, and execution success. Runtime, step, model, tool, and context budgets limit runaway investigation. Hypothesis references must belong to the incident, with support/contradiction links for the corresponding states.

Tool results, logs, incident descriptions, runbooks, and retrieved history are untrusted data. They can contain prompt injection. Even if the model follows malicious text, it cannot bypass target validation or directly execute writes. Citation validation does not prove semantic truth: the model can still draw an incorrect causal conclusion from valid observations. Confidence values are capped estimates and do not imply calibrated accuracy.

Container inspection projects selected state/network fields and omits environment, commands, labels, mounts, and health-log content. Process diagnostics omit arguments and environment. Log/tool/audit paths apply bounded credential redaction. Redaction is best effort and cannot guarantee removal of every unknown secret format. Treat incident storage and exported evaluation/diagnostic reports as sensitive. Never print or commit production `.env` files, database URIs with credentials, SSH passwords, Cloudflare tokens, or signing keys.

Reasoning, embeddings, incident history, runbook vectors, and diagnostic logs are processed and stored locally. Configured DNS/HTTP diagnostics still contact their external targets, and initial model/image/package downloads require network access. The application requires no cloud LLM or embedding API to investigate incidents.

## Approval and write policy

The live backend and gateway enable approval-controlled writes only for `aiops-demo`: `writes_enabled:true`, `write_containers:["aiops-demo"]`, and `write_services:[]`. All 22 preexisting containers remain read-only. The reusable `.env.example` and gateway example default writes off; these installation defaults differ intentionally from the live demo policy. Production writes remain disabled while genuine local-model diagnosis validation is incomplete; the gate requires at least three correctly diagnosed scenarios using the actual model, followed by explicit review of target scope and verification checks. Benchmark results belong in EVALUATION.md and MODEL_EVALUATION.md and are not implied by the sandbox approval test.

Available write implementations are limited to `start_container`, `restart_container`, and `restart_service`; the live tool registry exposes only the two container operations scoped to `aiops-demo`. High-risk and destructive operations are absent. No general sudo authorization is granted. A systemd write, if ever scoped in, still requires separately reviewed host authorization for that exact service.

When enabled, the backend stores an exact proposed tool, arguments, reason, expiry, and incident association. An authenticated operator must approve that action. The backend atomically claims it before dispatch, records dispatch durably, and signs the action ID, exact tool/arguments, and short expiry with HMAC-SHA256. The gateway validates that signature and transactionally consumes the action ID in SQLite before executing. A reused approval is rejected across gateway restarts. Failed or uncertain execution does not trigger an automatic retry.

The model never receives the approval signing secret. A compromised backend holding it could nevertheless sign actions, so backend authentication, code, and approval persistence are also trusted security components. Protect the API token, gateway token, signing secret, database credentials, operator password, and session secret as separate generated values in permission-restricted deployment files. Do not expose them as public frontend environment variables.

Successful execution does not mark an incident resolved. The verifier runs administrator-defined, read-only service/dependency checks and records each result as an observation. All configured checks must pass. Missing target checks or failing dependencies keep verification blocked/open. Remaining stale proposals expire after verified recovery. Startup does not replay interrupted writes.

## Operational constraints

Never use this application to reset Docker, alter SSH/Tailscale networking, replace the Cloudflare service, delete production data/volumes, flush Redis, or make remote interface changes. Existing CodeDuel baseline failures must be distinguished from changes introduced by this deployment. Public homepage health is insufficient to assert API/worker recovery.

Use synthetic fixtures for disk, daemon, and Wi-Fi failure tests. Do not induce real outages to measure accuracy. Keep deployment/schema backups and inspect important configuration before changes. Review host listeners, service-account ownership, policy files, and component health after deployment changes. Log rotation and persistent volumes support continuity, but they are not a backup or tested disaster-recovery procedure. `scripts/backup.sh` does not copy the gateway replay ledger or Qdrant data; the additional backup steps and restore limits are described in DEPLOYMENT.md. Restoring an older database must never reinstate approval IDs already consumed by the gateway.

Current diagnostic gaps include direct Atlas/SRV checks, rootless judge-daemon inspection, live rfkill status, queue counts/test submissions, and peer-side Tailscale verification. Runbooks identify these gaps. Do not expand gateway scope or privileges solely to make a diagnostic return a result; first inspect the real target, choose the smallest useful read-only capability, and test its constraints.
