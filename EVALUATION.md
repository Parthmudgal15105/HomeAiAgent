# Evaluation

Evaluation separates deterministic orchestration from actual local-model performance. No production service is deliberately stopped.

## Verified regression results

- **155 Python tests passed**, covering gateway scopes/schemas/timeouts/HTTP rebinding/redaction, signed one-use approvals, models, migrations, hypotheses, evidence ownership, provider JSON validation/retry, RAG protocol, context bounds, controller routes and recovery.
- Alembic upgrade and schema drift checks passed; combined development environment dependency check passed.
- Nine frontend tests, Next.js production build and TypeScript checks passed again on11 September2026. Server-side browser-session/proxy tests passed: unauthenticated401, wrong-password401, login200, authenticated history200, cross-origin mutation403, arbitrary path404.
- **19/19 live read-only gateway operations** executed successfully. A successful diagnostic operation can still report an unhealthy target; execution success is not service health.
- Remote network validation: dashboard3080 reachable over Tailscale; backend18000, gateway18081, Ollama11434, PostgreSQL15432 and Qdrant16333 were not reachable at the Tailscale address.

## Deterministic incident benchmark

The production `Agent` runs against a `ScriptedProvider` and `MockDiagnosticGateway` for eight independent fixtures: API stopped, Redis down, MongoDB down, cloudflared stopped, Docker daemon down, disk nearly full, disconnected networking and RF-kill-like trace.

On the deployed backend: **8/8 passed**, average2.875 diagnostic calls, zero unnecessary/repeated/unsafe calls, citation ownership accuracy100%, average57ms per fixture. These are orchestration regression numbers; scripted decisions do not measure LLM intelligence or inference latency. Fixtures, decisions, observations and scoring rubric are saved with provider name and fixture hash, and an EvaluationRun is persisted in PostgreSQL.

## Local retrieval benchmark

all-minilm embeddings (384 dimensions), Qdrant local collection, similarity threshold0.45, top4 retrieval. Eleven runbooks ingested. Eleven authored title/symptom queries each retrieved their matching runbook: **Recall@4=11/11**. These queries are a small authored check, not independent holdout data or a broad retrieval-quality estimate. Full ranked scores are retained in `reports/rag-benchmark.json` on the server.

## Live approval and recovery benchmark

An explicitly scoped, isolated `aiops-demo` HTTP container was observed stopped. Production Agent persisted an evidence-backed test diagnosis and pending action. Production IncidentService handled approval and called the actual gateway.

Verified: unsigned write rejected; pending action persisted; exact approved start executed; Docker running/healthy and HTTP200 checks passed; incident marked RESOLVED; embedding persisted in Qdrant and retrieved (similarity0.692); replay rejected independently by backend and gateway. Successful run8.86seconds. First run had a deliberately too-small demo CPU budget and correctly remained unresolved when health checks failed. The corrected demo uses0.5CPU/96MB.

This validates the real write/verification/RAG integration but uses an authored diagnosis, not an LLM. CodeDuel containers were never stopped, restarted or reconfigured for this test.

## Local reasoning-model benchmark

Completed actual qwen2.5:3b evaluation:8 cases,0/8 root-cause accuracy,Top-3 accuracy1/8,4.125 average executed tools,14 unnecessary executed tools,0 repeated executions,24 rejected duplicate attempts,0 invalid JSON,0 unsafe action attempts,265.24s average diagnosis latency. All cases failed safely after three rejected decisions. These results do not qualify the model for production acceptance. Qwen3 full-suite comparison is in progress. See MODEL_EVALUATION.md for model load/memory/latency/JSON/tool-choice measurements. Do not substitute the scripted8/8 result for this benchmark.

## Interpretation and limits

Root-cause scoring uses declared lexical term groups and decisive diagnostic evidence. Citation accuracy checks that IDs belong to this incident; it does not prove semantic entailment. Small synthetic datasets cannot establish broad production accuracy or calibrated confidence. Confidence remains an explicitly labeled model estimate with conservative backend ceilings. Recovery for generic host symptoms is disabled until symptom-specific checks are configured; successful SSH alone cannot certify an arbitrary host recovery.

Run `pytest` after installing `backend/requirements-dev.txt`, `python -m evals.run` for regression, and `python -m evals.run --provider ollama --model MODEL` for real-model synthetic evaluation. Reports record unmeasured metrics as null with reasons.

## Current live baseline —11 September2026

Gateway19/19 diagnostics and dashboard authentication/logout passed again. All platform components are healthy; Tailscale3080 is reachable, while18000/18081/11434/15432/16333/5432/6333/2375 are not. During qwen3 inference: Ollama3.846GiB, backend71.12MiB, frontend49.61MiB, PostgreSQL35.56MiB, Qdrant50.03MiB, gateway144.41MiB. These are snapshots, not peak-memory guarantees. CodeDuel homepage200, API500 and API container unhealthy before any new deployment. Read-only gateway logs show MongoServerSelectionError/TLS alert80; the other four CodeDuel containers remain healthy. No CodeDuel service was changed.
