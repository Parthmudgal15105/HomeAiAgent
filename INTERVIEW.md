# HomeServerAI interview guide

This describes the current repository source as of 16 September 2026, **not an accepted live autonomous deployment**. The earlier Tailscale deployment is reachable at `http://100.98.193.60:3080` according to the last verified record; the new autonomous changes could not be deployed because SSH authentication failed. Do not tell an interviewer that autonomous CodeDuel recovery has been observed in production. The accurate claim is that it is implemented and locally tested, with live acceptance pending.

## A. Thirty-second explanation

“HomeServerAI is a private home-server operations agent. It investigates incidents by choosing typed diagnostics—Docker state and logs, systemd, HTTP, DNS, network and resource checks—then can perform a narrowly allowlisted start or restart when current evidence and deterministic policy permit it. A separate host gateway executes the operation, PostgreSQL records the investigation and audit trail, Qdrant supplies relevant runbooks, and configured checks verify recovery. The model never receives a shell.”

## B. One-to-two-minute explanation

I built this because a home server can have many failure layers: a website may be down because of DNS, Cloudflare, Nginx, an API container, Redis, or external MongoDB. A fixed “restart everything” script can hide the real cause or disrupt healthy workloads. The Next.js dashboard creates an incident; the FastAPI controller gives an Ollama or optional Gemini model a constrained tool registry, current observations, topology and retrieved guidance. The model selects the next check, while Python validates the decision and a separate, allowlisted gateway performs the deterministic diagnostic. For a configured unhealthy target, an autonomous policy checks exact target state, application membership, retry budget and verification availability before a signed one-use action reaches the gateway. PostgreSQL stores evidence, hypotheses, actions and audits; Qdrant stores vectors for runbooks and verified incident history. The deployment is private over Tailscale. The new autonomous path is source-tested, not yet live-deployed.

## C. Architecture

```text
Browser on Tailscale → Next.js dashboard/session/proxy → FastAPI incident API
                                                     ├→ PostgreSQL (state/audit)
                                                     ├→ Agent/controller → Ollama or opt-in Gemini
                                                     │                  ↔ Ollama embeddings ↔ Qdrant
                                                     └→ schemas + autonomous policy → signed request
                                                                                 ↓
                                                separate host diagnostic gateway
                                                ├→ Docker container inspection/actions
                                                ├→ systemd status/actions
                                                └→ Linux, HTTP, DNS, TCP, ping, Tailscale checks
```

Next.js manages sign-in, incident timelines and overview; it does not execute host commands. FastAPI owns the agent loop, persistence, target policy and verification. Ollama provides local reasoning by default and embeddings for RAG; Gemini can replace only the reasoning provider. PostgreSQL is the transactional source of truth. Qdrant is the similarity-search index. The gateway runs as a dedicated host service with narrow HTTP tools and allowlists. Docker and systemd are controlled only through fixed gateway handlers. CodeDuel is an existing workload outside this project's Compose stack. Tailscale limits dashboard access to the private tailnet.

## D. Two end-to-end flows

“Is CodeDuel down?” creates an incident for the `codeduel` profile. The model can call `check_application_health`, inspect a failed component, compare current HTTP, container and dependency evidence, then return a cited diagnosis. A public homepage 200 alone is not proof that the API or worker works. Without a justified action, no write occurs.

“Turn on CodeDuel” uses the same incident/agent loop and topology. It inspects current components; if Redis is stopped, it can request `start_container` for `codeduel-redis-1`. Deterministic policy demands an exact stopped-state observation and a configured target check, then dispatches one signed action and verifies the target. The model reads that result before choosing another check/action. API and worker actions require observed healthy Redis. A final configured service/dependency check includes API readiness and public endpoints; failure remains unresolved. This is implemented source behavior, not a live-demonstrated result.

## E–F. Why an agent rather than a script?

The AI-driven part is the conditional choice of hypothesis and next tool from changing observations. A 502 can lead to a public HTTP check, local origin, proxy state, API logs, or DNS depending on what each result shows. A fixed script runs the same sequence regardless. The execution, schemas, target authorization, HMAC signing, retry cap and verification are deterministic; calling it an agent does **not** imply giving it general OS control. Deterministic automation still makes sense for known checks and simple alerts; the agent is useful where the diagnostic path branches across failure layers.

