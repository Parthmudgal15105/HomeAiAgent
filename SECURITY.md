# Security boundaries and operating policy

The configured reasoning model chooses from named capabilities. Python validation, configured target allowlists, a separate gateway, persisted action authorization and deterministic recovery checks enforce the boundary. Prompts guide reasoning but do not authorize operating-system access. Autonomous actions require additional current-evidence and retry-budget policy.

## Access and network exposure

The configured web listener is the Tailscale address `100.98.193.60:3080`. FastAPI (`18000`), the gateway (`18081`), Ollama (`11434`), PostgreSQL (`15432`), and Qdrant (`16333`) bind to host loopback. The Next.js and FastAPI containers use host networking with explicit bind addresses. Loopback access is private to the host's networking context, not isolation from other compromised host processes.

The web application requires a generated operator password and issues a signed, HttpOnly, SameSite=Strict session cookie with an eight-hour expiry. Its server-side proxy supplies the separate backend bearer token; the backend denies API access when its token is missing. Authentication is a single-operator model with no role separation or per-user attribution. Keep the application inside the authorized tailnet. The HTTP deployment relies on Tailscale's encrypted peer transport; public use requires reviewed HTTPS/access configuration and secure-cookie settings. Do not add a public hostname merely to make internal components reachable.

Gateway tool endpoints require a separate strong bearer token. Its minimal liveness endpoint contains no diagnostic output. Existing SSH, Tailscale configuration, and the token-bearing remote-managed Cloudflare service are preserved. The application does not expose a Docker socket, terminal, arbitrary proxy, or unrestricted command endpoint.

## Gateway privileges and tool scope

The gateway runs as the dedicated `aiops-gateway` account from root-owned code/configuration under `/opt/aiops-gateway`. Its systemd unit applies filesystem, privilege, process, CPU, memory and connection-concurrency restrictions. A private state directory holds the approval replay ledger.

**Docker group membership provides effectively host-root power.** The gateway can communicate with the host daemon and therefore belongs to the trusted computing base. Non-root execution and systemd hardening do not remove that Docker authority. The backend has no Docker group/socket access. Keep gateway source, executable environment, and policy unwritable by the service account; compromise of those files would undermine all diagnostic restrictions.

`config/gateway.json` supplies exact container names, systemd services, hostnames, HTTP URLs/aliases, TCP host/port pairs and filesystem paths. Manual write scope is five CodeDuel containers plus aiops-demo; host services and autonomous writes have no grants. Arbitrary names and extra argument fields fail validation. Commands use a fixed executable allowlist, argument arrays, sanitized environment, bounded output and hard timeouts. There is no generic shell tool.

HTTP probes use exact configured URLs or fixed container aliases. They reject redirects, validate resolved addresses, and pin the checked address for the connection while retaining HTTPS certificate/SNI checks. Public URL targets reject private/link-local/reserved destinations; configured localhost targets stay loopback. Container aliases use only their configured container, network, port, and path. TCP checks require a configured pair. These controls prevent model-supplied metadata URLs and arbitrary internal network probing.

## Model output, evidence, and sensitive data

Pydantic validates structured model decisions. Invalid output receives at most one constrained JSON repair retry; it is never interpreted as code. The backend independently checks tool identity, risk, arguments, duplicate calls, current observation ownership, and execution success. Runtime, step, model, tool, and context budgets limit runaway investigation. Hypothesis references must belong to the incident, with support/contradiction links for the corresponding states.

Tool results, logs, incident descriptions, runbooks, and retrieved history are untrusted data. They can contain prompt injection. Even if the model follows malicious text, it cannot bypass target validation or directly call the gateway write endpoint. It may still request a policy-authorized write on flawed reasoning; topology and state checks reduce, but do not eliminate, this risk. Citation validation does not prove semantic truth. Confidence values are capped estimates and do not imply calibrated accuracy.

Container inspection projects selected state/network fields and omits environment, commands, labels, mounts, and health-log content. Process diagnostics omit arguments and environment. Log/tool/audit paths apply bounded credential redaction. Redaction is best effort and cannot guarantee removal of every unknown secret format. Treat incident storage and exported evaluation/diagnostic reports as sensitive. Never print or commit production `.env` files, database URIs with credentials, SSH passwords, Cloudflare tokens, or signing keys.

Ollama is the default and keeps reasoning, embeddings, incident history, runbook vectors, and diagnostic logs local. Configured DNS/HTTP diagnostics still contact their external targets, and initial model/image/package downloads require network access. The application requires no cloud LLM or embedding API in this default mode.

