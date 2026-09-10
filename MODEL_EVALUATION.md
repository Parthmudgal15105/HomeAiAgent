# Local model evaluation

Status: in progress. These measurements are real Ollama CPU inference, but the initial four-case microbenchmark is not full incident accuracy.

Hardware: Intel i5-8250U,16GB RAM; Ollama limited to3CPU/7GB; no GPU offload. Both candidates are quantized Q4_K_M models.

| Candidate | Parameters | Model file | Four-case valid JSON | Expected next tool | Mean response |
|---|---:|---:|---:|---:|---:|
| qwen2.5:3b |3.1B|1.9GB|4/4|2/4|11.10s|
| qwen3:4b |4.0B|2.5GB|4/4|4/4|17.84s|

Raw timings, load times, generated tokens/sec and loaded-model/container memory are recorded in `reports/baseline-microbenchmark.json`. The simple benchmark allowed free-form arguments; several responses chose invalid arguments even when the tool name was correct. It cannot establish safe end-to-end reliability.

The canonical provider now constrains each tool's actual argument schema and current observation IDs, validates with Pydantic, and records first-token latency, total response, retries, invalid decisions and failures. Identical eight-case full-agent evaluations for each candidate are pending. qwen3:4b is a provisional test candidate; production selection is not final until those evaluations finish. Do not substitute the scripted8/8 result for model accuracy.
