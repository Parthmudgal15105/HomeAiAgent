# Local AI Home-Lab Operator architecture

The application investigates infrastructure incidents with a configurable reasoning model that chooses constrained diagnostics and selected recovery actions. Ollama is the private local default; Gemini is an explicit cloud option. PostgreSQL persists observations, hypotheses, actions, and evidence-backed reports. A separate host gateway executes the authorized capability vocabulary. The model has no shell tool. This autonomous expansion is local source only until deployed and verified.

This document describes the implementation and configured deployment. Live validation and measured model results belong in `IMPLEMENTATION.md`, `DEPLOYMENT.md`, and `MODEL_EVALUATION.md`; a diagram or configured health check is not proof that a service is running.

## Components and data flow

```mermaid
flowchart TD
    Browser[Authorized Tailscale browser] --> Web[Next.js UI and authenticated API proxy]
    Web --> API[FastAPI incident controller]
    API --> PG[(PostgreSQL)]
    API --> Agent[Bounded Python agent]
    Agent --> LLM[Ollama or Gemini reasoning provider]
    Agent --> RAG[Local retrieval service]
    RAG --> Embed[Ollama embedding model]
    RAG --> Qdrant[(Qdrant)]
    Agent --> Gateway[Host diagnostic gateway]
    Gateway --> Linux[Linux processes resources and networking]
    Gateway --> Docker[Host Docker: allowlisted CodeDuel containers]
    Gateway --> Systemd[Allowlisted systemd diagnostics]
    Gateway --> Targets[Configured HTTP DNS and TCP targets]
    API --> Policy[Evidence + topology + retry policy]
    Policy --> Gateway
    API --> Approval[Optional direct-operation approval]
    Approval --> Gateway
    Gateway --> Verify[Configured read-only recovery checks]
    Verify --> PG
```

The frontend displays incident history, investigation progress, observations, hypotheses, topology, diagnoses, and approval controls. Its server-side proxy holds the backend bearer token. The browser receives an expiring signed session cookie after operator authentication. The UI polls incident state; it does not run host commands.

FastAPI uses a custom Python orchestrator. `LLMProvider` defines decision/report interfaces. `OllamaLLMProvider` supplies local inference; `GeminiLLMProvider` calls Google's Interactions API with request storage disabled. Both use schema-constrained JSON, full local Pydantic validation, one bounded repair retry and the same agent/tool policy. Environment configuration selects the provider, model and context/runtime budgets. A single concurrent investigation is the default to suit the consumer CPU/RAM budget and bounded external usage.

## Investigation lifecycle

An incident begins `OPEN`. Starting an investigation claims it and sets `INVESTIGATING`. The agent retrieves optional local context, asks the model for the next structured decision, validates the tool/arguments, calls the gateway, and records the result before asking for another decision. Each decision can update explicit hypotheses and supporting or contradicting observation links. Tool selection depends on the accumulated evidence; production orchestration does not follow the scripted evaluation plans.

The loop limits decisions, total runtime, model time, tool time, context size, and identical tool/argument repeats. Unknown tools and writes presented as read-only diagnostic calls are rejected. An `EXECUTE_ACTION` decision can initiate a configured start/restart only after exact-target current evidence, topology membership, a one-attempt-per-target rule, action budget and verification-plan validation. Rejected decisions generate bounded feedback; repeated policy failures stop the investigation. A transport/permission failure is stored as a failed diagnostic and does not establish target failure by itself.

A diagnosis must cite existing observations from the same incident and include at least one successful diagnostic. Confidence is capped according to the number of distinct successful tools, with a maximum of 95%. It remains a model estimate, not an empirically calibrated probability. Citation validation checks ownership and successful execution; it does not prove every causal interpretation is correct.

A diagnosed incident remains open until recovery is verified. Autonomous actions are durably recorded as `AUTO_AUTHORIZED`, signed for one-use gateway dispatch, and verified against the exact target before reasoning continues. A final administrator-configured service/dependency verification is required for `RESOLVED`. Direct operator proposals still create `WAITING_FOR_APPROVAL` actions. Unsupported verification remains blocked/open. Interrupted investigations are marked failed on backend startup, and uncertain writes are never replayed automatically.

## Persistence and local retrieval

