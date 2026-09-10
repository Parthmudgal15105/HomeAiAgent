# Application unavailable

## Symptoms
A configured application does not load, rejects connections, or returns errors. Select its service profile to find actual URLs, containers and dependencies. Do not assume CodeDuel names apply to other workloads.

## Likely causes
An application process stopped, an upstream dependency is unavailable, a reverse proxy cannot reach its origin, or the host lacks resources or connectivity. A successful static homepage does not establish API or worker health.

## Recommended diagnostics
Choose a discriminating configured HTTP check, container inspection or service status from the current symptom. Use the dependency graph to investigate implicated downstream components. Inspect bounded redacted logs after observing an unhealthy process. Check disk, memory or network only when observations support those hypotheses. Historical incidents are guidance and never current evidence.

## Safe remediation
Explain the observed cause and recommended manual fix. Only allowlisted start/restart operations can become pending actions, and each needs explicit operator approval. A remote database is not a local container. Never change unrelated workload configuration or issue arbitrary shell commands.

## Verification checks
Check the affected process, implicated dependencies, local readiness and configured public endpoint. Resolve only if all configured recovery checks pass. A missing check or unavailable tool is unknown health; report the remaining uncertainty.
