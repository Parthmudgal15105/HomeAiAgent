"""Ground-truth synthetic fixtures, kept separate from production topology.

The scripted tool plans test orchestration deterministically. Only the Ollama
mode measures model diagnosis and tool-selection quality against these fixtures.
No case stops a real service, fills a disk, or changes host networking.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fixture:
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]

    def matches(self, tool: str, arguments: dict[str, Any]) -> bool:
        return self.tool == tool and all(arguments.get(key) == value for key, value in self.arguments.items())


@dataclass(frozen=True)
class Scenario:
    id: str
    symptom: str
    root_cause: str
    root_cause_term_groups: tuple[tuple[str, ...], ...]
    plan: tuple[Diagnostic, ...]
    fixtures: tuple[Fixture, ...]
    relevant_tools: frozenset[str]
    decisive_tools: frozenset[str]
    remediation: str
    verification_plan: tuple[str, ...]

    def result_for(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        for fixture in self.fixtures + HEALTHY_FIXTURES:
            if fixture.matches(tool, arguments):
                return deepcopy(fixture.result)
        raise ValueError(f"Synthetic fixture does not support {tool} with these arguments")


def container(name: str, state: str = "running", **extra: Any) -> dict[str, Any]:
    return {"name": name, "state": state, "status": state, "health": "healthy" if state == "running" else "unhealthy", **extra}


def inspected_container(name: str, state: str = "running", **extra: Any) -> dict[str, Any]:
    """Match the gateway's nested ``docker_inspect`` response shape."""
    running = state == "running"
    return {
        "name": name,
        "image": "synthetic/" + name,
        "state": {
            "status": state,
            "running": running,
            "restarting": False,
            "oom_killed": extra.pop("oom_killed", False),
            "exit_code": extra.pop("exit_code", 0 if running else 1),
            "started_at": "2026-01-01T00:00:00Z" if running else "0001-01-01T00:00:00Z",
            "finished_at": "0001-01-01T00:00:00Z" if running else "2026-01-01T00:00:00Z",
        },
        "restart_count": extra.pop("restart_count", 0),
        "health": extra.pop("health", "healthy" if running else "unhealthy"),
        "ports": {},
        "networks": [],
        **extra,
    }


def disk(path: str, used_percent: float, free_bytes: int) -> dict[str, Any]:
    """Use the production ``disk_usage`` shape rather than a legacy list fixture."""
    total_bytes = 100_000_000_000
    return {
        "path": path,
        "total_bytes": total_bytes,
        "used_bytes": total_bytes - free_bytes,
        "free_bytes": free_bytes,
        "used_percent": used_percent,
        "severity": "critical" if used_percent > 95 else "high" if used_percent >= 90 else "warning" if used_percent >= 80 else "normal",
        "inodes": {"total": 1_000_000, "used": 500_000, "free": 500_000, "used_percent": 50.0, "severity": "normal"},
    }


def atlas_connectivity(seed: str, *, reachable: bool, error_code: str | None = None) -> dict[str, Any]:
    """A credential-free fixture matching the bounded Atlas reachability tool."""
    shard = "ac-abc123-shard-00-00.etfzpvb.mongodb.net"
    probe = {
        "address": "203.0.113.10",
        "port": 27017,
        "tcp_reachable": reachable,
        "tls_reachable": reachable,
        "latency_ms": 12 if reachable else 3000,
        "error_code": None if reachable else error_code or "ATLAS_TLS_UNREACHABLE",
        "error": None if reachable else "Synthetic TLS reachability failure",
    }
    return {
        "seed": seed,
        "port": 27017,
        "reachable": reachable,
        "error_code": None if reachable else error_code or "ATLAS_TLS_UNREACHABLE",
        "error": None if reachable else "No permitted Atlas shard completed a verified TLS handshake",
        "srv": {"resolved": True, "records": [{"hostname": shard, "port": 27017}], "rejected_record_count": 0, "truncated": False, "error_code": None, "error": None},
        "shards": [{"hostname": shard, "port": 27017, "resolved": True, "addresses": ["203.0.113.10"], "probes": [probe], "error_code": None if reachable else probe["error_code"], "error": None if reachable else "Atlas shard did not complete a verified TLS handshake"}],
        "probe_budget_exhausted": False,
    }