PostgreSQL tables are `incidents`, `observations`, `hypotheses`, `actions`, `audit_events`, and `evaluation_runs`; Alembic manages schema changes. Incident state and results survive browser refreshes and application restarts. Important events record incident ID, model/tool timing, structured decisions, evidence, approvals, and verification results after redaction.

Runbooks in `runbooks/*.md` are split into bounded sections, embedded by a configurable local Ollama embedding model, and stored in Qdrant. Verified resolved incidents can be indexed with symptoms, root cause, important observations, and verification evidence. Retrieval uses a configured top-K and similarity threshold. The collection name includes an embedding-model identifier to separate incompatible spaces. Retrieval failures are recorded and the diagnostic loop can continue without RAG. Retrieved material supplies investigation guidance and never substitutes for current observations.

## Actual CodeDuel topology

`config/topology.json` is grounded in the inspected production Compose at `/opt/codeduel/docker-compose.prod.yml`. Existing remote-managed `cloudflared` sends public traffic to `127.0.0.1:8085`, the NGINX `codeduel-proxy-1` container. `codeduel-frontend-1` serves the frontend. `codeduel-api-1` uses internal port 5000 and `/health/ready`; `codeduel-worker-1` consumes BullMQ work. `codeduel-redis-1` provides password-protected Redis on the private backend network.

MongoDB is external Atlas, not a local container. The worker also uses a separate rootless judge Docker socket at `/run/user/1001/docker.sock`. Current gateway Docker tools inspect the host daemon and selected application containers, not that separate judge daemon. Container HTTP aliases resolve the inspected container address without publishing new application ports.

At discovery, public frontend/proxy/Redis worked while API and worker were already restarting with Atlas server-selection errors. That baseline is preserved in `SERVER_INVENTORY.md`. A homepage HTTP 200 does not establish API or submission health, and the logs' generic IP-allowlist suggestion does not establish the precise Atlas cause.

## Configured deployment boundaries

| Component | Host binding | Execution/storage |
| --- | --- | --- |
| Next.js web | `100.98.193.60:3080` | Container using host networking; non-root application |
| FastAPI | `127.0.0.1:18000` | Container using host networking; non-root application |
| Diagnostic gateway | `127.0.0.1:18081` | Dedicated `aiops-gateway` systemd account; root-owned installation under `/opt/aiops-gateway` |
| Ollama | `127.0.0.1:11434` | Local container and persistent model storage |
| Gemini | outbound HTTPS only | Optional Google-hosted reasoning; no inbound listener |
| PostgreSQL | `127.0.0.1:15432` | Local container and persistent database volume |
| Qdrant | `127.0.0.1:16333` | Local container and persistent vector storage |

The backend has neither a Docker socket mount nor root privileges. The gateway's Docker group membership is effectively host-root authority and makes it part of the trusted computing base; tool allowlists restrict callers, not the powers of a compromised gateway process. Internal services have no public hostname. Existing CodeDuel, Cloudflare, Tailscale, SSH, networks, and data volumes remain separate from the AI project.

## Evaluation and current limits

`python -m evals.run` injects a deterministic provider and mock gateway into the production `Agent` for eight synthetic incidents. This is labeled an orchestration/safety regression. `--provider ollama` and `--provider gemini` measure actual model decisions against the same fixture ground truth. JSON reports persist scenarios, decisions, observations, rubric, timing, and aggregate scores; optional database persistence adds `EvaluationRun` records. Tests never intentionally crash production services or change host networking.

The deployed gateway permits manual start/restart for five exact CodeDuel containers and manual start/stop/restart for aiops-demo. Autonomous grants are empty and backend autonomy is disabled. Host service writes, including Cloudflare, are disabled; the installer retires only this project’s exact earlier polkit grant. Verification polls a starting target for a bounded interval, and a later explicit Verify can finish the original action without executing it again. Configured health checks do not establish end-to-end submission, Atlas authentication or queue processing. Real-model acceptance remains unmet.

## Exact action policy (18 September 2026 source)

The installed gateway is the final authority for each `(tool, target)` pair. Its `allowed_actions` map permits an explicit signed manual action; its `autonomous_actions` subset marks a start/restart pair eligible for evidence-gated backend authorization. An absent target/action pair is denied even if the target is present in the read-only inventory. This preserves the typed frontend → authenticated backend → signed gateway → target path. Autonomous recovery remains default-off until real-model and live acceptance gates pass.
