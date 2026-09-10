"""Explicit scripted regression provider and instrumentation for actual models."""

from __future__ import annotations

from typing import Any

from backend.app.schemas import Decision, HypothesisUpdate

from .scenarios import Scenario


class ScriptedProvider:
    """Known answers exercise the real agent; this is not a model benchmark."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.position = 0
        self.invalid_json_responses = None
        self.raw_model_responses = None

    async def decide_next_action(self, context: dict[str, Any]) -> Decision:
        if self.position < len(self.scenario.plan):
            step = self.scenario.plan[self.position]
            self.position += 1
            return Decision(
                decision_type="TOOL_CALL", tool=step.tool, arguments=step.arguments,
                reason="Scripted orchestration regression: execute the next synthetic diagnostic.",
                hypothesis_updates=[HypothesisUpdate(description=self.scenario.root_cause, confidence=0.3, status="ACTIVE")],
            )
        observations = context.get("observations", [])
        evidence = [item["id"] for item in observations if item["tool_name"] in self.scenario.decisive_tools]
        return Decision(
            decision_type="DIAGNOSIS", root_cause=self.scenario.root_cause, confidence=0.95,
            evidence_observation_ids=evidence, summary=self.scenario.remediation,
            verification_plan=list(self.scenario.verification_plan),
            hypothesis_updates=[HypothesisUpdate(description=self.scenario.root_cause, confidence=0.95, status="CONFIRMED", supporting_observation_ids=evidence)],
        )


class RecordingProvider:
    """Record validated decision attempts without changing the underlying provider."""

    def __init__(self, provider: Any, registry: dict[str, dict[str, Any]]):
        self.provider = provider
        self.registry = registry
        self.decisions: list[dict[str, Any]] = []

    async def decide_next_action(self, context: dict[str, Any]) -> Decision:
        decision = await self.provider.decide_next_action(context)
        self.decisions.append({
            "decision_type": decision.decision_type,
            "tool": decision.tool,
            "arguments": decision.arguments,
            "risk_level": self.registry.get(decision.tool, {}).get("risk_level", "UNKNOWN"),
        })
        return decision
