"""Live, isolated approval/recovery smoke test. Never run against CodeDuel.

Run inside the configured backend container after the operator creates a STOPPED
aiops-demo container and explicitly scopes gateway writes to that container only:

    AIOPS_DEMO_CONTAINER=aiops-demo python /app/scripts/approval_smoke.py

The production Agent persists an evidence-backed deterministic diagnosis and
proposal. The production IncidentService approves, dispatches, verifies, and
indexes the result. This is an approval integration test, not an LLM benchmark.
The script never creates, stops, removes, or restarts a container.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

# Also support invocation by absolute script path from another working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from backend.app.agent import Agent, asdict
from backend.app.config import Settings
from backend.app.db import make_database
from backend.app.gateway import DiagnosticGateway, WRITE_TOOLS, validate_tool
from backend.app.models import Action, Incident
from backend.app.rag import LocalRAG
from backend.app.schemas import Decision, Remediation
from backend.app.service import IncidentService


DEMO_CONTAINER = "aiops-demo"


class SmokeCheckFailed(RuntimeError):
    """An authored, non-secret-bearing validation failure safe to report."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeCheckFailed(message)


def snapshot(sessions: Any, incident_id: str, action_id: str) -> dict[str, Any]:
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        action = session.get(Action, action_id)
        return {
            "incident_status": incident.status,
            "phase": incident.agent_state.get("phase"),
            "approval_status": action.approval_status,
            "executed_at": action.executed_at.isoformat() if action.executed_at else None,
            "verification_status": action.verification_status,
            "action_ok": action.result.get("ok"),
            "observation_count": len(incident.observations),
            "verification": incident.agent_state.get("verification", []),
            "indexed_for_history": incident.agent_state.get("indexed_for_history", False),
        }


def save_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as output:
        os.chmod(temporary, 0o600)
        json.dump(report, output, indent=2, ensure_ascii=False)
        output.write("\n")
    temporary.replace(path)


