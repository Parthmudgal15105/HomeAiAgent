"""Keep synthetic evaluations compatible with the deployed gateway contract."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.app.gateway import READ_TOOLS, WRITE_TOOLS, validate_tool
from jsonschema import Draft202012Validator

from .mock_gateway import MockDiagnosticGateway
from .production_contract import (
    ROOT,
    live_gateway_registry,
    load_gateway_config,
    production_incident_contracts,
    schema_interface,
)
from .scenarios import HEALTHY_FIXTURES, SCENARIOS


def _has_path(value, path: str) -> bool:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def test_synthetic_mock_keeps_the_live_gateway_protocol_surface():
    """Fictional fixture targets may differ; tool grammar and safety cannot."""
    live = live_gateway_registry()
    mock = asyncio.run(MockDiagnosticGateway("api_stopped").registry())

    assert mock.keys() == live.keys()
    for name, live_metadata in live.items():
        synthetic_metadata = mock[name]
        assert synthetic_metadata["risk_level"] == live_metadata["risk_level"], name
        assert schema_interface(synthetic_metadata["parameters"]) == schema_interface(live_metadata["parameters"]), name


def test_real_topology_health_checks_validate_against_the_gateway_and_backend_policy():
    """A topology edit cannot introduce a tool/argument the deployed agent rejects."""
    registry = live_gateway_registry()
    topology = json.loads((ROOT / "config" / "topology.json").read_text())
    for service, profile in topology["services"].items():
        for check in profile.get("health_checks", []):
            tool, arguments = check["tool"], check["arguments"]
            assert tool in registry, f"{service}: {tool} is absent from gateway metadata"
            assert tool in READ_TOOLS, f"{service}: {tool} is absent from the backend read-only allowlist"
            Draft202012Validator(registry[tool]["parameters"]).validate(arguments)
            validate_tool(registry, tool, arguments)


def test_gateway_metadata_exactly_reflects_checked_in_write_policy():
    """No metadata action target can silently widen beyond config/gateway.json."""
    config = load_gateway_config()
    registry = live_gateway_registry(config)
    # Current production policy permits only explicitly approved manual writes;
    # its gateway must not advertise an autonomous target as a side effect.
    assert config.writes_enabled is True
    assert config.autonomous_actions == {}
    expected_tools = {
        action
        for actions in config.allowed_actions.values()
        for action in actions
    }
    actual_tools = {name for name, metadata in registry.items() if metadata["risk_level"] != "READ_ONLY"}
    assert actual_tools == expected_tools

    for tool in sorted(actual_tools):
        metadata = registry[tool]
        target_field = "container" if tool.endswith("_container") else "service"
        expected_targets = sorted(target for target, actions in config.allowed_actions.items() if tool in actions)
        assert sorted(metadata["parameters"]["properties"][target_field]["enum"]) == expected_targets
        assert sorted(metadata.get("autonomous_targets", [])) == sorted(
            target for target, actions in config.autonomous_actions.items() if tool in actions
        )


def test_production_incident_scaffold_uses_only_permitted_tools_and_targets():
    """Requested incident coverage is policy-checked before any live run exists."""
    registry = live_gateway_registry()
    contracts = production_incident_contracts(registry)
    required = {
        "website_unavailable", "api_container_stopped", "redis_unavailable",
        "mongodb_atlas_connectivity_failure", "worker_stopped", "docker_daemon_unavailable",
        "disk_almost_full", "cloudflare_tunnel_stopped", "dns_failure",
        "unknown_external_failure", "model_timeout", "invalid_model_json",
        "diagnostic_tool_timeout", "recovery_succeeds", "recovery_fails_verification",
    }
    assert {case.id for case in contracts} == required

    for case in contracts:
        for call in (*case.diagnostics, *case.verification):
            assert call.tool in READ_TOOLS, f"{case.id}: {call.tool} is not a backend read-only tool"
            assert call.tool in registry, f"{case.id}: {call.tool} is not exposed by production gateway"
            Draft202012Validator(registry[call.tool]["parameters"]).validate(call.arguments)
            validate_tool(registry, call.tool, call.arguments)
        if case.recovery:
            assert case.recovery.tool in WRITE_TOOLS, f"{case.id}: recovery is not a bounded write action"
            assert case.recovery.tool in registry, f"{case.id}: recovery action is absent from production gateway"
            Draft202012Validator(registry[case.recovery.tool]["parameters"]).validate(case.recovery.arguments)
            validate_tool(registry, case.recovery.tool, case.recovery.arguments, allow_write=True)
        if case.capability_gap:
            assert case.expected_outcome == "ESCALATE", case.id
            assert case.capability_status == "MISSING_TOOL", case.id
            assert not case.recovery, case.id
        if case.expected_outcome in {"MODEL_TIMEOUT", "MODEL_INVALID_OUTPUT"}:
            assert not case.diagnostics and not case.recovery, case.id

    atlas = next(case for case in contracts if case.id == "mongodb_atlas_connectivity_failure")
    assert atlas.capability_status == "KNOWN_TOOL"
    assert atlas.capability_gap is None
    assert any(call.tool == "mongodb_atlas_connectivity" for call in atlas.diagnostics)


def test_atlas_incident_scaffold_escalates_with_a_capability_gap_when_the_tool_is_absent():
    """Keep the out-of-scope path covered even when a deployment lacks Atlas support."""
    registry = live_gateway_registry()
    registry.pop("mongodb_atlas_connectivity", None)
    atlas = next(case for case in production_incident_contracts(registry) if case.id == "mongodb_atlas_connectivity_failure")
    assert atlas.expected_outcome == "ESCALATE"
    assert atlas.capability_status == "MISSING_TOOL"
    assert atlas.capability_gap == "mongodb_atlas_connectivity"
    assert all(call.tool != "mongodb_atlas_connectivity" for call in atlas.diagnostics)


def test_synthetic_fixture_results_preserve_critical_live_gateway_result_shapes():
    """Avoid training/evaluating against legacy flat Docker or disk responses."""
    fixtures = [*HEALTHY_FIXTURES, *(fixture for scenario in SCENARIOS for fixture in scenario.fixtures)]
    required_paths = {
        "docker_inspect": ("name", "state.status", "state.running", "restart_count", "health", "networks"),
        "disk_usage": ("path", "used_percent", "severity", "inodes.used_percent", "inodes.severity"),
        "mongodb_atlas_connectivity": ("seed", "port", "reachable", "error_code", "srv.resolved", "srv.records", "shards", "probe_budget_exhausted"),
    }
    matched = {tool: 0 for tool in required_paths}
    for fixture in fixtures:
        # A legacy synthetic Docker-handler error does not claim to be an
        # inspect result. Atlas reachability intentionally returns structured
        # error fields, so it remains subject to its result contract.
        if fixture.tool not in required_paths or (fixture.tool != "mongodb_atlas_connectivity" and fixture.result.get("error")):
            continue
        matched[fixture.tool] += 1
        for path in required_paths[fixture.tool]:
            assert _has_path(fixture.result, path), f"{fixture.tool} fixture is missing {path}"
    assert all(matched.values()), "Each critical gateway result contract needs at least one fixture"
