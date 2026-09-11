from __future__ import annotations

import concurrent.futures
import http.server
import json
import socketserver
import threading
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from diagnostic_gateway.config import GatewayConfig, utilization_severity
from diagnostic_gateway.main import create_app
from diagnostic_gateway.safety import ApprovalError, ApprovalLedger, CommandResult, ToolError, approval_signature, http_probe, redact, run_command, safe_address
from diagnostic_gateway.tools import DiagnosticTools


TOKEN = "t" * 48
SECRET = "s" * 48
AUTH = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def config(tmp_path):
    return GatewayConfig(containers=["codeduel-api-1", "aiops-demo"], write_containers=["aiops-demo"], services=["docker", "cloudflared", "tailscaled", "ssh"], hosts=["codeduel.online", "127.0.0.1", "localhost"], http_urls=["https://codeduel.online", "http://127.0.0.1:8085"], tcp_targets=[{"host": "127.0.0.1", "port": 8085}], writes_enabled=True, state_path=str(tmp_path / "approvals.sqlite3"))


@pytest.fixture
def client(config):
    return TestClient(create_app(config, token=TOKEN, approval_secret=SECRET))


def test_auth_required_for_metadata_and_calls(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/tools").status_code == 401
    assert client.post("/tools/docker_list", json={}).status_code == 401
    assert client.get("/tools", headers=AUTH).status_code == 200


def test_missing_auth_secret_fails_closed(config):
    client = TestClient(create_app(config, token="", approval_secret=SECRET))
    assert client.get("/tools", headers=AUTH).status_code == 503


def test_container_inventory_projects_safe_fields_and_does_not_infer_absence_from_truncation(config, monkeypatch):
    tools = DiagnosticTools(config)
    commands = []
    def command(argv):
        commands.append(argv)
        return CommandResult(json.dumps({'Names': 'aiops-demo', 'State': 'running'}) + '\n{', '', 0, True)
    monkeypatch.setattr(tools, 'command', command)
    result = tools.docker_list()
    assert result['missing_configured_containers'] == []
    assert result['unobserved_configured_containers'] == ['codeduel-api-1']
    assert result['truncated'] is True
    projection = commands[0][-1]
    assert '{{json .Names}}' in projection
    assert '.Labels' not in projection and '.Command' not in projection and '{{json .}}' not in projection


def test_all_required_read_tools_registered(client):
    metadata = client.get("/tools", headers=AUTH).json()["tools"]
    names = {item["name"] for item in metadata if item["risk_level"] == "READ_ONLY"}
    assert len(names) == 19
    assert {"dns_lookup", "ping_host", "http_check", "docker_list", "docker_inspect", "docker_logs", "service_status", "journal_logs", "network_interfaces", "route_table", "memory_usage", "disk_usage", "system_uptime", "process_list", "port_check"} <= names
    assert not any(name in names for name in ("run_shell", "execute_bash"))
    inspect = next(item for item in metadata if item["name"] == "docker_inspect")
    assert inspect["parameters"]["properties"]["container"]["enum"] == ["codeduel-api-1", "aiops-demo"]
    assert inspect["parameters"]["additionalProperties"] is False


@pytest.mark.parametrize("tool,args", [
    ("docker_logs", {"container": "codeduel-api-1; whoami"}),
    ("service_status", {"service": "--all"}),
    ("docker_logs", {"container": "codeduel-api-1", "lines": 501}),
    ("docker_logs", {"container": "codeduel-api-1", "lines": "100"}),
    ("ping_host", {"hostname": "codeduel.online", "count": 100}),
    ("process_list", {"limit": 1000}),
    ("docker_list", {"command": "rm -rf /"}),
    ("http_check", {"url": "https://codeduel.online", "headers": {}}),
    ("port_check", {"host": "localhost", "port": True}),
])
def test_strict_schema_rejects_injection_and_invalid_args(client, tool, args):
    assert client.post("/tools/" + tool, json=args, headers=AUTH).status_code == 422


@pytest.mark.parametrize("tool,args", [
    ("docker_inspect", {"container": "unrelated-production"}),
    ("service_status", {"service": "unrelated-service"}),
    ("dns_lookup", {"hostname": "secret.attacker.example"}),
    ("http_check", {"url": "http://169.254.169.254/latest/meta-data"}),
    ("http_check", {"url": "https://codeduel.online/unknown"}),
    ("http_check", {"url": "https://codeduel.online@attacker.example"}),
    ("http_check", {"url": "https://codeduel.online?target=http://127.0.0.1"}),
    ("disk_usage", {"path": "/etc/shadow"}),
    ("port_check", {"host": "127.0.0.1", "port": 5432}),
])
def test_scopes_rejected_before_execution(client, tool, args, monkeypatch):
    registry = client.app.state.registry
    definition = registry.definitions[tool]
    def forbidden(**kwargs):
        pytest.fail("Disallowed tool reached execution")
    monkeypatch.setattr(definition, "handler", forbidden)
    response = client.post("/tools/" + tool, json=args, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "allowlisted" in response.json()["error"]


def test_unknown_tool_and_disabled_writes(config):
    config.writes_enabled = False
    client = TestClient(create_app(config, token=TOKEN, approval_secret=SECRET))
    assert client.post("/tools/run_shell", json={}, headers=AUTH).status_code == 404
    assert client.post("/tools/restart_container", json={"container": "aiops-demo"}, headers=AUTH).status_code == 404


def test_request_body_limit_and_safe_validation_errors(client):
    assert client.post("/tools/docker_list", content=b" " * 8193, headers=AUTH).status_code == 413
    response = client.post("/tools/docker_logs", json={"container": "password=hide-me!"}, headers=AUTH)
    assert "hide-me" not in response.text


@pytest.mark.parametrize("percent,expected", [(0, "normal"), (79.99, "normal"), (80, "warning"), (89.99, "warning"), (90, "high"), (95, "high"), (95.01, "critical"), (100, "critical")])
def test_threshold_boundaries(percent, expected):
    assert utilization_severity(percent) == expected


def test_secret_redaction_recurses_and_removes_common_credentials():
    value = {"password": "do-not-display", "access_token": "never-show", "nested": ["mongodb+srv://alice:mySecret@cluster.example/app", "password=abc123 token: xyz456", "Authorization: Bearer eyJsecret.signature.value", "api_key='key-value'", "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"]} # secret-scan: fixture
    rendered = json.dumps(redact(value))
    for secret in ("do-not-display", "never-show", "mySecret", "abc123", "xyz456", "key-value", "eyJsecret", "\nsecret\n"):
        assert secret not in rendered
    assert "[REDACTED]" in rendered


@pytest.mark.parametrize("value,secret", [
    ("sessionID=ses-123456789 session_id: abcdefgh", "ses-123456789"),
    ({"sessionId": "ses-123456789"}, "ses-123456789"),
    ("tailscale received tskey-auth-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKL", "tskey-auth-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKL"), # secret-scan: fixture
    ("cloudflared --token arbitrary-cloudflare-credential", "arbitrary-cloudflare-credential"),
    ("cloudflared --token='arbitrary quoted tunnel token'", "arbitrary quoted tunnel token"),
    ("credential blob eyJhIjoiYWJjZCIsInQiOiJ0dW5uZWwiLCJzIjoic2VjcmV0In0=", "eyJhIjoiYWJjZCIsInQiOiJ0dW5uZWwiLCJzIjoic2VjcmV0In0="),
    ("API key sk-proj-abcdefghijklmnopqrstuvwxyz0123456789", "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"), # secret-scan: fixture
    ("key ghp_abcdefghijklmnopqrstuvwxyz0123456789", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"), # secret-scan: fixture
    ("Authorization: Bearer raw-arbitrary-token", "raw-arbitrary-token"),
])
def test_infrastructure_token_and_session_redaction(value, secret):
    assert secret not in json.dumps(redact(value))


@pytest.mark.parametrize("value,secrets", [
    ("Cookie: first=first-secret; second=second-secret\r\nstatus: failed", ["first-secret", "second-secret"]),
    ("Set-Cookie: auth=some-secret; HttpOnly; Secure", ["some-secret"]),
    ("Proxy-Authorization: Custom opaque-value", ["opaque-value"]),
    ("postgresql+psycopg://alice:pw@private-db.example/database?sslmode=require", ["alice", "pw", "private-db.example"]), # secret-scan: fixture
    ("mongodb+srv://private-cluster.example/application", ["private-cluster.example"]),
    ("redis://:password@redis.internal:6379/0", ["password", "redis.internal"]),
])
def test_full_headers_and_database_uris_redacted(value, secrets):
    rendered = redact(value)
    assert all(secret not in rendered for secret in secrets)
    assert "REDACTED" in rendered


def test_normalized_output_is_bounded_and_truncation_is_explicit(client, config, monkeypatch):
    monkeypatch.setattr(client.app.state.registry.definitions["network_interfaces"], "handler",
                        lambda: {"interfaces": ["x" * 50000], "password": "never-output-this"})
    response = client.post("/tools/network_interfaces", json={}, headers=AUTH)
    assert response.json()["result"]["truncated"] is True
    assert len(response.content) < config.max_output_bytes
    assert "never-output-this" not in response.text


def test_failed_write_consumes_approval_and_never_retries(client, monkeypatch):
    calls = []
    def uncertain(**args):
        calls.append(args)
        raise ToolError("Timeout; execution outcome is unknown")
    monkeypatch.setattr(client.app.state.registry.definitions["start_container"], "handler", uncertain)
    args, action, expiry = {"container": "aiops-demo"}, "uncertain-action-1", str(int(time.time()) + 120)
    headers = {**AUTH, "X-Action-ID": action, "X-Approval-Expires": expiry,
               "X-Approval-Token": approval_signature(SECRET, action, "start_container", args, expiry)}
    assert client.post("/tools/start_container", json=args, headers=headers).json()["ok"] is False
    assert client.post("/tools/start_container", json=args, headers=headers).status_code == 403
    assert len(calls) == 1


def test_execution_response_redacts_log_and_error(client, monkeypatch):
    monkeypatch.setattr(client.app.state.registry.definitions["docker_logs"], "handler", lambda **kwargs: {"lines": ["password=private-value"]})
    response = client.post("/tools/docker_logs", json={"container": "codeduel-api-1"}, headers=AUTH)
    assert response.json()["ok"] is True
    assert "private-value" not in response.text


@pytest.mark.parametrize("address", ["169.254.169.254", "10.0.0.1", "127.0.0.1", "::1", "0.0.0.0", "224.0.0.1", "fd00::1"])
def test_public_http_rejects_private_and_special_addresses(address):
    assert not safe_address(address)


def test_http_dns_rebinding_and_mixed_answers_rejected(monkeypatch):
    monkeypatch.setattr("diagnostic_gateway.safety.resolve_addresses", lambda host: ["8.8.8.8", "127.0.0.1"])
    with pytest.raises(ToolError, match="network scope"):
        http_probe("https://codeduel.online")
    assert safe_address("127.0.0.1", local_target=True)
    assert safe_address("::1", local_target=True)
    assert not safe_address("169.254.169.254", container_target=True)


class HTTPHandler(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        self.seen.append(self.path)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/secret")
            self.end_headers()
        elif self.path == "/large":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 10000)
        elif self.path == "/slow":
            try:
                for character in b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}":
                    self.wfile.write(bytes([character]))
                    self.wfile.flush()
                    time.sleep(0.04)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    def log_message(self, *args):
        pass


@pytest.fixture
def local_http():
    HTTPHandler.seen = []
    server = socketserver.TCPServer(("127.0.0.1", 0), HTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_http_local_probe_redirect_and_bounded_preview(local_http):
    result = http_probe(local_http + "/health")
    assert result["reachable"] and result["status_code"] == 200
    assert result["body_preview"] == '{"ok":true}'
    redirect = http_probe(local_http + "/redirect")
    assert redirect["status_code"] == 302
    assert redirect["redirect_followed"] is False
    large = http_probe(local_http + "/large")
    assert len(large["body_preview"]) <= 4096
    assert large["body_truncated"] is True
    assert HTTPHandler.seen == ["/health", "/redirect", "/large"]


def test_http_uses_validated_numeric_address_without_second_dns(local_http, monkeypatch):
    # DNS returns an allowed address once. Subsequent DNS lookups would fail.
    calls = []
    def resolve(host):
        calls.append(host)
        return ["127.0.0.1"]
    monkeypatch.setattr("diagnostic_gateway.safety.resolve_addresses", resolve)
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: pytest.fail("Unexpected second DNS lookup"))
    assert http_probe(local_http)["reachable"]
    assert calls == ["127.0.0.1"]


def test_http_total_deadline_blocks_slow_drip_headers(local_http):
    started = time.monotonic()
    result = http_probe(local_http + "/slow", timeout=0.15)
    assert result["reachable"] is False
    assert time.monotonic() - started < 0.8


def test_container_http_alias_uses_only_configured_container_port_path(config, monkeypatch):
    from diagnostic_gateway.config import ContainerHTTP
    config.container_http = {"api-ready": ContainerHTTP(container="codeduel-api-1", port=5000, path="/health/ready", network="codeduel_default")}
    tools = DiagnosticTools(config)
    monkeypatch.setattr(tools, "docker_inspect", lambda container: {"networks": [{"name": "codeduel_default", "ip_address": "172.20.0.8"}]})
    calls = []
    monkeypatch.setattr("diagnostic_gateway.tools.http_probe", lambda url, **kwargs: calls.append((url, kwargs)) or {"reachable": True})
    result = tools.http_check("api-ready")
    assert result["container"] == "codeduel-api-1"
    assert calls == [("http://172.20.0.8:5000/health/ready", {"address": "172.20.0.8", "container_target": True})]
    monkeypatch.setattr(tools, "docker_inspect", lambda container: {"networks": [{"name": "codeduel_default", "ip_address": "169.254.169.254"}]})
    with pytest.raises(ToolError, match="network scope"):
        tools.http_check("api-ready")


def test_approval_required_and_valid_action_executes_once(client, monkeypatch):
    executions = []
    monkeypatch.setattr(client.app.state.registry.definitions["restart_container"], "handler", lambda **args: executions.append(args) or {"execution_succeeded": True, "verification_required": True})
    args = {"container": "aiops-demo"}
    assert client.post("/tools/restart_container", json=args, headers=AUTH).status_code == 403
    expires = str(int(time.time()) + 120)
    action = "test-action-0001"
    headers = {**AUTH, "X-Action-ID": action, "X-Approval-Expires": expires, "X-Approval-Token": approval_signature(SECRET, action, "restart_container", args, expires)}
    response = client.post("/tools/restart_container", json=args, headers=headers)
    assert response.status_code == 200 and response.json()["ok"]
    assert len(executions) == 1
    assert client.post("/tools/restart_container", json=args, headers=headers).status_code == 403
    assert len(executions) == 1


def test_unconsumed_denial_cannot_overwrite_previous_approval_audit(client, config, monkeypatch):
    import sqlite3
    monkeypatch.setattr(client.app.state.registry.definitions["restart_container"], "handler", lambda **args: {"execution_succeeded": True})
    args, action, expires = {"container": "aiops-demo"}, "audit-action-0001", str(int(time.time()) + 120)
    headers = {**AUTH, "X-Action-ID": action, "X-Approval-Expires": expires, "X-Approval-Token": approval_signature(SECRET, action, "restart_container", args, expires)}
    assert client.post("/tools/restart_container", json=args, headers=headers).json()["ok"]
    denied = client.post("/tools/restart_container", json={"container": "unlisted-container"}, headers=headers)
    assert denied.json()["ok"] is False
    with sqlite3.connect(config.state_path) as db:
        stored = json.loads(db.execute("SELECT result FROM consumed_approvals WHERE action_id=?", (action,)).fetchone()[0])
    assert stored["ok"] is True


def test_approval_binds_exact_action_tool_arguments_and_expiry(config):
    ledger = ApprovalLedger(config.state_path)
    args = {"container": "aiops-demo"}
    action, expiry = "test-action-0002", str(int(time.time()) + 120)
    sig = approval_signature(SECRET, action, "restart_container", args, expiry)
    for changed in ({"tool": "start_container"}, {"arguments": {"container": "codeduel-api-1"}}, {"expires": str(int(expiry) + 1)}, {"action_id": "test-action-0003"}):
        values = dict(secret=SECRET, action_id=action, tool="restart_container", arguments=args, expires=expiry, signature=sig)
        values.update(changed)
        with pytest.raises(ApprovalError):
            ledger.consume(**values)
    for expiry in (str(int(time.time()) - 1), str(int(time.time()) + 700), "invalid"):
        with pytest.raises(ApprovalError):
            ledger.consume(secret=SECRET, action_id=action, tool="restart_container", arguments=args, expires=expiry, signature=sig)


def test_replay_protection_survives_new_ledger_and_concurrent_requests(config):
    args, action, expiry = {"container": "aiops-demo"}, "test-action-concurrent", str(int(time.time()) + 120)
    sig = approval_signature(SECRET, action, "restart_container", args, expiry)
    ledger = ApprovalLedger(config.state_path)
    def consume():
        try:
            ledger.consume(secret=SECRET, action_id=action, tool="restart_container", arguments=args, expires=expiry, signature=sig)
            return True
        except ApprovalError:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(lambda _: consume(), range(4))) == 1
    ledger = ApprovalLedger(config.state_path)
    assert consume() is False


def test_command_timeout_and_output_limit(monkeypatch):
    import sys
    monkeypatch.setattr("diagnostic_gateway.safety.shutil.which", lambda *args, **kwargs: sys.executable)
    with pytest.raises(ToolError, match="timeout"):
        run_command(["docker", "-c", "import time; time.sleep(3)"], timeout=0.1)
    result = run_command(["docker", "-c", "import sys; sys.stdout.write('x'*1000000); sys.stdout.flush()"], timeout=2, max_bytes=1024)
    assert result.truncated is True
    assert len(result.stdout.encode()) + len(result.stderr.encode()) == 1024
    with pytest.raises(ToolError, match="not allowlisted"):
        run_command(["sh", "-c", "echo forbidden"])


def test_docker_inspect_command_excludes_secrets(config, monkeypatch):
    tools = DiagnosticTools(config)
    commands = []
    def command(argv, **kwargs):
        commands.append(argv)
        return CommandResult(json.dumps({"name": "/codeduel-api-1", "networks": {"codeduel_default": {"IPAddress": "172.20.0.2", "Gateway": "172.20.0.1"}}}), "", 0)
    monkeypatch.setattr(tools, "command", command)
    result = tools.docker_inspect("codeduel-api-1")
    assert result["networks"][0]["ip_address"] == "172.20.0.2"
    assert commands[0][-2:] == ["--", "codeduel-api-1"]
    projection = commands[0][4]
    assert ".Config.Env" not in projection
    assert ".Config.Cmd" not in projection
    assert ".State.Health.Log" not in projection


def test_config_rejects_unsafe_scopes():
    with pytest.raises(ValidationError):
        GatewayConfig(containers=["--privileged"])
    with pytest.raises(ValidationError):
        GatewayConfig(write_containers=["unlisted"])
    with pytest.raises(ValidationError):
        GatewayConfig(http_urls=["https://user:pass@codeduel.online"]) # secret-scan: fixture


def test_host_resource_tools_are_structured(config):
    tools = DiagnosticTools(config)
    assert tools.memory_usage()["total_bytes"] > 0
    assert tools.disk_usage()["used_percent"] >= 0
    assert tools.system_uptime()["uptime_seconds"] > 0
    assert isinstance(tools.network_interfaces()["interfaces"], list)
    processes = tools.process_list(3)
    assert len(processes["processes"]) <= 3
    assert "arguments_omitted" in processes
