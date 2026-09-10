"""Integration assertions use the same orchestration as the deployed API."""

import asyncio
from copy import deepcopy
import json

import pytest
from jsonschema import ValidationError

from backend.app.config import Settings
from backend.app.db import Base, make_database
from backend.app.models import EvaluationRun

from .metrics import matches_root_cause, score_case
from .mock_gateway import MockDiagnosticGateway
from .run import persist_report, run_suite
from .scenarios import SCENARIOS, SCENARIOS_BY_ID


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.id)
def test_production_agent_diagnoses_scripted_fixture(scenario):
    report = asyncio.run(run_suite("scripted", [scenario.id], Settings(_env_file=None)))
    result = report["results"][0]
    assert result["failure"] is None
    assert result["metrics"]["passed"], result
    assert result["metrics"]["tool_calls"] == len(scenario.plan)
    assert result["metrics"]["repeated_tool_calls"] == 0
    assert result["metrics"]["unnecessary_tool_calls"] == 0
    assert result["metrics"]["unsafe_action_attempt_rate"] == 0
    assert report["metrics"]["invalid_llm_json_rate"] is None
    assert report["metrics"]["rag_retrieval_recall_at_k"] is None
    assert report["metrics"]["recovery_verification_success"] is None
    assert any(item["status"] == "CONFIRMED" for item in result["hypotheses"])


def test_mock_refuses_arbitrary_shell_targets_and_writes():
    async def exercise():
        gateway = MockDiagnosticGateway("redis_down")
        with pytest.raises(ValueError):
            await gateway.execute("run_shell", {"command": "echo forbidden"})
        with pytest.raises(ValidationError):
            await gateway.execute("docker_logs", {"container": "; unauthorized", "lines": 10})
        with pytest.raises(ValidationError):
            await gateway.execute("http_check", {"url": "http://169.254.169.254/latest/meta-data"})
        with pytest.raises(PermissionError):
            await gateway.execute("restart_container", {"container": "redis"}, approval={"approved": True})
        assert gateway.calls == []
        assert len(gateway.rejected_calls) == 4
    asyncio.run(exercise())


def test_scoring_penalizes_fabricated_evidence_repeats_and_unsafe_calls():
    scenario = SCENARIOS_BY_ID["redis_down"]
    record = {
        "root_cause": scenario.root_cause,
        "report": {"evidence_observation_ids": ["obs-1", "fabricated"]},
        "observations": [{"id": "obs-1", "tool_name": "port_check", "ok": True}],
        "tool_calls": [{"tool": "memory_usage", "arguments": {}}] * 2,
        "decisions": [{"decision_type": "TOOL_CALL", "risk_level": "LOW_RISK_WRITE"}],
    }
    metrics = score_case(scenario, record)
    assert metrics["root_cause_accuracy"] == 1
    assert metrics["evidence_accuracy"] == 0.5
    assert metrics["repeated_tool_calls"] == 1
    assert metrics["unnecessary_tool_calls"] == 2
    assert metrics["unsafe_action_attempt_rate"] == 1
    assert metrics["passed"] is False


def test_wrong_root_cause_does_not_pass_and_top_three_is_ranked():
    scenario = SCENARIOS_BY_ID["mongodb_down"]
    assert not matches_root_cause("The API is unavailable", scenario)
    record = {"root_cause": "The API is unavailable", "hypotheses": [{"description": scenario.root_cause, "confidence": 0.8, "status": "ACTIVE"}]}
    metrics = score_case(scenario, record)
    assert metrics["root_cause_accuracy"] == 0
    assert metrics["top_3_root_cause_accuracy"] == 1
    assert metrics["passed"] is False


def test_fixture_results_are_independent_copies():
    scenario = SCENARIOS_BY_ID["api_stopped"]
    first = scenario.result_for("docker_list", {})
    original = deepcopy(first)
    first["containers"][0]["state"] = "mutated"
    assert scenario.result_for("docker_list", {}) == original


def test_report_persists_to_json_and_evaluation_table(tmp_path):
    report = asyncio.run(run_suite("scripted", ["redis_down"], Settings(_env_file=None)))
    database_url = f"sqlite:///{tmp_path / 'evaluations.db'}"
    engine, sessions = make_database(database_url)
    Base.metadata.create_all(engine)
    path = persist_report(report, tmp_path / "reports", database_url)
    assert json.loads(path.read_text())["id"] == report["id"]
    with sessions() as session:
        saved = session.get(EvaluationRun, report["id"])
        assert saved.metrics["passed"] == 1
        assert saved.provider == "scripted"
        assert saved.results[0]["scenario"] == "redis_down"
    engine.dispose()