CONTAINERS = tuple(container(name) for name in ("codeduel-api", "codeduel-worker", "redis"))
SYNTHETIC_TOPOLOGY: dict[str, Any] = {
    "description": "Synthetic evaluation environment; names and ports are fictional fixtures, not discovered production facts.",
    "services": {
        "codeduel-public": {"url": "https://codeduel.online", "depends_on": ["cloudflared", "codeduel-api"]},
        "codeduel-api": {"container": "codeduel-api", "url": "http://127.0.0.1:3001/health", "depends_on": ["mongodb-atlas", "redis"]},
        "codeduel-worker": {"container": "codeduel-worker", "depends_on": ["redis", "mongodb-atlas", "docker"]},
        "redis": {"container": "redis", "host": "127.0.0.1", "port": 6379},
        "mongodb-atlas": {"description": "Synthetic external Atlas dependency; no local MongoDB container is modeled.", "depends_on": []},
        "cloudflared": {"systemd_service": "cloudflared"},
        "docker": {"systemd_service": "docker"},
    },
}

HEALTHY_FIXTURES = (
    Fixture("dns_lookup", {}, {"resolved": True, "addresses": ["198.51.100.20"]}),
    Fixture("http_check", {}, {"reachable": True, "status_code": 200, "latency_ms": 12, "body_preview": '{"status":"ok"}'}),
    Fixture("docker_list", {}, {"containers": list(CONTAINERS)}),
    *(Fixture("docker_inspect", {"container": item["name"]}, inspected_container(item["name"])) for item in CONTAINERS),
    Fixture("docker_logs", {}, {"lines": ["Service ready; dependency connections established"], "output": "Service ready; dependency connections established"}),
    Fixture("service_status", {}, {"state": "active", "active": True, "sub_state": "running"}),
    Fixture("journal_logs", {}, {"lines": ["Service started successfully"], "output": "Service started successfully"}),
    Fixture("port_check", {}, {"open": True, "reachable": True}),
    Fixture("ping_host", {}, {"hostname": "configured-host", "reachable": True, "packet_loss_percent": 0, "rtt_avg_ms": 1.0, "note": "ICMP may be blocked even when the service works", "error": None}),
    Fixture("disk_usage", {}, disk("/", 42, 58_000_000_000)),
    Fixture("memory_usage", {}, {"used_percent": 40, "available_bytes": 8_000_000_000, "swap_used_bytes": 0}),
    Fixture("network_interfaces", {}, {"interfaces": [{"name": "wlo1", "state": "UP", "addresses": ["192.0.2.10"]}], "rfkill": [{"device": "phy0", "soft_blocked": False, "hard_blocked": False}]}),
    Fixture("route_table", {}, {"routes": [{"destination": "default", "gateway": "192.0.2.1", "interface": "wlo1"}]}),
    Fixture("system_uptime", {}, {"uptime_seconds": 86_400}),
    Fixture("process_list", {}, {"processes": [{"name": "cloudflared", "pid": 321}, {"name": "dockerd", "pid": 322}]}),
    Fixture("tailscale_status", {}, {"state": "Running", "online": True}),
    Fixture("cloudflared_status", {}, {"state": "active", "active": True}),
    Fixture("docker_stats", {}, {"containers": [{"name": item["name"], "cpu_percent": 2, "memory_percent": 4} for item in CONTAINERS]}),
    Fixture("recent_docker_events", {}, {"events": []}),
)