## G. Every registered capability

The first 27 rows are gateway read tools in `diagnostic_gateway/tools.py`; `check_application_health` is the backend composite in `backend/app/gateway.py`; the last six are gateway writes exposed only when configured. Inputs shown are the actual JSON argument names. “None” means `{}`. All variable targets are constrained by live registry schemas and gateway configuration; `process_list` has bounded optional parameters. Examples describe use, not permission to operate an arbitrary target.

| Tool | Input | Mode | What it does; example |
| --- | --- | --- | --- |
| `dns_lookup` | `hostname` | Read | Resolves configured A/AAAA name; check `codeduel.online`. |
| `ping_host` | `hostname`, optional `count` | Read | Bounded ICMP probe; test an allowlisted gateway. |
| `http_check` | `url` | Read | Exact configured HTTP/HTTPS or container alias, no redirects; test API readiness. |
| `docker_list` | None | Read | Lists configured containers including stopped ones; locate missing CodeDuel parts. |
| `docker_inspect` | `container` | Read | Projects safe state, health, ports and networks; inspect API. |
| `docker_logs` | `container`, optional `lines` | Read | Bounded redacted recent logs; identify Atlas error. |
| `service_status` | `service` | Read | Reads selected systemd unit state; check cloudflared. |
| `is_service_enabled` | `service` | Read | Checks boot enablement; distinguish active-now from enabled-at-boot. |
| `journal_logs` | `service`, optional `lines` | Read | Bounded unit journal; investigate tunnel failure. |
| `network_interfaces` | None | Read | Interface state and addresses; inspect host connectivity. |
| `route_table` | None | Read | Structured routes; diagnose path loss. |
| `default_gateway` | None | Read | Default route; test LAN egress configuration. |
| `cpu_usage` | None | Read | Short host CPU sample; investigate slowness. |
| `memory_usage` | None | Read | RAM and swap utilization; check pressure. |
| `disk_usage` | `path` | Read | Capacity for configured mount; check `/storage`. |
| `filesystem_mounts` | None | Read | Mount and capacity summary; spot missing storage. |
| `temperatures` | None | Read | Available sensor readings; inspect thermal pressure. |
| `system_uptime` | None | Read | Uptime, boot time and load averages; contextualize load. |
| `process_list` | optional `limit`, `sort_by` | Read | Bounded names/resource ranking; find top CPU/memory use. |
| `find_process` | `name` | Read | Exact executable-name search; find a process. |
| `inspect_process` | `pid` | Read | Safe status/resource fields; inspect a selected PID. |
| `listening_ports` | None | Read | TCP listeners; check whether an expected port is bound. |
| `port_check` | `host`, `port` | Read | Configured TCP pair; test port 8085. |
| `tailscale_status` | None | Read | Structured Tailscale state; check private access. |
| `cloudflared_status` | None | Read | Tunnel unit status; distinguish tunnel from origin. |
| `docker_stats` | None | Read | One resource sample for configured containers; identify hot container. |
| `recent_docker_events` | optional `minutes` | Read | Bounded lifecycle events; correlate recent crashes. |
| `check_application_health` | `application` | Read | Runs configured profile/dependency checks; summarize CodeDuel. |
| `restart_container` | `container` | Write | Restarts an allowed unhealthy container; e.g. API only with evidence. |
| `start_container` | `container` | Write | Starts an allowed stopped container; e.g. Redis. |
| `stop_container` | `container` | Write | Stops an allowed container; direct operator approval only. |
| `restart_service` | `service` | Write | Restarts an allowed unit; cloudflared only under narrow evidence/polkit. |
| `start_service` | `service` | Write | Starts an allowed inactive/failed unit; e.g. cloudflared. |
| `stop_service` | `service` | Write | Stops an allowed unit; operator approval only, cloudflared stop prohibited. |

There is no shell, generic command, Docker exec/run, host reboot, process kill, deletion, package, firewall or SSH configuration capability. The gateway rejects disabled/unknown tools and targets. The checked-in write targets are five recorded CodeDuel container names, `aiops-demo`, and `cloudflared`; actual live deployment freshness is unverified.

## H. Base diagnostics: what each layer proves

