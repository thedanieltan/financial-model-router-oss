from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fmr import __version__
from fmr.core import route_job, routing_policy
from fmr.core.receipts import validate_execution_result
from fmr.execution import ExecutionOrchestrator, SqliteExecutionLedger
from fmr.provider_service import prepare_handoff
from fmr.registry import ProviderRegistry
from fmr.workflow import builtin_workflow_blueprints, compile_workflow, execute_workflow, workflow_rerun_plan

PROTOCOL_VERSION = "2025-11-25"


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}


TOOLS = (
    _tool("discover_providers", "List discoverable provider and package manifests without loading provider code.", {}, []),
    _tool("list_workflow_blueprints", "List deterministic practitioner workflow blueprints without provider execution.", {}, []),
    _tool("compile_workflow", "Compile a practitioner objective into an ordered, hash-pinned workflow with routed model steps and explicit blockers.", {"request": {"type": "object"}}, ["request"]),
    _tool("plan_workflow_rerun", "Identify exactly which workflow steps are invalidated by changed data or assumptions.", {"plan": {"type": "object"}, "changed_inputs": {"type": "array", "items": {"type": "string"}}}, ["plan", "changed_inputs"]),
    _tool("execute_workflow", "Execute dependency-ready workflow steps through the standard model router and provider lifecycle.", {"plan": {"type": "object"}, "idempotency_key": {"type": "string"}, "ledger_path": {"type": "string"}, "output_directory": {"type": "string"}, "approvals": {"type": "object"}}, ["plan", "idempotency_key", "ledger_path", "output_directory"]),
    _tool("route_job", "Simulate deterministic routing and return candidates, rejection reasons, privacy behavior and missing requirements.", {"job": {"type": "object"}, "policy": {"type": "string"}}, ["job"]),
    _tool("prepare_handoff", "Create a version- and hash-pinned provider handoff; unresolved requirements remain blocked.", {"job": {"type": "object"}, "policy": {"type": "string"}}, ["job"]),
    _tool("execute_job", "Execute an accepted handoff using the standard idempotent lifecycle.", {"handoff": {"type": "object"}, "idempotency_key": {"type": "string"}, "ledger_path": {"type": "string"}, "output_directory": {"type": "string"}}, ["handoff", "idempotency_key", "ledger_path", "output_directory"]),
    _tool("validate_job_result", "Validate an execution result against its immutable handoff and artifact contract.", {"result": {"type": "object"}, "handoff": {"type": "object"}}, ["result", "handoff"]),
    _tool("get_execution_receipt", "Retrieve a completed value-free execution receipt by execution ID.", {"execution_id": {"type": "string"}, "ledger_path": {"type": "string"}}, ["execution_id", "ledger_path"]),
)


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "discover_providers":
        return {"providers": [item.to_dict() for item in ProviderRegistry.builtins().providers()]}
    if name == "list_workflow_blueprints":
        return {"blueprints": list(builtin_workflow_blueprints())}
    if name == "compile_workflow":
        return compile_workflow(arguments["request"])
    if name == "plan_workflow_rerun":
        return workflow_rerun_plan(arguments["plan"], arguments["changed_inputs"])
    if name == "execute_workflow":
        ledger = SqliteExecutionLedger(arguments["ledger_path"])
        orchestrator = ExecutionOrchestrator(ledger=ledger, managed_output_root=arguments["output_directory"])
        return execute_workflow(
            arguments["plan"],
            idempotency_key=arguments["idempotency_key"],
            output_dir=Path(arguments["output_directory"]) / arguments["plan"]["workflow_id"],
            approvals=arguments.get("approvals"),
            orchestrator=orchestrator,
        )
    if name == "route_job":
        return route_job(arguments["job"], policy=routing_policy(arguments.get("policy")))
    if name == "prepare_handoff":
        return prepare_handoff(arguments["job"], policy_name=arguments.get("policy"))
    if name == "execute_job":
        ledger = SqliteExecutionLedger(arguments["ledger_path"])
        handoff = arguments["handoff"]
        return ExecutionOrchestrator(ledger=ledger, managed_output_root=arguments["output_directory"]).execute_request({
            "contract_version": "execution-request.v1", "handoff": handoff,
            "idempotency_key": arguments["idempotency_key"],
            "execution_mode": handoff["execution_configuration"]["mode"], "timeout_seconds": 120,
            "secret_references": [], "output_policy": {"mode": "managed", "overwrite": False, "publish": False},
        })
    if name == "validate_job_result":
        issues = validate_execution_result(arguments["result"], handoff=arguments["handoff"])
        return {"valid": not issues, "issues": list(issues)}
    if name == "get_execution_receipt":
        result = SqliteExecutionLedger(arguments["ledger_path"]).execution_result(arguments["execution_id"])
        if result is None:
            raise ValueError("execution receipt was not found")
        return result
    raise ValueError(f"unknown tool: {name}")


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if message.get("jsonrpc") != "2.0":
        return _error(message.get("id"), -32600, "Invalid Request")
    if "id" not in message:
        return None
    method = message.get("method")
    try:
        if method == "initialize":
            requested = message.get("params", {}).get("protocolVersion")
            version = requested if requested == PROTOCOL_VERSION else PROTOCOL_VERSION
            return _result(message["id"], {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "fmr", "version": __version__}, "instructions": "Deterministic practitioner workflow and financial-model routing. Missing inputs, assumptions and unsupported capabilities are never invented."})
        if method == "ping":
            return _result(message["id"], {})
        if method == "tools/list":
            return _result(message["id"], {"tools": list(TOOLS)})
        if method == "tools/call":
            params = message.get("params")
            if not isinstance(params, dict) or not isinstance(params.get("name"), str) or not isinstance(params.get("arguments", {}), dict):
                return _error(message["id"], -32602, "Invalid params")
            payload = call_tool(params["name"], params.get("arguments", {}))
            return _result(message["id"], {"content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}], "structuredContent": payload, "isError": False})
        return _error(message["id"], -32601, "Method not found")
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        if method == "tools/call":
            payload = {"error": str(exc)}
            return _result(message["id"], {"content": [{"type": "text", "text": json.dumps(payload)}], "structuredContent": payload, "isError": True})
        return _error(message["id"], -32602, str(exc))


def _result(identifier: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def main() -> int:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = handle_message(message)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
