# Cloudflare Tunnel unavailable

Applies to `cloudflare`. The existing `cloudflared.service` is remotely managed. It forwards `codeduel.online` and `www.codeduel.online` to `http://localhost:8085`. Its systemd configuration contains a tunnel token and must not be printed or replaced. There is no local ingress file to regenerate.

## Symptoms and possible causes

Public CodeDuel fails while local proxy/API checks work; Cloudflare may return a tunnel error. Possible causes include an inactive connector, failed outbound connectivity, tunnel configuration, or an unavailable local origin. A 502 alone does not distinguish a tunnel failure from an API dependency failure.

## Recommended diagnostics

Compare `http_check` for the public homepage, local proxy `/healthz`, and `codeduel-api-ready`. Inspect `service_status` or `cloudflared_status`, then bounded `journal_logs` for `cloudflared` when needed. A running process does not prove an established tunnel connection. Use current journal errors and public/local reachability to refine the hypothesis. Investigate host routes/networking when outbound connection failures affect multiple services.

`/healthz` on port 8085 checks NGINX only. A healthy proxy cannot eliminate API/worker or Atlas failures.

## Safe remediation

Do not replace the token-bearing service, delete/recreate the tunnel, or change its authentication. Current policy disables systemd writes. A justified restart requires an operator-approved procedure accounting for existing CodeDuel access. Adding an AI public hostname is a separate explicit configuration change; the AI app is intended for private Tailscale access by default.

## Verification

Require connector active state plus successful public endpoint checks and healthy origins relevant to the incident. Keep API/queue failures separate if the frontend recovers while dependencies remain unavailable.
