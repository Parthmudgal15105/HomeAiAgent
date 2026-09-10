# Host diagnostic gateway

This process is the host trust boundary. The backend must have neither root nor
Docker socket access. Run the gateway as a dedicated `aiops-gateway` host account
with Docker and journal groups, binding only to `127.0.0.1:18081`.

**Docker group membership is effectively host-root capability.** API allowlists
constrain callers but cannot remove that risk if the gateway process is
compromised. Keep it small, private, patched and separate from the backend.
The systemd hardening settings do not sandbox the Docker daemon on its behalf.

Install `requirements.txt` into a dedicated Python >=3.10 virtual environment.
The included `aiops-gateway.service` is a generic example. The actual deployed, root-owned unit is `deploy/aiops-gateway.service`, installed with `scripts/install_gateway.sh`. Its read-only filesystem protection deliberately
keeps `/proc` and host networking visible to diagnostics. `/var/lib/aiops-gateway`
is its only persistent writable directory. ICMP uses the host's unprivileged
ping policy; unavailable permission returns a diagnostic error, not escalation.

Set `GATEWAY_CONFIG_PATH` to an administrator-owned JSON file matching
`config.example.json`. Set `GATEWAY_TOKEN` and `GATEWAY_APPROVAL_SECRET` to
independently generated random secrets of at least 32 characters. They belong
in a mode-0600 environment file, never source control. The environment file
is read by systemd, not by the unprivileged process. The config/code/venv should
not be writable by `aiops-gateway`. `GATEWAY_STATE_PATH` optionally overrides
the replay database path.

Routes:

- `GET /healthz`: minimal unauthenticated process liveness.
- `GET /tools`: metadata with risk levels and JSON schemas, including configured
  target enums. Requires `Authorization: Bearer <GATEWAY_TOKEN>`.
- `POST /tools/{name}`: direct JSON arguments and the same bearer authentication.
  Response: `{tool, ok, result, error?, duration_ms}`. Invalid schemas return 422,
  unknown/disabled tools 404, missing/invalid approvals 403. Normal diagnostic
  failures have `ok:false` with bounded, redacted error text.

The configuration is an explicit scope policy. `containers`, `services`, `hosts`,
`disk_paths`, exact `http_urls`, and exact `tcp_targets` are allowlists. Container
HTTP aliases resolve the configured container's network address from a reduced
Docker inspect projection on every call. Their container/port/path cannot be
changed by model input. Set `network` on aliases when a container has several
networks. An Atlas SRV cluster hostname is not necessarily an A/AAAA host; a
failed ordinary DNS lookup alone does not establish an Atlas outage. Add actual
inspected shard hostnames/ports for TCP diagnosis when appropriate.

HTTP permits exact configured URLs only, rejects URL redirects, validates DNS
addresses, and pins the validated address at the socket layer while preserving
HTTPS certificate checks and SNI. Public endpoints cannot resolve to private,
link-local, reserved or multicast destinations. Explicit localhost endpoints
must resolve to loopback; container aliases must resolve to a private container
address. HTTP headers and body share a wall-clock deadline. Other TCP probes use
exact configured host/port pairs and reject special addresses. No proxy
environment variables are honored.

Container inspect excludes environment, commands, mounts, labels and health
log output. Process tools omit command arguments/environment. Log tools apply
best-effort credential and token redaction; logs may still contain unrecognized
secrets, so all diagnostic storage and inference remain local. Commands use
fixed binary names, argument arrays, a sanitized environment, bounded output
and hard timeouts; no arbitrary shell or command tool exists.

The reusable gateway example defaults writes off. The current installed policy
sets `writes_enabled:true`, `write_containers:["aiops-demo"]`, and
`write_services:[]`; all preexisting containers remain read-only. Production
writes require actual local-model validation and a reviewed scope change as
described in SECURITY.md. Write target lists must remain subsets of diagnostic
allowlists. No high-risk operations exist. Service writes call
`systemctl --no-ask-password` without sudo and will be denied unless a separately
reviewed host authorization policy permits the exact service. Do not grant
unrestricted sudo or general systemd management.

Each write requires a persisted human approval in the backend and these headers:

```
X-Action-ID: <unique action id, 8–128 letters/digits/_/->
X-Approval-Expires: <Unix timestamp, now < expiry <= now+600>
X-Approval-Token: <hex HMAC-SHA256>
```

The UTF-8 signed message is exactly:

```
action_id + ':' + tool + ':' + json.dumps(arguments, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + ':' + expires
```

The gateway records action consumption transactionally in SQLite **before**
execution. Replay is rejected across process restarts; failed or uncertain
operations require a new approval, never automatic retry. The HMAC authorizes
the exact tool, arguments, action and expiry; the model never receives the
secret. A compromised backend remains capable of signing writes, so backend
approval authorization/persistence is part of the trust boundary too. Successful
execution returns `verification_required:true` and does not claim recovery.

Test from the repository root:

```
python -m pip install -r diagnostic_gateway/requirements.txt pytest httpx
python -m pytest diagnostic_gateway/tests -q
```