SCENARIOS = (
    Scenario(
        id="api_stopped", symptom="codeduel.online returns 502; investigate why the API is unavailable.",
        root_cause="The codeduel-api container is stopped (exited); its dependencies remain healthy.",
        root_cause_term_groups=(("api", "codeduel-api"), ("stopped", "exited", "not running", "inactive")),
        plan=(Diagnostic("http_check", {"url": "https://codeduel.online"}), Diagnostic("docker_list"), Diagnostic("docker_inspect", {"container": "codeduel-api"})),
        fixtures=(
            Fixture("http_check", {"url": "https://codeduel.online"}, {"reachable": True, "status_code": 502, "body_preview": "Bad gateway"}),
            Fixture("http_check", {"url": "http://127.0.0.1:3001/health"}, {"reachable": False, "error": "Connection refused"}),
            Fixture("docker_list", {}, {"containers": [container("codeduel-api", "exited"), *CONTAINERS[1:]]}),
            Fixture("docker_inspect", {"container": "codeduel-api"}, inspected_container("codeduel-api", "exited", exit_code=0, oom_killed=False)),
            Fixture("docker_logs", {"container": "codeduel-api"}, {"output": "Received SIGTERM; graceful shutdown completed", "lines": ["Received SIGTERM; graceful shutdown completed"]}),
        ),
        relevant_tools=frozenset({"http_check", "docker_list", "docker_inspect", "docker_logs", "service_status", "dns_lookup", "port_check"}),
        decisive_tools=frozenset({"docker_list", "docker_inspect"}),
        remediation="Request approval to start the codeduel-api container.",
        verification_plan=("Check codeduel-api running and healthy", "Check local API and public HTTP endpoint"),
    ),
    Scenario(
        id="redis_down", symptom="CodeDuel submissions are stuck in the BullMQ queue while the site still loads.",
        root_cause="Redis is unavailable, preventing the CodeDuel worker from processing BullMQ jobs.",
        root_cause_term_groups=(("redis",), ("unavailable", "down", "stopped", "refused", "failure", "exited")),
        plan=(Diagnostic("docker_logs", {"container": "codeduel-worker", "lines": 100}), Diagnostic("port_check", {"host": "127.0.0.1", "port": 6379}), Diagnostic("docker_inspect", {"container": "redis"})),
        fixtures=(
            Fixture("docker_logs", {"container": "codeduel-worker"}, {"output": "BullMQ connection error: connect ECONNREFUSED redis:6379; jobs stalled", "lines": ["BullMQ connection error: connect ECONNREFUSED redis:6379; jobs stalled"]}),
            Fixture("port_check", {"port": 6379}, {"open": False, "reachable": False, "error": "Connection refused"}),
            Fixture("docker_list", {}, {"containers": [*CONTAINERS[:2], container("redis", "exited")]}),
            Fixture("docker_inspect", {"container": "redis"}, inspected_container("redis", "exited", exit_code=1)),
            Fixture("docker_logs", {"container": "redis"}, {"output": "Redis process exited; no listener on port 6379", "lines": ["Redis process exited; no listener on port 6379"]}),
        ),
        relevant_tools=frozenset({"docker_logs", "port_check", "docker_inspect", "docker_list", "http_check"}),
        decisive_tools=frozenset({"docker_logs", "port_check", "docker_inspect", "docker_list"}),
        remediation="Request approval to start Redis, then verify the worker reconnects and queue progress resumes.",
        verification_plan=("Check Redis port and container health", "Check worker logs and queue progress", "Check API health"),
    ),
    Scenario(
        id="mongodb_down", symptom="codeduel.online returns 502 and the CodeDuel API repeatedly exits with MongoDB Atlas errors.",
        root_cause="MongoDB Atlas connectivity is unavailable; the external database dependency prevents the CodeDuel API from starting.",
        root_cause_term_groups=(("mongodb", "mongo", "database"), ("atlas", "connectivity", "external"), ("unavailable", "down", "failure", "unreachable")),
        plan=(Diagnostic("docker_logs", {"container": "codeduel-api", "lines": 100}), Diagnostic("mongodb_atlas_connectivity", {"seed": "cluster0.etfzpvb.mongodb.net"})),
        fixtures=(
            Fixture("http_check", {}, {"reachable": False, "status_code": 502, "error": "API upstream unavailable"}),
            Fixture("docker_list", {}, {"containers": [container("codeduel-api", "exited"), CONTAINERS[1], CONTAINERS[2]]}),
            Fixture("docker_inspect", {"container": "codeduel-api"}, inspected_container("codeduel-api", "exited", exit_code=1)),
            Fixture("docker_logs", {"container": "codeduel-api"}, {"container": "codeduel-api", "lines": ["MongoServerSelectionError: MongoDB Atlas server selection failed; terminating API"], "truncated": False}),
            Fixture("mongodb_atlas_connectivity", {"seed": "cluster0.etfzpvb.mongodb.net"}, atlas_connectivity("cluster0.etfzpvb.mongodb.net", reachable=False)),
        ),
        relevant_tools=frozenset({"docker_logs", "mongodb_atlas_connectivity", "docker_inspect", "docker_list", "http_check", "service_status", "dns_lookup"}),
        decisive_tools=frozenset({"docker_logs", "mongodb_atlas_connectivity"}),
        remediation="Escalate the external Atlas connectivity failure; do not restart a nonexistent local MongoDB service.",
        verification_plan=("Check configured Atlas reachability", "Check API container and local endpoint", "Check public endpoint"),
    ),
    Scenario(
        id="cloudflared_stopped", symptom="codeduel.online is unavailable externally, but the local CodeDuel API responds.",
        root_cause="The cloudflared service is inactive, so the Cloudflare Tunnel cannot reach the healthy local application.",
        root_cause_term_groups=(("cloudflared", "cloudflare", "tunnel"), ("inactive", "stopped", "down", "not running", "unavailable")),
        plan=(Diagnostic("http_check", {"url": "http://127.0.0.1:3001/health"}), Diagnostic("service_status", {"service": "cloudflared"}), Diagnostic("journal_logs", {"service": "cloudflared", "lines": 100})),
        fixtures=(
            Fixture("http_check", {"url": "https://codeduel.online"}, {"reachable": True, "status_code": 530, "body_preview": "Cloudflare Tunnel error 1033"}),
            Fixture("service_status", {"service": "cloudflared"}, {"state": "inactive", "active": False, "sub_state": "dead"}),
            Fixture("cloudflared_status", {}, {"state": "inactive", "active": False}),
            Fixture("journal_logs", {"service": "cloudflared"}, {"output": "cloudflared.service: Deactivated successfully; tunnel connections closed", "lines": ["cloudflared.service: Deactivated successfully; tunnel connections closed"]}),
        ),
        relevant_tools=frozenset({"http_check", "service_status", "journal_logs", "cloudflared_status", "dns_lookup", "process_list"}),
        decisive_tools=frozenset({"service_status", "journal_logs", "cloudflared_status"}),
        remediation="Request approval to restart the cloudflared service.",
        verification_plan=("Check cloudflared active", "Check local and public endpoints"),
    ),
    Scenario(
        id="docker_daemon_down", symptom="CodeDuel containers and the judge are unavailable; Docker commands fail.",
        root_cause="The Docker daemon is inactive, making the CodeDuel container workloads unavailable.",
        root_cause_term_groups=(("docker",), ("daemon", "service"), ("inactive", "down", "stopped", "unavailable", "not running")),
        plan=(Diagnostic("docker_list"), Diagnostic("service_status", {"service": "docker"}), Diagnostic("journal_logs", {"service": "docker", "lines": 100})),
        fixtures=(
            Fixture("docker_list", {}, {"error": "Cannot connect to Docker daemon at unix:///var/run/docker.sock", "containers": []}),
            Fixture("docker_inspect", {}, {"error": "Cannot connect to Docker daemon"}),
            Fixture("docker_logs", {}, {"error": "Cannot connect to Docker daemon"}),
            Fixture("service_status", {"service": "docker"}, {"state": "inactive", "active": False, "sub_state": "dead"}),
            Fixture("journal_logs", {"service": "docker"}, {"output": "docker.service: Stopped Docker Application Container Engine", "lines": ["docker.service: Stopped Docker Application Container Engine"]}),
            Fixture("http_check", {}, {"reachable": False, "error": "Connection refused"}),
        ),
        relevant_tools=frozenset({"docker_list", "service_status", "journal_logs", "process_list", "disk_usage", "memory_usage"}),
        decisive_tools=frozenset({"docker_list", "service_status", "journal_logs"}),
        remediation="Request approval for a Docker service restart after assessing impact to all existing workloads.",
        verification_plan=("Check Docker service active", "Check expected containers running", "Check CodeDuel endpoints"),
    ),
    Scenario(
        id="disk_full", symptom="CodeDuel intermittently fails to save data and logs report no space left on device.",
        root_cause="The root filesystem is critically full (99.5% used), causing application and database writes to fail.",
        root_cause_term_groups=(("disk", "filesystem", "storage"), ("full", "space", "99.5", "capacity", "exhaust")),
        plan=(Diagnostic("disk_usage"), Diagnostic("docker_logs", {"container": "codeduel-api", "lines": 100})),
        fixtures=(
            Fixture("disk_usage", {}, disk("/", 99.5, 50_000_000)),
            Fixture("docker_logs", {"container": "codeduel-api"}, {"output": "ENOSPC: no space left on device while writing /var/app/data", "lines": ["ENOSPC: no space left on device while writing /var/app/data"]}),
            Fixture("docker_logs", {"container": "codeduel-worker"}, {"output": "Queue persistence failed: No space left on device", "lines": ["Queue persistence failed: No space left on device"]}),
        ),
        relevant_tools=frozenset({"disk_usage", "docker_logs", "journal_logs", "docker_list", "docker_inspect"}),
        decisive_tools=frozenset({"disk_usage", "docker_logs"}),
        remediation="Review disk consumers and retention with the operator; do not delete data or prune Docker automatically.",
        verification_plan=("Check free disk space after approved cleanup", "Verify application and database writes"),
    ),
    Scenario(
        id="host_network_down", symptom="The host cannot reach its gateway or the internet; CodeDuel and Tailscale are unreachable.",
        root_cause="Host networking is unavailable: the primary network interface is down and no default route exists.",
        root_cause_term_groups=(("network", "interface", "route", "connectivity"), ("down", "unavailable", "missing", "no default", "disconnect")),
        plan=(Diagnostic("network_interfaces"), Diagnostic("route_table"), Diagnostic("ping_host", {"hostname": "192.0.2.1"})),
        fixtures=(
            Fixture("network_interfaces", {}, {"interfaces": [{"name": "wlo1", "state": "DOWN", "addresses": []}], "rfkill": [{"device": "phy0", "soft_blocked": False, "hard_blocked": False}]}),
            Fixture("route_table", {}, {"routes": [], "default_route": None}),
            Fixture("ping_host", {}, {"hostname": "192.0.2.1", "reachable": False, "packet_loss_percent": 100, "rtt_avg_ms": None, "note": "ICMP may be blocked even when the service works", "error": "Network is unreachable"}),
            Fixture("dns_lookup", {}, {"resolved": False, "addresses": [], "error": "Temporary failure in name resolution"}),
            Fixture("http_check", {"url": "https://codeduel.online"}, {"reachable": False, "error": "Network is unreachable"}),
            Fixture("tailscale_status", {}, {"state": "NoState", "online": False, "error": "Network unavailable"}),
        ),
        relevant_tools=frozenset({"network_interfaces", "route_table", "ping_host", "tailscale_status", "dns_lookup", "http_check", "journal_logs"}),
        decisive_tools=frozenset({"network_interfaces", "route_table", "ping_host"}),
        remediation="Operator should restore host network connectivity using a local console; avoid remote network changes that risk losing SSH.",
        verification_plan=("Check interface address and default route", "Check gateway and internet reachability", "Check Tailscale and CodeDuel"),
    ),
    Scenario(
        id="wifi_rfkill", symptom="Wi-Fi suddenly stopped; Tailscale and CodeDuel are unreachable. Investigate without changing networking.",
        root_cause="The Wi-Fi radio is soft blocked by rfkill (airplane mode), leaving the wireless interface down.",
        root_cause_term_groups=(("rfkill", "rf-kill", "airplane", "radio", "wireless", "wi-fi", "wifi"), ("blocked", "disabled", "airplane", "kill")),
        plan=(Diagnostic("network_interfaces"), Diagnostic("journal_logs", {"service": "NetworkManager", "lines": 100}), Diagnostic("route_table")),
        fixtures=(
            Fixture("network_interfaces", {}, {"interfaces": [{"name": "wlo1", "state": "DOWN", "addresses": []}], "rfkill": [{"device": "phy0", "soft_blocked": True, "hard_blocked": False}]}),
            Fixture("journal_logs", {}, {"output": "NetworkManager: Wi-Fi radio disabled by rfkill; wlo1 unavailable; operation not possible due to RF-kill", "lines": ["NetworkManager: Wi-Fi radio disabled by rfkill; wlo1 unavailable; operation not possible due to RF-kill"]}),
            Fixture("route_table", {}, {"routes": [], "default_route": None}),
            Fixture("ping_host", {}, {"hostname": "192.0.2.1", "reachable": False, "packet_loss_percent": 100, "rtt_avg_ms": None, "note": "ICMP may be blocked even when the service works", "error": "Network is unreachable"}),
            Fixture("tailscale_status", {}, {"state": "NoState", "online": False}),
            Fixture("dns_lookup", {}, {"resolved": False, "addresses": [], "error": "Network is unreachable"}),
        ),
        relevant_tools=frozenset({"network_interfaces", "journal_logs", "route_table", "ping_host", "tailscale_status", "service_status"}),
        decisive_tools=frozenset({"network_interfaces", "journal_logs"}),
        remediation="Ask the operator to disable airplane mode or unblock Wi-Fi at the local console; do not toggle host networking automatically.",
        verification_plan=("Check rfkill state clear", "Check wireless address and route", "Check gateway, Tailscale, and public service"),
    ),
)

SCENARIOS_BY_ID = {scenario.id: scenario for scenario in SCENARIOS}
