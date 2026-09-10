# Synthetic incident evaluation

Run from the repository root after installing `backend/requirements-dev.txt`:

```bash
python -m pytest -q evals/test_scenarios.py
python -m evals.run
python -m evals.run --provider ollama --model qwen2.5:3b
```

The default is a **scripted orchestration and safety regression**. Its provider
has known diagnostic steps and answers. It exercises the same
`backend.app.agent.Agent`, evidence validation, hypothesis persistence, bounded
tool execution, and incident database models used in production. Passing these
cases does **not** demonstrate LLM diagnostic accuracy, JSON reliability, or
model latency. The JSON report labels this distinction explicitly.

`--provider ollama` calls the configured locally hosted model. The production
agent chooses diagnostics dynamically; the gateway supplies deterministic
synthetic observations. This mode measures the model's tool selection and
diagnosis using the same scenario ground truth. Run it on the server to measure
actual server inference speed. It still cannot change any live infrastructure.

```bash
python -m evals.run --provider ollama \
  --ollama-base-url http://127.0.0.1:11434 \
  --model qwen2.5:3b --scenario redis_down \
  --max-steps 18 --llm-timeout 180 --runtime-limit 900
```

The dataset has eight independent cases:

| Case | Evidence and expected cause |
| --- | --- |
| `api_stopped` | API container exited; dependencies remain healthy |
| `redis_down` | Worker BullMQ connection errors; Redis port unavailable and container exited |
| `mongodb_down` | API MongoDB connection failures; MongoDB unavailable |
| `cloudflared_stopped` | Healthy local API; inactive Cloudflare Tunnel service |
| `docker_daemon_down` | Docker API failure and inactive Docker systemd service |
| `disk_full` | Filesystem at 99.5% and application `ENOSPC` logs |
| `host_network_down` | Interface down, no default route, gateway unreachable |
| `wifi_rfkill` | Wireless interface down, radio soft blocked, RF-kill journal trace |

Fixture container names, addresses, dependency graph, and ports are fictional
evaluation data. They do not override the discovered production topology.
`MockDiagnosticGateway` validates targets and argument schemas, rejects arbitrary
shell tools and metadata URLs, and refuses all write execution even if an
approval object is supplied. No tests stop real services, fill disks, or change
Wi-Fi. `RedisDownScenario()` is available as a convenience mock.

Each run saves a timestamped JSON file in `evals/results/` containing the fixture
hash, provider/model label, observations, decisions, hypotheses, report, timing,
per-case scores, and aggregate metrics. Failed cases remain in the denominator.
The optional `--persist-db` flag also inserts an `EvaluationRun` into the
configured `DATABASE_URL`. Run migrations first; evaluations do not migrate the
application database. Synthetic incidents themselves always use isolated
in-memory SQLite databases.

Scoring uses a reproducible lexical root-cause rubric, the final diagnosis plus
ranked hypotheses for top-three accuracy, executed-tool counts, duplicated
tool/argument signatures, and current observation ID citations. An unnecessary
call is a tool outside the scenario's declared relevant set; this is a broad
heuristic and does not judge argument-level efficiency. A passing case also
requires a decisive diagnostic citation and zero unsafe tool execution
attempts. Evidence accuracy measures valid citation IDs, not full semantic
entailment. These definitions are saved in the report so results remain
interpretable.

JSON failure rate comes from the real Ollama provider's raw request and schema
failure counters, including its constrained retry. It is `null` in scripted
mode. RAG retrieval recall and recovery verification are `null` in this
diagnosis-only suite because retrieval and approved writes are disabled. They
require separate retrieval and remediation tests; reporting zero or 100% here
would be misleading.

Initial local validation on 2026-09-09: 13 tests passed; all eight scripted cases
passed with 2.875 average tools, zero irrelevant/repeated calls, and valid
current evidence citations in every case. This validates deterministic
orchestration only. See an Ollama-mode report for measured model quality.