Selecting `LLM_PROVIDER=gemini` changes that privacy boundary. The backend sends the bounded, best-effort-redacted reasoning context to Google's Gemini API over HTTPS. This context can include the incident description, topology, allowed tool schemas, current diagnostic results, hypotheses, and retrieved runbook/history excerpts. The request sets API-side interaction storage to false, but processing remains subject to the Google account, project, service terms, logging and retention policies; do not treat that flag as a no-retention guarantee. Local Pydantic, evidence-ownership, target-allowlist, approval and replay checks remain authoritative. The API key is accepted only through `GEMINI_API_KEY`, represented as a Pydantic secret, sent in the `x-goog-api-key` header, and never placed in a URL, report or repository. Restrict and rotate it in Google Cloud/AI Studio, keep `.env` mode0600, and use Gemini only when sending this diagnostic context is acceptable.

## Autonomous and operator-approved write policy

The deployed policy allows approval-controlled CodeDuel container start/restart and demo start/stop/restart. Installation defaults remain `ENABLE_WRITE_ACTIONS=false` and `ENABLE_AUTONOMOUS_ACTIONS=false`; the live operator-enabled manual-write setting is true while autonomy remains false. Gateway autonomous grants are empty. Real-model acceptance has not passed.

Source includes container and service action implementations, but exposed targets depend on exact gateway grants. The dormant autonomous policy checks topology, current state evidence, logs, dependencies, target verification and bounded attempts. No autonomous grant is enabled. Cloudflare and other host service writes are disabled; the installer removes only the byte-identical earlier project polkit grant. No general sudo authorization is granted.

Gateway hard guards reject Docker, SSH and Tailscale unit writes and Cloudflare stop. Current policy disables every host service write, including Cloudflare start/restart. Never add control-plane targets to autonomous grants.

For an autonomous action, the backend persists the incident, exact tool/target, reason, evidence observation IDs, authorization mode, dispatch time, result and verification. The action ID, exact tool/arguments and short expiry are signed with HMAC-SHA256; the gateway consumes the ID transactionally in SQLite before executing. A reused authorization is rejected across gateway restarts. Failed or uncertain execution does not trigger an automatic retry. The separate direct-operation path still requires authenticated approval and the same signed dispatch mechanism.

The model never receives the approval signing secret. A compromised backend holding it could nevertheless sign actions, so backend authentication, code, and approval persistence are also trusted security components. Protect the API token, gateway token, signing secret, database credentials, operator password, and session secret as separate generated values in permission-restricted deployment files. Do not expose them as public frontend environment variables.

Successful execution does not mark an incident resolved. For start/restart, the verifier runs administrator-defined, read-only service/dependency checks and records each result as an observation. All configured checks must pass. A deliberate stop verifies only the exact target is inactive and leaves the incident open; it never claims application recovery. Missing target checks or failing dependencies keep verification blocked/open. Remaining stale proposals expire after verified recovery. Startup does not replay interrupted writes.

## Operational constraints

Never use this application to reset Docker, alter SSH/Tailscale networking, replace the Cloudflare service, delete production data/volumes, flush Redis, or make remote interface changes. Existing CodeDuel baseline failures must be distinguished from changes introduced by this deployment. Public homepage health is insufficient to assert API/worker recovery.

Use synthetic fixtures for disk, daemon, and Wi-Fi failure tests. Do not induce real outages to measure accuracy. Keep deployment/schema backups and inspect important configuration before changes. Review host listeners, service-account ownership, policy files, and component health after deployment changes. Log rotation and persistent volumes support continuity, but they are not a backup or tested disaster-recovery procedure. `scripts/backup.sh` does not copy the gateway replay ledger or Qdrant data; the additional backup steps and restore limits are described in DEPLOYMENT.md. Restoring an older database must never reinstate approval IDs already consumed by the gateway.

Current diagnostic gaps include direct Atlas/SRV checks, rootless judge-daemon inspection, live rfkill status, queue counts/test submissions, and peer-side Tailscale verification. Runbooks identify these gaps. Do not expand gateway scope or privileges solely to make a diagnostic return a result; first inspect the real target, choose the smallest useful read-only capability, and test its constraints.

## Exact production action grants (18 September 2026 source)

The deployed policy lists each permitted tool per target in `allowed_actions`; `autonomous_actions` is empty. CodeDuel containers have manual start/restart grants only; the demo also permits manual stop. Backend autonomy defaults to false and is false on the server. The optional Cloudflare Access design in DEPLOYMENT.md remains an unimplemented optional access path; Tailscale authentication was verified from a separate Mac.