"""Read-only contracts between production gateway policy and synthetic evals.

The evaluation fixtures intentionally model synthetic outages, but their tool
protocol must not drift from the gateway that the production agent calls.  This
module reads the checked-in administrator-owned gateway policy only; it never
opens a socket, invokes a diagnostic, or changes infrastructure.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from diagnostic_gateway.config import GatewayConfig
from diagnostic_gateway.tools import DiagnosticTools


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ContractDiagnostic:
    """One non-executed gateway call used to validate a planned incident path."""

    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProductionIncidentContract:
    """A policy-valid, non-executing acceptance path for a realistic incident."""

    id: str
    symptom: str
    diagnostics: tuple[ContractDiagnostic, ...]
    expected_outcome: str
    capability_status: str | None = None
    capability_gap: str | None = None
    recovery: ContractDiagnostic | None = None
    verification: tuple[ContractDiagnostic, ...] = ()


def load_gateway_config(path: Path | None = None) -> GatewayConfig:
    """Load the repository's production policy without contacting the gateway."""
    source = path or ROOT / "config" / "gateway.json"
    return GatewayConfig.model_validate(json.loads(source.read_text()))


def live_gateway_registry(config: GatewayConfig | None = None) -> dict[str, dict[str, Any]]:
    """Return the same metadata shape exposed by ``GET /tools`` in production."""
    policy = config or load_gateway_config()
    return {entry["name"]: entry for entry in DiagnosticTools(policy).metadata()}


def _enum(registry: dict[str, dict[str, Any]], tool: str, field: str) -> list[Any]:
    try:
        values = registry[tool]["parameters"]["properties"][field]["enum"]
    except KeyError as exc:
        raise ValueError(f"Production gateway metadata lacks {tool}.{field} allowlist") from exc
    if not values:
        raise ValueError(f"Production gateway metadata has an empty {tool}.{field} allowlist")
    return values


def _required_value(registry: dict[str, dict[str, Any]], tool: str, field: str, value: Any) -> Any:
    if value not in _enum(registry, tool, field):
        raise ValueError(f"Production policy no longer permits {tool}({field}={value!r})")
    return value