HTTP tests an application response, e.g. readiness 200, but one endpoint does not prove every user journey. TCP only proves a connection can be established to a host/port, not that the application is healthy. A process check proves a process exists; systemd adds unit state and restart metadata; Docker adds container state/health but not necessarily business functionality. DNS tests name resolution, ping tests ICMP reachability (which can be blocked), routes/interfaces reveal network configuration, and Tailscale status tests the local private-network daemon. Combining layers narrows the fault: public HTTP fails + local origin succeeds suggests the public/tunnel layer; API readiness fails + Redis healthy + Atlas error in logs suggests an external database path.

## I–K. RAG, embeddings and Qdrant

`POST /api/runbooks/ingest` invokes `LocalRAG.ingest_runbooks`: it reads `runbooks/*.md`, splits at `##` sections, combines into chunks of roughly 4,500 characters, redacts text, and embeds each with the configured Ollama embedding model. `LocalRAG` creates a cosine-distance Qdrant collection whose name includes a hash of the embedding model so incompatible vectors do not mix. A new incident query includes service/title/description; it is embedded, and Qdrant returns up to `RAG_TOP_K` matches (default four) above the configured score threshold (default 0.45). The agent supplies retrieved runbook and verified incident excerpts to the reasoning model; retrieval failure does not block diagnostics. Verified resolved incidents are indexed after final verification, not merely after a plausible diagnosis.

An embedding is a numerical representation of a text's meaning. Similar failure descriptions can have nearby vectors even when wording differs; cosine similarity finds nearby runbook/incident chunks. Qdrant stores those vectors, text and source metadata for retrieval. It is not the source of truth for current incidents. A historical Redis incident suggests useful checks, but only **current** observations can establish that Redis is failing now.

## L. PostgreSQL

The SQLAlchemy/Alembic tables are `incidents`, `observations`, `hypotheses`, `actions`, `audit_events`, and `evaluation_runs`. PostgreSQL provides transactional incident/action state, observation ownership, durable audit records and recovery across browser refresh or backend restart. Qdrant answers semantic-nearest-neighbor questions; PostgreSQL answers exact operational questions such as “which action was claimed?” and “what verification passed?” They are deliberately separate.

## M–N. Actual agent loop and tool calling

`Agent.investigate` claims an incident and bounds runtime; `_run` gets the live tool registry, retrieves optional RAG context, and repeatedly asks `LLMProvider.decide_next_action` for a Pydantic `Decision`. The model sees tool names, descriptions, JSON schemas, topology, current observations, hypotheses and remaining steps. Ollama receives a constrained JSON output schema; Gemini receives a compatible subset. Local Pydantic validation, backend `validate_tool`, JSON Schema validation and gateway scope validation are authoritative even if the model outputs a well-formed but wrong call. The controller records each observation and audit event, updates hypotheses, and either calls another read tool, requests a policy-checked autonomous action, saves a diagnosis, asks for input or stops.

The loop defaults to 18 decisions and 900 seconds, has model/tool/write timeouts, a 26,000-character context budget, a default single concurrent incident, a three-rejected-decision stop, and duplicate read-call rejection until a write makes re-probing meaningful. Output and logs are bounded/redacted. The gateway has fixed executable/argument arrays, short command timeouts and response limits. Autonomous writes add six actions per incident by default and one attempt per target; a timeout or uncertain result is never blindly replayed. The precise model context can be compacted while retaining observation IDs and tool constraints.

## O–P. Why no shell, and how autonomy remains bounded

A shell would turn an LLM mistake or prompt injection in logs into unrestricted host authority. The model only selects from named, typed capabilities. For an autonomous start/restart, `backend/app/autonomy.py` requires that the target belongs to the incident's configured application/dependencies, that a successful fresh same-incident exact-target state observation shows the appropriate unhealthy/stopped state, that the action and target budgets allow it, and that deterministic target verification is configured. API/worker actions require healthy Redis evidence. Container restarts require logs and reject known Atlas/Redis dependency-error signatures. A cloudflared restart needs a failing public endpoint and working local origin. The backend persists `AUTO_AUTHORIZED` and signs the exact action; the gateway consumes it once in SQLite before executing. Every action and verification appears in PostgreSQL audits. This is risk reduction, not proof that the model's diagnosis is always correct.

