"""Run the production Agent against synthetic infrastructure, then save metrics.

python -m evals.run
python -m evals.run --provider ollama --model qwen2.5:3b
LLM_PROVIDER=gemini GEMINI_API_KEY=... python -m evals.run --provider gemini --model gemini-3.8-flash
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.db import Base, make_database
from backend.app.llm import create_llm_provider
from backend.app.models import EvaluationRun, Incident, AuditEvent
from sqlalchemy import select

from .metrics import aggregate, score_case
from .mock_gateway import MockDiagnosticGateway
from .providers import RecordingProvider, ScriptedProvider
from .scenarios import SCENARIOS, SCENARIOS_BY_ID, SYNTHETIC_TOPOLOGY, Scenario


async def evaluate_scenario(scenario: Scenario, provider_name: str, settings: Settings) -> dict[str, Any]:
    from backend.app.agent import Agent

    engine, sessions = make_database("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    gateway = MockDiagnosticGateway(scenario)
    provider = ScriptedProvider(scenario) if provider_name == "scripted" else create_llm_provider(settings.model_copy(update={'llm_provider': provider_name}))
    recording = RecordingProvider(provider, await gateway.registry())
    with sessions() as session:
        incident = Incident(title=scenario.symptom[:300], description=scenario.symptom, service="codeduel")
        session.add(incident)
        session.commit()
        incident_id = incident.id

    started = time.monotonic()
    failure = None
    try:
        agent = Agent(settings=settings, sessions=sessions, gateway=gateway, llm=recording, rag=None)
        await agent.investigate(incident_id)
    except Exception as exc:
        # A failed case remains in the report and does not silently vanish from accuracy.
        failure = f"{type(exc).__name__}: {str(exc)[:1000]}"
    latency = round(time.monotonic() - started, 4)
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        if incident.status == 'FAILED':
            failure = failure or incident.agent_state.get('error') or incident.summary or 'Agent failed'
        record: dict[str, Any] = {
            "scenario": scenario.id,
            "symptom": scenario.symptom,
            "expected_root_cause": scenario.root_cause,
            "status": incident.status,
            "root_cause": incident.root_cause,
            "confidence": incident.root_cause_confidence,
            "report": incident.report,
            "failure": failure,
            "latency_seconds": latency,
            "tool_calls": gateway.calls,
            "rejected_gateway_calls": gateway.rejected_calls,
            "decisions": recording.decisions,
            "observations": [
                {"id": item.id, "tool_name": item.tool_name, "arguments": item.tool_arguments, "ok": item.raw_result.get("ok", True), "result": item.normalized_result, "duration_ms": item.duration_ms}
                for item in incident.observations
            ],
            "hypotheses": [
                {"description": item.description, "confidence": item.confidence, "status": item.status, "supporting_observation_ids": item.supporting_observation_ids}
                for item in incident.hypotheses
            ],
            "invalid_json_responses": getattr(provider, "metrics", {}).get("invalid_json"),
            "raw_model_responses": getattr(provider, "metrics", {}).get("requests"),
            "model_latencies_ms": getattr(provider, "metrics", {}).get("latencies_ms", []),
            "llm_metrics": getattr(provider, "metrics", {}),
            "decision_rejections": [item.payload for item in session.scalars(select(AuditEvent).where(AuditEvent.incident_id == incident_id, AuditEvent.event_type == "decision_rejected"))],
        }
    engine.dispose()
    record["metrics"] = score_case(scenario, record)
    return record


async def run_suite(provider_name: str = "scripted", scenario_ids: list[str] | None = None, settings: Settings | None = None, progress_file: Path | None = None) -> dict[str, Any]:
    if provider_name not in {"scripted", "ollama", "gemini"}:
        raise ValueError("Provider must be scripted, ollama or gemini")
    selected = [SCENARIOS_BY_ID[item] for item in scenario_ids] if scenario_ids else list(SCENARIOS)
    settings = settings or Settings(_env_file=None)
    with tempfile.TemporaryDirectory(prefix="homeai-evaluation-") as directory:
        topology = Path(directory) / "topology.json"
        topology.write_text(json.dumps(SYNTHETIC_TOPOLOGY))
        isolated = settings.model_copy(update={"database_url": "sqlite:///:memory:", "topology_path": str(topology), "rag_enabled": False, "enable_write_actions": False})
        results = []
        for scenario in selected:
            result = await evaluate_scenario(scenario, provider_name, isolated)
            results.append(result)
            if progress_file:
                progress_file.parent.mkdir(parents=True, exist_ok=True)
                progress_file.write_text(json.dumps({'complete': False, 'provider': provider_name, 'model': model_name(provider_name, settings), 'completed_cases': len(results), 'planned_cases': len(selected), 'metrics': aggregate(results), 'results': results}, indent=2))
            print(json.dumps({"progress": scenario.id, "model": model_name(provider_name, settings) or "scripted", "metrics": result["metrics"], "failure": result["failure"]}), flush=True)
    metrics = aggregate(results)
    if provider_name == "scripted":
        metrics["unmeasured"]["invalid_llm_json_rate"] = "No model is called in scripted mode; JSON reliability is not measured."
    return {
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider_name,
        "model": model_name(provider_name, settings),
        "evaluation_type": "scripted orchestration and safety regression" if provider_name == "scripted" else f"{provider_name} model diagnosis benchmark on synthetic infrastructure",
        "fixture_sha256": hashlib.sha256(Path(__file__).with_name("scenarios.py").read_bytes()).hexdigest(),
        "synthetic_only": True,
        "production_agent": "backend.app.agent.Agent",
        "settings": evaluation_settings(provider_name, settings),
        "metrics": metrics,
        "results": results,
}


def model_name(provider_name: str, settings: Settings) -> str | None:
    if provider_name == 'ollama':
        return settings.ollama_model
    if provider_name == 'gemini':
        return settings.gemini_model
    return None


def evaluation_settings(provider_name: str, settings: Settings) -> dict[str, Any]:
    names = ['agent_max_steps', 'agent_llm_timeout_seconds', 'agent_max_runtime_seconds', 'agent_context_chars']
    if provider_name == 'ollama':
        names += ['ollama_num_ctx', 'ollama_num_predict', 'ollama_num_thread']
    elif provider_name == 'gemini':
        names += ['gemini_thinking_level', 'gemini_max_output_tokens']
    return {key: getattr(settings, key) for key in names}


def persist_report(report: dict[str, Any], output_dir: Path, database_url: str | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{report['created_at'][:10]}-{report['provider']}-{report['id']}.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if database_url:
        engine, sessions = make_database(database_url)
        # Deliberately do not create/migrate production tables here: deployment owns schema.
        try:
            with sessions() as session:
                session.add(EvaluationRun(id=report["id"], provider=report["provider"], metrics=report["metrics"], results=report["results"]))
                session.commit()
        finally:
            engine.dispose()
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["scripted", "ollama", "gemini"], default="scripted")
    parser.add_argument("--scenario", action="append", choices=list(SCENARIOS_BY_ID), help="Select case(s); default runs all eight")
    parser.add_argument("--model", help="Override the selected provider's model")
    parser.add_argument("--ollama-base-url", help="Override local Ollama URL")
    parser.add_argument("--max-steps", type=int, help="Override the bounded agent step limit")
    parser.add_argument("--llm-timeout", type=int, help="Per-call LLM timeout in seconds")
    parser.add_argument("--runtime-limit", type=int, help="Total per-incident runtime budget in seconds")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results")
    parser.add_argument("--persist-db", action="store_true", help="Also add EvaluationRun to DATABASE_URL; tables must already exist")
    args = parser.parse_args()
    model_setting = 'ollama_model' if args.provider == 'ollama' else 'gemini_model'
    overrides = {
        key: value for key, value in {
            model_setting: args.model,
            "ollama_base_url": args.ollama_base_url,
            "agent_max_steps": args.max_steps,
            "agent_llm_timeout_seconds": args.llm_timeout,
            "agent_max_runtime_seconds": args.runtime_limit,
        }.items() if value is not None
    }
    settings = Settings(**overrides)
    selected_model = model_name(args.provider, settings) or 'scripted'
    progress = args.output_dir / ('progress-' + args.provider + '-' + selected_model.replace(':', '-').replace('/', '-') + '.json')
    report = asyncio.run(run_suite(args.provider, args.scenario, settings, progress))
    path = persist_report(report, args.output_dir, settings.database_url if args.persist_db else None)
    progress.write_text(json.dumps({'complete': True, 'report_path': str(path), 'metrics': report['metrics']}, indent=2))
    print(json.dumps({"evaluation_type": report["evaluation_type"], "model": report["model"], "metrics": report["metrics"], "report_path": str(path.resolve())}, indent=2))
    return 0 if report["metrics"]["passed"] == report["metrics"]["scenario_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
