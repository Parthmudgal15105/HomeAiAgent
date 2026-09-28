# Failure modes and operator escalation

The controller records a stable non-secret failure category with the incident and audit trail. A failure never authorizes a write.

| Category | Meaning | Safe next step |
|---|---|---|
| `MODEL_TIMEOUT` | One model decision exceeded its configured deadline. | Preserve observations; retry only through a new bounded investigation after checking model availability. |
| `MODEL_UNAVAILABLE` | The configured model endpoint or provider could not serve a request. | Check the configured provider and quota; do not switch providers automatically. |
| `MODEL_INVALID_OUTPUT` | Structured output or policy validation failed repeatedly. | Review the recorded validation feedback and model/evaluation contract. |
| `TOOL_TIMEOUT` | A diagnostic exceeded its deadline. | Treat it as missing evidence, not as proof of a component failure. |
| `TOOL_FAILURE` | An allowed diagnostic returned a non-timeout execution error. | Inspect the bounded error code and choose another discriminating check. |
| `INFRASTRUCTURE_FAILURE` | A local transport, dependency, or controller boundary failed. | Restore the controller dependency or escalate; do not infer an application root cause. |

## Capability gaps

`NEED_USER_INPUT` persists an `ESCALATED` incident rather than a generic open result. It carries `capability_status`, an optional machine-readable `capability_gap`, `missing_capability`, and `recommended_next_check`. `MISSING_TOOL` describes a missing safe observation or action; it cannot widen gateway scope.

MongoDB Atlas is limited to the read-only `mongodb_atlas_connectivity` diagnostic. It performs bounded SRV resolution, suffix-constrained shard resolution, pinned TCP, and verified TLS handshake checks without credentials or MongoDB queries. A successful result establishes network/TLS reachability only. Authentication, provider-side state, query health, and application configuration remain escalation paths.

## Time and loop bounds

Each investigation records per-step, model, tool, and optional RAG timing. The agent enforces its incident runtime, model-call budget, duplicate-read prevention, three rejected-decision limit, and configured tool/model deadlines. RAG retrieval is deferred until initial observation evidence by default so a CPU-only embedding request does not evict the reasoning model before the first decision.

Manual remediation remains approval-gated. A proposed start requires a successful fresh observation that the exact target is stopped; a restart requires the exact target to be running and unhealthy. Every action is separately verified; failed or uncertain verification remains unresolved or escalated.