## Q. CodeDuel topology

The recorded production Compose names are `codeduel-redis-1`, `codeduel-api-1`, `codeduel-worker-1`, `codeduel-frontend-1`, and `codeduel-proxy-1` (Nginx). Redis backs BullMQ work consumed by the worker. The API uses external MongoDB Atlas and exposes internal `/health/ready`; that readiness also covers dependencies and worker heartbeat. The frontend can serve while the API is broken. Nginx proxies through local port 8085; remote-managed cloudflared publishes `codeduel.online`. Docker on the host runs the application containers; the worker also uses a separate rootless judge Docker socket, which this gateway does not inspect. `config/topology.json` defines these relationships and checks; `config/gateway.json` independently defines allowed diagnostic/write targets. No local MongoDB container exists.

## R–S. Two interview scenarios

For a `codeduel.online` 502, first compare public HTTP with local origin. If origin fails, inspect Nginx/proxy and API readiness, then Docker state and relevant logs. If the API is running but readiness fails, inspect Redis and dependency clues; an Atlas server-selection error is evidence of an external dependency path, not proof of the precise Atlas firewall/IP-allowlist cause. Restart only an exact target that policy and current state justify; otherwise report `INSUFFICIENT_CAPABILITY` and what requires outside intervention. Verify the target and then the configured public/API checks.

For “Turn on CodeDuel,” start from the topology, inspect existing states, and skip healthy components. If Redis is stopped, start and verify it before API/worker actions. Start other stopped required containers individually; the model chooses subsequent checks from each result. Verify API readiness, public homepage and API endpoint, and report partial health if a component or external Atlas remains unavailable. This sequence is an intended source workflow; production behavior has not been smoke-tested.

## T–U. Out-of-scope failures and safety

If the required fix is reboot, firewall modification, Atlas console change, Docker exec, filesystem write, package upgrade or another missing capability, the agent should stop and say `INSUFFICIENT_CAPABILITY`, citing what it observed and what human or external action is needed. It should not invent a tool, try arbitrary shell, or repeat a failed restart. Safety layers are exact allowlists, strict schemas, topology membership, evidence ownership/state checks, one-use HMAC, gateway replay ledger, budgets, timeouts, redaction, audit, deterministic verification and private Tailscale access. The Docker group remains powerful—effectively host-root if the gateway process is compromised—so gateway code/config ownership is part of the trusted boundary.

## V–AC. Technology and design choices

| Question | Interview answer |
| --- | --- |
| Local Ollama vs Gemini | Ollama is default for local reasoning; Gemini is an optional external reasoning provider. With Gemini, bounded redacted incident context, tool results, topology and retrieved guidance leave the server; embeddings and stored data remain local. |
| Why Ollama? | Privacy, no per-call model bill and local operation even when a cloud model is unavailable; tradeoffs are CPU latency and weaker observed small-model reasoning. It does not make external HTTP/DNS probes offline. |
| Why Qdrant? | It supports vector similarity search over runbooks and verified history with cosine distance and metadata. Plain SQL text lookup would miss semantically similar wording; it complements rather than replaces PostgreSQL. |
| Why PostgreSQL? | It durably and transactionally stores exact incident, observation, action and audit state. A vector index is not appropriate for one-use dispatch claims or relational evidence ownership. |
| Why FastAPI? | Python keeps Pydantic decisions, async HTTP/provider calls, SQLAlchemy persistence and controller policy together with typed API endpoints. |
| Why Next.js? | It supplies the authenticated browser dashboard, incident timeline, responsive overview and a server-side proxy that hides the backend bearer token from browser code. |
| Why a separate gateway? | The FastAPI container has no host Docker socket or root access. Only the narrow, host-resident gateway can reach Docker/systemd, and it revalidates target scope independently. |
| Docker group concern | Docker-group membership is essentially host-level power. Allowlisting constrains requests through the gateway API, not a fully compromised gateway process; source ownership, service hardening and private network access remain critical. |

## AD. AI-driven versus deterministic