def schema_interface(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove only administrator-owned target choices before comparing schemas.

    Synthetic fixtures have fictional targets, so target *values* are expected
    to differ. Property names, types, bounds, required fields and extra-field
    denial are protocol and safety semantics and must remain identical.
    """
    result = deepcopy(schema)
    properties = result.get("properties", {})
    for field in ("hostname", "container", "service", "url", "path"):
        if field in properties:
            properties[field].pop("enum", None)
            properties[field].pop("const", None)
    # ``port_check`` uses an anyOf of configured host/port pairs. Its paired
    # target values are policy, while the top-level host/port types are protocol.
    result.pop("anyOf", None)
    return result


def synthetic_registry_from_live(config: GatewayConfig | None = None) -> dict[str, dict[str, Any]]:
    """Build the synthetic mock registry from live schema metadata.

    Only policy allowlists are substituted. This makes a changed real argument
    name, bound, or required field fail the contract test instead of being
    silently hidden by a stale hand-written mock schema.
    """
    registry = deepcopy(live_gateway_registry(config))
    containers = ["codeduel-api", "codeduel-worker", "redis"]
    services = ["docker", "cloudflared", "tailscaled", "ssh", "NetworkManager"]
    hosts = ["127.0.0.1", "localhost", "192.0.2.1", "1.1.1.1", "codeduel.online", "redis"]
    urls = ["https://codeduel.online", "http://127.0.0.1:3001/health"]
    disk_paths = ["/"]

    for tool, metadata in registry.items():
        properties = metadata["parameters"].get("properties", {})
        if "hostname" in properties:
            properties["hostname"]["enum"] = hosts
        if "container" in properties:
            properties["container"]["enum"] = containers
        if "service" in properties:
            properties["service"]["enum"] = services
        if "url" in properties:
            properties["url"]["enum"] = urls
        if "path" in properties:
            properties["path"]["enum"] = disk_paths
        if tool == "port_check":
            metadata["parameters"]["anyOf"] = [
                {"properties": {"host": {"const": host}, "port": {"const": port}}}
                for host, port in (("127.0.0.1", 3001), ("127.0.0.1", 6379), ("127.0.0.1", 27017))
            ]
    return registry


def production_incident_contracts(registry: dict[str, dict[str, Any]]) -> tuple[ProductionIncidentContract, ...]:
    """Return bounded, policy-valid scenario paths without executing them.

    The two model-failure rows intentionally contain no gateway call: a model
    timeout or invalid output must terminate before a tool is selected.  Atlas
    remains an escalation fixture until the deployed policy exposes a bounded
    Atlas diagnostic; when it does, its input is sourced from the live schema.
    """
    api = _required_value(registry, "docker_inspect", "container", "codeduel-api-1")
    worker = _required_value(registry, "docker_inspect", "container", "codeduel-worker-1")
    redis = _required_value(registry, "docker_inspect", "container", "codeduel-redis-1")
    public = _required_value(registry, "http_check", "url", "https://codeduel.online")
    seed = _required_value(registry, "dns_lookup", "hostname", "cluster0.etfzpvb.mongodb.net")
    cloudflared = _required_value(registry, "service_status", "service", "cloudflared")
    docker = _required_value(registry, "service_status", "service", "docker")
    disk_path = _required_value(registry, "disk_usage", "path", "/")

    atlas_diagnostics = [ContractDiagnostic("docker_logs", {"container": api, "lines": 100})]
    atlas_gap: str | None = "mongodb_atlas_connectivity"
    atlas_capability_status: str | None = "MISSING_TOOL"
    atlas_outcome = "ESCALATE"
    if "mongodb_atlas_connectivity" in registry:
        seeds = _enum(registry, "mongodb_atlas_connectivity", "seed")
        atlas_diagnostics.append(ContractDiagnostic("mongodb_atlas_connectivity", {"seed": seeds[0]}))
        atlas_gap = None
        atlas_capability_status = "KNOWN_TOOL"
        atlas_outcome = "DIAGNOSE_OR_ESCALATE_WITH_EVIDENCE"

    return (
        ProductionIncidentContract(
            "website_unavailable", "codeduel.online is down.",
            (ContractDiagnostic("http_check", {"url": public}), ContractDiagnostic("dns_lookup", {"hostname": seed})),
            "DIAGNOSE_OR_ESCALATE_WITH_EVIDENCE",
        ),
        ProductionIncidentContract(
            "api_container_stopped", "The CodeDuel API container is unavailable.",
            (ContractDiagnostic("docker_inspect", {"container": api}),), "DIAGNOSE",
            recovery=ContractDiagnostic("start_container", {"container": api}),
            verification=(ContractDiagnostic("docker_inspect", {"container": api}), ContractDiagnostic("http_check", {"url": public})),
        ),
        ProductionIncidentContract(
            "redis_unavailable", "Submissions are stalled in the CodeDuel queue.",
            (ContractDiagnostic("docker_logs", {"container": worker, "lines": 100}), ContractDiagnostic("docker_inspect", {"container": redis})),
            "DIAGNOSE_OR_ESCALATE_WITH_EVIDENCE",
            recovery=ContractDiagnostic("start_container", {"container": redis}),
            verification=(ContractDiagnostic("docker_inspect", {"container": redis}), ContractDiagnostic("docker_logs", {"container": worker, "lines": 100})),
        ),
        ProductionIncidentContract(
            "mongodb_atlas_connectivity_failure", "The API logs an Atlas server-selection failure.",
            tuple(atlas_diagnostics), atlas_outcome, capability_status=atlas_capability_status, capability_gap=atlas_gap,
        ),
        ProductionIncidentContract(
            "worker_stopped", "The CodeDuel worker is unavailable.",
            (ContractDiagnostic("docker_inspect", {"container": worker}),), "DIAGNOSE",
            recovery=ContractDiagnostic("start_container", {"container": worker}),
            verification=(ContractDiagnostic("docker_inspect", {"container": worker}),),
        ),
        ProductionIncidentContract(
            "docker_daemon_unavailable", "Docker diagnostics cannot reach the host daemon.",
            (ContractDiagnostic("docker_list", {}), ContractDiagnostic("service_status", {"service": docker})), "DIAGNOSE_OR_ESCALATE_WITH_EVIDENCE",
        ),
        ProductionIncidentContract(
            "disk_almost_full", "The host filesystem is almost full.",
            (ContractDiagnostic("disk_usage", {"path": disk_path}),), "DIAGNOSE_OR_ESCALATE_WITH_EVIDENCE",
        ),
        ProductionIncidentContract(
            "cloudflare_tunnel_stopped", "The public site is unavailable while the host remains reachable.",
            (ContractDiagnostic("http_check", {"url": public}), ContractDiagnostic("service_status", {"service": cloudflared})), "DIAGNOSE_OR_ESCALATE_WITH_EVIDENCE",
        ),
        ProductionIncidentContract(
            "dns_failure", "The public hostname does not resolve.",
            (ContractDiagnostic("dns_lookup", {"hostname": seed}),), "DIAGNOSE_OR_ESCALATE_WITH_EVIDENCE",
        ),
        ProductionIncidentContract(
            "unknown_external_failure", "A dependency outside HomeServerAI reports an error.",
            (ContractDiagnostic("docker_logs", {"container": api, "lines": 100}),), "ESCALATE",
            capability_status="MISSING_TOOL", capability_gap="external_dependency_diagnostic",
        ),
        ProductionIncidentContract("model_timeout", "The local model did not respond within its call budget.", (), "MODEL_TIMEOUT"),
        ProductionIncidentContract("invalid_model_json", "The local model emitted invalid structured output twice.", (), "MODEL_INVALID_OUTPUT"),
        ProductionIncidentContract(
            "diagnostic_tool_timeout", "A selected diagnostic exceeded its time budget.",
            (ContractDiagnostic("http_check", {"url": public}),), "TOOL_TIMEOUT",
        ),
        ProductionIncidentContract(
            "recovery_succeeds", "A stopped API can be recovered through an approved bounded action.",
            (ContractDiagnostic("docker_inspect", {"container": api}),), "RESOLVED_AFTER_VERIFICATION",
            recovery=ContractDiagnostic("start_container", {"container": api}),
            verification=(ContractDiagnostic("docker_inspect", {"container": api}), ContractDiagnostic("http_check", {"url": public})),
        ),
        ProductionIncidentContract(
            "recovery_fails_verification", "A recovery action completes but the API remains unhealthy.",
            (ContractDiagnostic("docker_inspect", {"container": api}),), "OPEN_OR_ESCALATED_AFTER_FAILED_VERIFICATION",
            recovery=ContractDiagnostic("start_container", {"container": api}),
            verification=(ContractDiagnostic("docker_inspect", {"container": api}), ContractDiagnostic("http_check", {"url": public})),
        ),
    )
