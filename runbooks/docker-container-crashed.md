# Docker container crashed

## Symptoms
A configured container is exited, restarting, unhealthy, or repeatedly increasing its restart count. Distinguish an intentionally stopped workload from a reported incident.

## Likely causes
Application startup exception, dependency connection failure, out-of-memory termination, missing configuration, or exhausted disk space. Docker daemon failure differs from a single container crash.

## Recommended diagnostics
Inspect container state including exit code, OOM flag, restart count and health. Read a bounded sample of redacted logs. Check an implicated dependency or host memory/disk pressure; do not repeat the same inspection without evidence that state changed. A tool permission error is not proof that the container failed.

## Safe remediation
Start or restart only the exact allowlisted container after diagnosis and explicit persisted approval. Address a persistent dependency failure before restarting dependent applications. Never delete containers, prune volumes, or reset Docker as part of this workflow.

## Verification checks
Confirm running state, configured container health, dependency readiness and affected application endpoints. Record all recovery observations. If checks still fail, retain the unresolved incident and investigate further; do not replay an uncertain action.
