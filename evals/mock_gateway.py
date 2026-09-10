"""In-memory gateway with validated synthetic targets and no OS/network calls."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from jsonschema import validate

from .scenarios import SCENARIOS_BY_ID, Scenario


def schema(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


CONTAINER = {"type": "string", "enum": ["codeduel-api", "codeduel-worker", "redis", "mongodb"]}
SERVICE = {"type": "string", "enum": ["docker", "cloudflared", "tailscaled", "ssh", "NetworkManager"]}
HOST = {"type": "string", "enum": ["127.0.0.1", "localhost", "192.0.2.1", "1.1.1.1", "codeduel.online", "redis", "mongodb"]}
LINES = {"type": "integer", "minimum": 1, "maximum": 500}


PARAMETERS = {
    "dns_lookup": schema({"hostname": {"type": "string", "enum": ["codeduel.online", "redis", "mongodb"]}}, ("hostname",)),
    "ping_host": schema({"host": HOST}, ("host",)),
    "http_check": schema({"url": {"type": "string", "enum": ["https://codeduel.online", "http://127.0.0.1:3001/health"]}}, ("url",)),
    "docker_list": schema({}),
    "docker_inspect": schema({"container": CONTAINER}, ("container",)),
    "docker_logs": schema({"container": CONTAINER, "lines": LINES}, ("container",)),
    "service_status": schema({"service": SERVICE}, ("service",)),
    "journal_logs": schema({"service": SERVICE, "lines": LINES}, ("service",)),
    "network_interfaces": schema({}),
    "route_table": schema({}),
    "memory_usage": schema({}),
    "disk_usage": schema({}),
    "system_uptime": schema({}),
    "process_list": schema({}),
    "port_check": schema({"host": HOST, "port": {"type": "integer", "enum": [3001, 6379, 27017]}}, ("host", "port")),
    "tailscale_status": schema({}),
    "cloudflared_status": schema({}),
    "docker_stats": schema({}),
    "recent_docker_events": schema({}),
    "restart_container": schema({"container": CONTAINER}, ("container",)),
    "start_container": schema({"container": CONTAINER}, ("container",)),
    "restart_service": schema({"service": SERVICE}, ("service",)),
}
WRITE_TOOLS = frozenset({"restart_container", "start_container", "restart_service"})
DESCRIPTIONS = {
    "dns_lookup": "Resolve an allowlisted hostname.",
    "http_check": "Check an allowlisted local or public HTTP health endpoint.",
    "docker_list": "List synthetic containers with current states and health.",
    "docker_inspect": "Inspect one allowlisted container's state, exit status, and health.",
    "docker_logs": "Read bounded logs from one allowlisted container.",
    "service_status": "Read the active state of an allowlisted systemd service.",
    "journal_logs": "Read bounded journal logs for one allowlisted systemd service.",
    "network_interfaces": "Read interface states, addresses, and Wi-Fi rfkill radio block status.",
    "route_table": "Read current host routes and default gateway.",
    "disk_usage": "Read filesystem space and deterministic severity thresholds.",
    "port_check": "Check whether a configured dependency TCP port accepts a connection.",
}


class MockDiagnosticGateway:
    def __init__(self, scenario: Scenario | str):
        self.scenario = SCENARIOS_BY_ID[scenario] if isinstance(scenario, str) else scenario
        self.calls: list[dict[str, Any]] = []
        self.rejected_calls: list[dict[str, Any]] = []

    async def registry(self) -> dict[str, dict[str, Any]]:
        return {
            name: {"name": name, "description": DESCRIPTIONS.get(name, name.replace("_", " ")), "risk_level": "LOW_RISK_WRITE" if name in WRITE_TOOLS else "READ_ONLY", "parameters": deepcopy(parameters)}
            for name, parameters in PARAMETERS.items()
        }

    async def execute(self, tool: str, arguments: dict[str, Any], approval: dict[str, Any] | None = None) -> dict[str, Any]:
        call = {"tool": tool, "arguments": deepcopy(arguments)}
        try:
            if tool not in PARAMETERS:
                raise ValueError("Unknown diagnostic tool")
            if tool in WRITE_TOOLS:
                raise PermissionError("Diagnosis simulations never execute write actions")
            validate(instance=arguments, schema=PARAMETERS[tool])
            result = self.scenario.result_for(tool, arguments)
        except Exception:
            self.rejected_calls.append(call)
            raise
        self.calls.append(call)
        return {"tool": tool, "ok": True, "result": result, "duration_ms": 0.1}


class RedisDownScenario(MockDiagnosticGateway):
    """Convenience fixture for integration tests and the documented demo."""

    def __init__(self):
        super().__init__("redis_down")
