# Application HTTP 502

## Symptoms
The configured public URL returns Bad Gateway while DNS may still resolve. A running tunnel process alone does not establish origin connectivity.

## Likely causes
Reverse proxy origin unavailable, application container stopped, invalid upstream routing, or a dependency failure causing application startup to fail. An old log error does not establish an active outage.

## Recommended diagnostics
Check the exact configured public and local health URLs. Inspect tunnel or proxy state if the local service responds but the public route fails. If local readiness fails, inspect application state and recent bounded logs, then check the implicated database or queue. Select each next diagnostic from fresh observations rather than following this list mechanically.

## Safe remediation
Recommend only the evidenced target. Restarting the tunnel will not repair a stopped application or unavailable database. Allowlisted start/restart actions need persisted approval; configuration changes and high-risk operations remain manual.

## Verification checks
Confirm dependency readiness, application readiness, local reverse-proxy response and the actual public application route. Do not use an unimplemented health URL. Successful homepage delivery alone is insufficient for an API outage.
