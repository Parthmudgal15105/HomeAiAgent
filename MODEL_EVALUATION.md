# Local model evaluation

Status: in progress. These measurements are real Ollama CPU inference, but the initial four-case microbenchmark is not full incident accuracy.

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
| Root-cause accuracy |0/8|Running|
| Top-3 accuracy |1/8|Running|
| Average executed tools |4.125|Running|
| Unnecessary tools, total |14|Running|
| Repeated executions |0|Running|
| Rejected repeat attempts |24|Running|
| Invalid JSON |0|Running|
| Unsafe action attempts |0|Running|
| Average incident latency |265.24s|Running|

Every Qwen2.5 case reached the three-rejected-decision safety limit by repeating prior diagnostics. Valid JSON alone did not produce a useful diagnosis. Model selection remains provisional until the identical Qwen3 comparison and live acceptance complete.

## Optional Gemini provider

`gemini-3.8-flash` is available as an explicit cloud reasoning option while Ollama remains the default and continues to provide local embeddings. A live Interactions API connectivity smoke returned valid structured JSON in6.7394seconds with no retry. The production-loop synthetic Redis scenario then passed in22.4611seconds across four requests with root-cause/evidence accuracy100% and zero invalid, repeated, rejected, unnecessary or unsafe decisions. Per-request latencies were3.4532s,5.6957s,6.3295s and6.8752s. This single scenario is integration evidence only; complete the same eight-case suite before comparing its diagnostic quality with local candidates.

The server deployment authenticated to the configured model successfully, but its post-deployment generation smoke was blocked by HTTP429 after the key reached the20-request free-tier quota used during development. This is an external quota result, not a model-quality score; deployed inference remains unverified until a later successful run.