async def exercise(report: dict[str, Any], output: Path) -> None:
    report["phase"] = "preflight"
    require(os.getenv("AIOPS_DEMO_CONTAINER") == DEMO_CONTAINER, "Explicit AIOPS_DEMO_CONTAINER=aiops-demo is required")
    service_name = os.getenv("AIOPS_DEMO_SERVICE", "demo")
    require(service_name in {"demo", DEMO_CONTAINER}, "Demo service must be named demo or aiops-demo")
    require(bool(os.getenv("DATABASE_URL")), "Explicit backend DATABASE_URL is required")
    settings = Settings()
    require(settings.enable_write_actions, "Backend write policy must explicitly enable the isolated demonstration")
    require(settings.rag_enabled, "Local RAG must be enabled for the full lifecycle smoke test")
    require(bool(settings.gateway_token) and bool(settings.gateway_approval_secret), "Configured gateway authentication and approval signing are required")
    for name, url in (("gateway", settings.gateway_url), ("Ollama", settings.ollama_base_url), ("Qdrant", settings.qdrant_url)):
        parsed = urlsplit(url)
        require(parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}, f"{name} must use the local server loopback endpoint")
    profile = settings.topology().get("services", {}).get(service_name)
    require(isinstance(profile, dict) and bool(profile.get("health_checks")), "A configured demo topology profile with health checks is required")

    gateway = DiagnosticGateway(settings)
    registry = await gateway.registry()
    require("start_container" in registry, "Gateway must explicitly expose start_container for the demo")
    for name, metadata in registry.items():
        if metadata.get("risk_level") == "READ_ONLY":
            continue
        require(name in {"start_container", "restart_container"}, "Gateway exposes a write outside the isolated demo container scope")
        require(metadata.get("risk_level") == "LOW_RISK_WRITE", "Gateway write risk must be LOW_RISK_WRITE")
        allowed = metadata.get("parameters", {}).get("properties", {}).get("container", {}).get("enum")
        require(allowed == [DEMO_CONTAINER], "Gateway write allowlist must contain only aiops-demo")
    validate_tool(registry, "docker_inspect", {"container": DEMO_CONTAINER})
    validate_tool(registry, "start_container", {"container": DEMO_CONTAINER}, allow_write=True)

    engine, sessions = make_database(settings.database_url)
    require(engine.dialect.name == "postgresql", "Live lifecycle test requires the configured PostgreSQL database")
    try:
        rag = LocalRAG(settings)
        # No reasoning call occurs: the deterministic diagnosis cites live state.
        agent = Agent(settings, sessions, gateway, llm=None, rag=rag)
        service = IncidentService(settings, sessions, agent, gateway, rag)
        checks = service.verification_checks(service_name)
        require(any(
            check.tool == "docker_inspect" and check.arguments == {"container": DEMO_CONTAINER}
            and check.expect.get("state.running") is True and check.expect.get("health") == "healthy"
            for check in checks
        ), "Demo verification must require aiops-demo running and healthy")
        for check in checks:
            require(check.tool not in WRITE_TOOLS, "Demo recovery checks must be read-only")
            require(check.arguments.get("container", DEMO_CONTAINER) == DEMO_CONTAINER, "Demo verification must not select production containers")
            validate_tool(registry, check.tool, check.arguments)

        initial = await gateway.execute("docker_inspect", {"container": DEMO_CONTAINER})
        state = initial.get("result", {}).get("state", {})
        require(initial.get("ok") is True, "Live demo inspection must succeed")
        require(initial.get("result", {}).get("name", "").lstrip("/") == DEMO_CONTAINER, "Inspected container identity differs from aiops-demo")
        require(state.get("running") is False and state.get("status") in {"created", "exited"}, "aiops-demo must already be stopped; the test will not stop it")
        report.update({"service": service_name, "initial_state": {"running": state.get("running"), "status": state.get("status")}})
        save_report(output, report)

        report["phase"] = "unsigned_gateway_denial"
        async with httpx.AsyncClient(timeout=settings.agent_tool_timeout_seconds, trust_env=False) as client:
            denied = await client.post(
                settings.gateway_url.rstrip("/") + "/tools/start_container",
                headers={"Authorization": f"Bearer {settings.gateway_token}"},
                json={"container": DEMO_CONTAINER},
            )
        report["unsigned_gateway_status"] = denied.status_code
        require(denied.status_code == 403, "Gateway did not reject a demo write missing signed approval")
        unchanged = await gateway.execute("docker_inspect", {"container": DEMO_CONTAINER})
        require(unchanged.get("ok") is True and unchanged.get("result", {}).get("state", {}).get("running") is False, "Demo changed state before persisted approval")
        report["unsigned_gateway_rejected"] = True

        with sessions() as session:
            incident = Incident(
                title="Isolated approval smoke: aiops-demo is stopped",
                description="Operator-authorized integration demonstration for aiops-demo only. Deterministic diagnosis from live read-only container state; no production workload is a remediation target.",
                service=service_name, severity="LOW",
            )
            session.add(incident)
            session.commit()
            incident_id = incident.id
        report.update({"incident_id": incident_id, "phase": "persist_diagnosis"})
        observation_id = agent.record_observation(incident_id, "docker_inspect", {"container": DEMO_CONTAINER}, initial, "Live isolated demo container is stopped.")
        decision = Decision(
            decision_type="DIAGNOSIS",
            root_cause="The isolated aiops-demo container is stopped, so its demonstration HTTP server is unavailable.",
            confidence=0.95, evidence_observation_ids=[observation_id],
            summary="Start only the operator-created aiops-demo container after this exact action is approved; verify configured health checks before resolving.",
            remediation=[Remediation(tool="start_container", arguments={"container": DEMO_CONTAINER}, reason="The operator authorized this isolated demo start to test persisted approval and recovery verification.")],
            verification_plan=["Require the configured aiops-demo running and healthy checks to pass."],
        )
        agent.save_diagnosis(incident_id, decision, registry)
        with sessions() as session:
            incident = session.get(Incident, incident_id)
            require(incident.status == "WAITING_FOR_APPROVAL", "Diagnosis did not create a persisted pending action")
            require(len(incident.actions) == 1, "Demo must have exactly one proposed action")
            proposed = incident.actions[0]
            require(proposed.tool_name == "start_container" and proposed.arguments == {"container": DEMO_CONTAINER}, "Proposed action differs from the isolated demo start")
            require(proposed.approval_status == "PENDING" and proposed.executed_at is None, "Proposed action was executed before approval")
            action_id = proposed.id
        report.update({"action_id": action_id, "evidence_observation_id": observation_id, "pending": snapshot(sessions, incident_id, action_id), "phase": "approve_and_verify"})
        save_report(output, report)

        # This is the same persisted approval path called by POST /api/actions/{id}/approve.
        await service.approve(action_id)
        after = snapshot(sessions, incident_id, action_id)
        report["after_approval"] = after
        require(after["approval_status"] == "APPROVED" and bool(after["executed_at"]), "Action approval/dispatch was not persisted")
        require(after["action_ok"] is True, "Demo start failed or outcome is uncertain; the test will not retry the write")

        if after["incident_status"] != "RESOLVED":
            report["phase"] = "wait_for_demo_health"
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                result = await asyncio.wait_for(gateway.execute("docker_inspect", {"container": DEMO_CONTAINER}), timeout=max(0.1, deadline - time.monotonic()))
                agent.record_observation(incident_id, "docker_inspect", {"container": DEMO_CONTAINER}, result, "Bounded read-only smoke-test wait for demo startup health.", phase="VERIFICATION")
                current = result.get("result", {})
                if result.get("ok") is True and current.get("state", {}).get("running") is True and current.get("health") == "healthy":
                    await service.verify(incident_id, action_id)
                    break
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(min(2, remaining))
        final = snapshot(sessions, incident_id, action_id)
        report["final"] = final
        require(final["incident_status"] == "RESOLVED" and final["verification_status"] == "PASSED", "Configured demo health verification did not resolve the incident")
        require(bool(final["verification"]) and all(item.get("passed") is True for item in final["verification"]), "Persisted recovery checks do not all pass")
        save_report(output, report)

        report["phase"] = "replay_denial"
        try:
            await service.approve(action_id)
        except ValueError:
            report["backend_replay_rejected"] = True
        else:
            raise SmokeCheckFailed("Backend accepted approval replay")
        with sessions() as session:
            stored_approval = asdict(session.get(Action, action_id))
        try:
            # Negative replay test uses the production signer and exact stored action.
            # Even a valid signature must not consume the same action ID twice.
            await gateway.execute("start_container", {"container": DEMO_CONTAINER}, approval=stored_approval)
        except httpx.HTTPStatusError as exc:
            report["gateway_replay_status"] = exc.response.status_code
            require(exc.response.status_code == 403, "Gateway replay failed for an unexpected reason")
            report["gateway_replay_rejected"] = True
        else:
            raise SmokeCheckFailed("Gateway accepted the consumed action ID again")
        require(snapshot(sessions, incident_id, action_id)["executed_at"] == final["executed_at"], "Replay altered the persisted execution timestamp")

        report["phase"] = "verify_local_rag"
        require(final["indexed_for_history"] is True, "Resolved demo incident was not indexed by the production RAG path")
        document_id = f"incident:{incident_id}"
        point_id = str(uuid5(NAMESPACE_URL, document_id))
        async with rag.client() as client:
            response = await client.get(f"/collections/{rag.collection}/points/{point_id}")
            response.raise_for_status()
            point = response.json().get("result", {})
        payload = point.get("payload", {})
        require(payload.get("document_id") == document_id and payload.get("incident_id") == incident_id and payload.get("kind") == "incident", "Qdrant does not contain the exact resolved incident document")
        report["rag"] = {"indexed_for_history": True, "persisted_point_verified": True, "collection": rag.collection, "point_id": point_id}
        try:
            hits = await rag.retrieve("Isolated aiops-demo container stopped; approved start restored its HTTP server and verified recovery.")
            matches = [item for item in hits if item.get("incident_id") == incident_id]
            report["rag"].update({"retrieval_completed": True, "retrieved_count": len(hits), "incident_in_top_k": bool(matches), "matching_scores": [item.get("score") for item in matches]})
        except Exception as exc:
            # Durable upsert is already proved; retrieval ranking/availability is separate evidence.
            report["rag"].update({"retrieval_completed": False, "retrieval_error_type": type(exc).__name__})
        report.update({"phase": "complete", "passed": True})
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Persist JSON result; default is a unique file under /tmp")
    parser.add_argument("--timeout-seconds", type=int, default=420, help="Whole-test time limit, including local embedding work (60–900)")
    args = parser.parse_args()
    require(60 <= args.timeout_seconds <= 900, "Whole-test timeout must be between 60 and 900 seconds")
    report_id = str(uuid4())
    output = args.output or Path("/tmp") / f"aiops-approval-smoke-{report_id}.json"
    report: dict[str, Any] = {
        "id": report_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "test_type": "live isolated persisted approval, gateway enforcement, recovery and local RAG integration",
        "diagnosis_source": "deterministic diagnosis citing a live stopped-container observation; not an LLM diagnosis benchmark",
        "container": DEMO_CONTAINER, "passed": False, "phase": "initializing",
    }
    logging.basicConfig(level=logging.WARNING)
    started = time.monotonic()
    try:
        # Confirm the report destination is usable before any gateway write attempt.
        save_report(output, report)
        async def bounded() -> None:
            await asyncio.wait_for(exercise(report, output), timeout=args.timeout_seconds)
        asyncio.run(bounded())
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc) if isinstance(exc, SmokeCheckFailed) else "Test stopped; inspect the recorded phase and application audit events. No write is retried automatically."
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        try:
            save_report(output, report)
        except OSError:
            report["report_write_failed"] = True
        summary = {key: report[key] for key in ("passed", "phase", "incident_id", "action_id", "unsigned_gateway_rejected", "backend_replay_rejected", "gateway_replay_rejected", "rag", "error_type", "error", "elapsed_seconds") if key in report}
        summary["final"] = report.get("final")
        summary["report_path"] = str(output)
        print(json.dumps(summary, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
