# Local model evaluation

Status: production model gate not passed. These measurements are real Ollama CPU inference, but the initial four-case microbenchmark is not full incident accuracy.

## 28 September 2026 actual home-server run

Server revision `1575932` was deployed through the guarded deployment script. HomeServerAI backend, frontend, Ollama, Qdrant, PostgreSQL and the authenticated gateway registry were healthy. This run used the real server Ollama instance and `qwen2.5:3b`; it did **not** use mocked model responses. Safe recovery remained disabled.

The first baseline incident failed after 245.76 seconds with two invalid structured decisions. After reducing the prompt to one bounded action and replacing the report-sized local response contract with `action`, `reason`, and schema-constrained `args`, the model produced valid decisions but initially selected an invalid endpoint; preserving only current per-tool argument constraints fixed that orchestration defect. The final eight-scenario run (`api_stopped`, `redis_down`, `mongodb_down`, `cloudflared_stopped`, `docker_daemon_down`, `disk_full`, `host_network_down`, `wifi_rfkill`) used a 45-second first-decision budget. All eight timed out before a first decision: 0/8 passed, 0 tool calls, 0 malformed JSON responses, 0 retries, 0 repeated/unnecessary calls, and no unsafe action attempts. Mean incident latency was 45.08 seconds.

Classification: the packaging omissions and invalid target were **ORCHESTRATION** issues and are fixed; the final run is a **MODEL** latency/capability failure for this Qwen2.5:3b deployment. Prompt/context reduction cannot make this server/model combination meet the 45-second decision budget. The existing scripted fixture suite remains controller coverage only and must not be compared with this real-model result.

The production image intentionally excludes test tooling and the frontend runtime image does not expose the development test runner, so the existing backend/gateway/frontend scripted suites could not be executed in-place on this server without creating a separate temporary test environment. The deployed service health checks did pass. The unrelated CodeDuel `/api/explore/problems` endpoint remained intermittently 500 and its API container unhealthy; it is outside HomeServerAI and did not change this classification.

## 28 September 2026 reliability guardrails

The local-source controller now uses a compact prompt view for tools/topology, keeps the full response schema for validation, caps default Ollama output at 384 tokens, and rejects an estimated prompt-plus-output request above the configured context window before calling Ollama. A representative checked-in production registry measured approximately 7,515 estimated input tokens plus 384 output tokens against `OLLAMA_NUM_CTX=8192`; this is a guardrail estimate, not a successful inference measurement. RAG retrieval is deferred until initial observation evidence by default to avoid evicting the CPU reasoning model.

No new Ollama, Gemini, or live-host evaluation was run for this change. The scripted contract suite is controller coverage only; it must not be represented as model quality or production acceptance.

Hardware: Intel i5-8250U,16GB RAM; Ollama limited to3CPU/7GB; no GPU offload. Both candidates are quantized Q4_K_M models.

| Candidate | Parameters | Model file | Four-case valid JSON | Expected next tool | Mean response |
|---|---:|---:|---:|---:|---:|
| qwen2.5:3b |3.1B|1.9GB|4/4|2/4|11.10s|
| qwen3:4b |4.0B|2.5GB|4/4|4/4|17.84s|

Raw timings, load times, generated tokens/sec and loaded-model/container memory are recorded in `reports/baseline-microbenchmark.json`. The simple benchmark allowed free-form arguments; several responses chose invalid arguments even when the tool name was correct. It cannot establish safe end-to-end reliability.

The canonical provider now constrains each tool's actual argument schema and current observation IDs, validates with Pydantic, and records first-token latency, total response, retries, invalid decisions and failures. Identical eight-case full-agent evaluations for each candidate are pending. qwen3:4b is a provisional test candidate; production selection is not final until those evaluations finish. Do not substitute the scripted8/8 result for model accuracy.

## Eight-case production-agent comparison

Qwen2.5 completed on10 September2026 using Ollama directly, production Agent, isolated synthetic gateway and SQLite persistence. The eight fixtures and settings are recorded in `reports/model-comparison/2026-09-10-ollama-859cd5b6-90fe-47e8-bb53-d94c8608e0c5.json`. RAG and remediation are deliberately separate evaluations.

| Metric | qwen2.5:3b | qwen3:4b |
|---|---:|---|
| Root-cause accuracy |0/8|Not completed|
| Top-3 accuracy |1/8|Not completed|
| Average executed tools |4.125|Not completed|
| Unnecessary tools, total |14|Not completed|
| Repeated executions |0|Not completed|
| Rejected repeat attempts |24|Not completed|
| Invalid JSON |0|Not completed|
| Unsafe action attempts |0|Not completed|
| Average incident latency |265.24s|Not completed|

Every Qwen2.5 case reached the three-rejected-decision safety limit by repeating prior diagnostics. Valid JSON alone did not produce a useful diagnosis. Model selection remains provisional until the identical Qwen3 comparison and live acceptance complete.

## Optional Gemini provider

`gemini-3.8-flash` is available as an explicit cloud reasoning option while Ollama remains the default and continues to provide local embeddings. A live Interactions API connectivity smoke returned valid structured JSON in6.7394seconds with no retry. The production-loop synthetic Redis scenario then passed in22.4611seconds across four requests with root-cause/evidence accuracy100% and zero invalid, repeated, rejected, unnecessary or unsafe decisions. Per-request latencies were3.4532s,5.6957s,6.3295s and6.8752s. This single scenario is integration evidence only; complete the same eight-case suite before comparing its diagnostic quality with local candidates.

The server deployment authenticated to the configured model successfully, but its post-deployment generation smoke was blocked by HTTP429 after the key reached the20-request free-tier quota used during development. This is an external quota result, not a model-quality score; deployed inference remains unverified until a later successful run.

## 18 September 2026 real-provider acceptance

The intended-setting Gemini run completed two cases (API stopped and Redis down), both FAILED with zero diagnostics and approximately 240 seconds per case, before the 600-second outer command limit stopped the suite. No complete accuracy result is available from that run.

A separate bounded availability run used the same eight scenarios and production Agent, with explicit per-call timeout 20 seconds and incident runtime limit 60 seconds. It completed and persisted an EvaluationRun: **0/8 passed**, one ReadTimeout and seven HTTP 429 quota errors (the provider reported a 20-request/day free-tier limit). No tools or actions executed. Root-cause and evidence scores were zero; mean case latency was 5.2517 seconds. Zero invalid/unsafe decisions here reflects no successful decisions, not demonstrated model safety. These changed timeout settings make this an availability result, not a comparable diagnostic-quality benchmark.

Report: `reports/model-comparison/2026-09-18-gemini-bounded-availability.json`. The server retains the longer-run log in `reports/private/gemini-eval-20260918.log`. A separate live frontend-health investigation ended FAILED after 240.389 seconds with ReadTimeout and zero observations/actions. No production autonomous recovery was attempted. Backend autonomy is false and gateway autonomous grants are empty until a full intended-setting evaluation and live investigation pass.

## Scripted fixtures — not model results

The 18 September controller fixture rerun passed 8/8 without calling a reasoning model. It verifies orchestration only and does not change model acceptance.

## Separate retrieval measurement

Local all-minilm embeddings ingested 14 runbook chunks. Recall@4 was 13/14 (92.86%) at threshold 0.45, including after clarifying the generic runbook title. This small authored benchmark is not independent holdout accuracy. A verified manual production incident was indexed in Qdrant, but the query “Manual restart codeduel-frontend-1 verified recovery” retrieved no result at the same threshold. Retrieval remains partially accepted.
