"""In-memory gateway with validated synthetic targets and no OS/network calls.

The mock retains fictional fixtures but derives its JSON Schema protocol from
the checked-in production gateway metadata.  Synthetic target enums are the
only intentional difference, preventing a stale mock from masking a real
tool-argument change.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator

from .production_contract import synthetic_registry_from_live
from .scenarios import SCENARIOS_BY_ID, Scenario

WRITE_TOOLS = frozenset({"restart_container", "start_container", "stop_container", "restart_service", "start_service", "stop_service"})


class MockDiagnosticGateway:
    def __init__(self, scenario: Scenario | str):
        self.scenario = SCENARIOS_BY_ID[scenario] if isinstance(scenario, str) else scenario
        self.calls: list[dict[str, Any]] = []
        self.rejected_calls: list[dict[str, Any]] = []
        # Metadata construction is pure; it reads only config/gateway.json.
        self._registry = synthetic_registry_from_live()

    async def registry(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._registry)

    async def execute(self, tool: str, arguments: dict[str, Any], approval: dict[str, Any] | None = None) -> dict[str, Any]:
        call = {"tool": tool, "arguments": deepcopy(arguments)}
        try:
            metadata = self._registry.get(tool)
            if metadata is None:
                raise ValueError("Unknown diagnostic tool")
            if tool in WRITE_TOOLS:
                raise PermissionError("Diagnosis simulations never execute write actions")
            Draft202012Validator(metadata["parameters"]).validate(arguments)
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