| AI-driven | Deterministic |
| --- | --- |
| Hypothesis and next useful diagnostic | Tool names, JSON schemas and allowed argument targets |
| Interpretation of current evidence | HTTP/DNS/TCP/Docker/systemd probe execution |
| Order of checks and proposed targeted recovery | Evidence/topology/retry policy and HMAC one-use dispatch |
| Final explanation and uncertainty | Verification comparisons, persistence and audit records |

## AE–AF. Limitations and future work

The new autonomous path has not been deployed: SSH authentication failed, so live container names, service authorization and smoke checks are not fresh. Prior model quality is insufficient for a production confidence claim: qwen2.5:3b scored 0/8 root causes in an earlier eight-scenario benchmark; Gemini passed one synthetic scenario but the deployed key later hit HTTP 429 quota. The configured checks are not a real CodeDuel submission test, independent Atlas authentication, queue-depth inspection, rootless judge-daemon check or peer-side Tailscale test. The local polkit rule is unverified. Redaction is best effort. Future work is model/provider evaluation on more scenarios, safe demo-based live acceptance, better dependency/queue checks, notifications or scheduling, historical metrics, failure classification and carefully reviewed additions to the tool vocabulary. None should be described as present now.

## AG. Likely interviewer questions and short answers

1. **Why is this an agent?** The model chooses the next diagnostic or action from observations and can change course when results contradict a hypothesis. Code, not the model, executes each bounded tool.
2. **Why not a script?** A script is useful for a known fixed workflow, but 502s can arise at several layers. The agent's diagnostic path branches on evidence; verification remains deterministic.
3. **How does tool calling work?** The model sees a live registry of names, descriptions and JSON schemas. Its structured `Decision` is validated by Pydantic, backend policy and gateway scope before execution.
4. **What if the model invents a tool?** `validate_tool` rejects names outside both the backend allowlist and live registry. Repeated invalid decisions terminate the investigation.
5. **What if it chooses a dangerous action?** Dangerous capabilities are absent; autonomous stop is explicitly forbidden. A valid-looking write still needs exact target, state, topology, budget and verification checks.
6. **Can it run arbitrary commands?** No generic shell, SSH, Docker exec/run or subprocess API is exposed. The gateway's internal fixed command arrays are not model-provided commands.
7. **How does RAG work?** Current incident text is embedded and compared with Qdrant vectors for runbooks and verified incidents. Returned passages guide the next checks but do not count as current evidence.
8. **What is an embedding?** It is a numeric semantic representation of text. Nearby vectors can retrieve a relevant runbook despite different wording.
9. **Why Qdrant?** It indexes vectors and retrieves near neighbors by cosine similarity. PostgreSQL continues to own exact transactional state.
10. **Why PostgreSQL?** It stores incidents, evidence, hypotheses, actions and audits with durable relationships. That matters for traceability and one-use action claims.
11. **How do you prevent infinite loops?** There are step/time/tool limits, duplicate read rejection, three invalid-decision limit and autonomous action/target budgets. Failed writes are never automatically retried.
12. **How does verification work?** After each autonomous write, a configured exact-target check is run and recorded. Final service/dependency checks must all pass before `RESOLVED`.
13. **Is exit code zero enough?** No. A Docker or systemd command can succeed while readiness or public HTTP still fails; the separate checks make that visible.
14. **Why a separate gateway?** It isolates host-facing Docker/systemd access from the web/API containers. It also rechecks scopes and consumes signed actions once.
15. **How does CodeDuel recovery work?** The topology identifies five containers and their dependencies. The agent inspects, starts only stopped allowed parts, reads verification and continues toward API/public checks.
16. **What if Atlas is down?** Atlas is external and there is no local MongoDB container to restart. The agent reports the observed dependency failure and stops if no allowed fix exists.
17. **What if Ollama is unavailable?** Local reasoning requests fail and the incident is marked failed with an audit. Gemini is optional configuration, not an automatic fallback; RAG also needs local Ollama embeddings.
18. **What is in incident history?** Verified resolved incidents may be embedded with symptoms, root cause, key observations and verification. Their authoritative records remain in PostgreSQL.
19. **How are timeouts handled?** Provider, tool, write and overall investigation calls have bounded time. An uncertain write is not replayed; the outcome requires inspection.
20. **How are duplicate actions prevented?** The backend allows only one autonomous attempt per target per incident, while the gateway consumes each signed action ID once in SQLite. A repeated signature cannot execute twice.
21. **How does it know CodeDuel membership?** Administrator-owned `config/topology.json` defines components and dependencies. Separate `config/gateway.json` grants exact gateway target scope; the LLM cannot add a target.
22. **Can it restart Docker?** No. Docker, SSH and Tailscale unit writes are protected in the gateway because they can disrupt the host or remote access.
23. **Can it stop CodeDuel?** Stop handlers exist for an explicit operator-approved direct operation, but autonomous policy rejects stop. Cloudflared stop is blocked even at the gateway.
24. **What does HTTP 200 prove?** Only that a specific endpoint responded as configured. The homepage can be 200 while CodeDuel API or worker is unhealthy.
25. **What does a TCP check prove?** It proves a connection to a configured host/port could be made. It says little about HTTP correctness, authentication or application dependencies.
26. **How do you handle prompt injection in logs?** Logs and retrieved text are treated as data in the prompt. More importantly, their instructions cannot add tools or bypass deterministic validation, though they can still mislead diagnosis.
27. **What is the main security weakness?** The gateway's Docker group is powerful if the gateway is compromised. Model reasoning can also be wrong within allowed actions, so limiting targets and measuring reliability remain essential.
28. **What is the current deployment state?** The older approval-gated version was previously deployed over Tailscale. New autonomous changes are only local source-tested because available SSH credentials were rejected.
29. **What did the model evaluation show?** One older qwen2.5:3b eight-case benchmark scored 0/8 root causes; a Gemini synthetic Redis case passed 1/1, then deployed requests hit quota. These are not evidence of production-ready autonomy.
30. **Why not restart every container to turn on CodeDuel?** Healthy components do not need interruption, and a restart may hide an external dependency failure. The policy only authorizes a target with relevant current state evidence and then requires verification.
31. **What if verification fails?** The action remains auditable with failed verification and the incident stays unresolved. The agent can collect further evidence, but cannot loop on the same target.
32. **What would you improve next?** First obtain access and validate the exact live topology and safe demo action; then benchmark the intended reasoning model across varied incidents. Only after that would I expand capabilities or consider unattended scheduling.

## Suggested 15–20 minute discussion arc

Use 1 minute for the problem and 30-second pitch, 3 minutes for architecture and data stores, 3 minutes for the actual tool/agent loop, 3 minutes for a CodeDuel 502 and “turn on” walkthrough, 2 minutes for RAG and embeddings, 3 minutes for safety/autonomous verification, and 2 minutes for measured results and honest limitations. Keep the remaining time for interviewer questions. If asked for a demo, show the read-only dashboard and a safe fixture or already stopped demo target; do not induce a CodeDuel outage.

33. **Why is autonomous recovery disabled by default now?** The real-model eight-case acceptance threshold has not been met; deterministic safety checks do not prove diagnostic accuracy.
34. **What is the difference between allowed and autonomous actions?** `allowed_actions` permits a signed operator-approved action; `autonomous_actions` is its start/restart-only subset that can be considered after current evidence checks.
35. **Who is the final action authority?** The diagnostic gateway checks the exact tool and target before consuming a one-use signed action.
36. **Can a model invent a container name?** No. Its arguments must match the gateway schema and exact allowlist, and the backend checks incident topology.
37. **Why use a separate frontend for Cloudflare Access?** The Tailscale dashboard has one HTTP origin and cookie setting; an HTTPS Access hostname needs its own origin and Secure cookie without changing the private endpoint.
38. **Does Cloudflare Access replace the app password?** No. Access is the first authentication layer, and the application login remains the second.
39. **What does a successful container restart prove?** Only that the restart command completed. Target state and configured application/dependency checks still have to pass.
40. **How do you handle an uncertain write timeout?** The action is durably claimed and never replayed; the gateway/agent inspect current state and preserve the uncertainty in audit history.
41. **Why keep runbooks in RAG?** They provide local troubleshooting context and prior verified examples, while current observations and gateway policy determine what the agent may claim or do.
42. **What is still required before calling this production-ready?** Restore authorized server access, verify deployed source and policy, run real-model evaluation, prove live login and private ports, demonstrate an approved safe production action and verification, and check persistence after reboot.
