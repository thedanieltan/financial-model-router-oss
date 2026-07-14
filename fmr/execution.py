from __future__ import annotations

import hashlib
import json
import multiprocessing
import queue
import shutil
from pathlib import Path
from typing import Any

from fmr.core.handoffs import digest
from fmr.core.receipts import validate_execution_result


def _native_worker(handoff: dict[str, Any], output_dir: str, result_queue: Any) -> None:
    try:
        from fmr.providers.native_xlsx import execute_budget_forecast_handoff
        result_queue.put(("ok", execute_budget_forecast_handoff(handoff, output_dir)))
    except Exception as exc:  # provider process boundary
        result_queue.put(("error", type(exc).__name__, str(exc)))


def _execute_native_with_timeout(handoff: dict[str, Any], output_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(target=_native_worker, args=(handoff, str(output_dir), result_queue))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError(f"provider execution timed out after {timeout_seconds} seconds")
    try:
        message = result_queue.get_nowait()
    except queue.Empty as exc:
        raise RuntimeError(f"provider process exited without a receipt (exit code {process.exitcode})") from exc
    if message[0] == "error":
        if message[1] in {"ValueError", "JSONDecodeError"}:
            raise ValueError(message[2])
        raise RuntimeError(message[2])
    return message[1]


class ExecutionOrchestrator:
    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}

    def execute(self, handoff: dict[str, Any], *, idempotency_key: str, output_dir: str | Path = ".", timeout_seconds: int = 120, secret_references: tuple[str, ...] = ()) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not isinstance(timeout_seconds, int) or timeout_seconds < 1:
            raise ValueError("timeout_seconds must be a positive integer")
        if handoff.get("contract_version") != "provider-handoff.v1":
            raise ValueError("provider-handoff.v1 is required")
        cache_key = hashlib.sha256((handoff.get("handoff_sha256", "") + "\0" + idempotency_key).encode()).hexdigest()
        if cache_key in self._results:
            return self._results[cache_key]
        if handoff.get("status") != "ready":
            result = self._result(handoff, cache_key, "blocked", [], "blocked", list(handoff.get("unresolved_requirements", [])), False, {}, "invalid_input")
            self._results[cache_key] = result
            return result
        provider_id = handoff.get("provider", {}).get("provider_id")
        try:
            if provider_id == "native-xlsx":
                provider_receipt = _execute_native_with_timeout(handoff, Path(output_dir) / cache_key[:16], timeout_seconds)
                outputs = provider_receipt["output_artifacts"]
                validation = provider_receipt["validation"]["status"]
            elif provider_id == "reference-handoff":
                provider_receipt = {"provider_receipt_version": "reference-handoff-receipt.v1", "status": "completed", "handoff_sha256": handoff["handoff_sha256"]}
                outputs = [{"kind": "external_provider_handoff", "reference": f"handoff:{handoff['handoff_sha256']}"}]
                validation = "passed"
            else:
                raise ValueError(f"provider executor is not installed: {provider_id}")
            result = self._result(handoff, cache_key, "completed", outputs, validation, [], False, provider_receipt, None)
        except (ValueError, json.JSONDecodeError) as exc:
            result = self._result(handoff, cache_key, "failed", [], "failed", [str(exc)], False, {}, "invalid_input")
        except (OSError, RuntimeError) as exc:
            result = self._result(handoff, cache_key, "failed", [], "failed", [str(exc)], True, {}, "provider_failure")
        issues = validate_execution_result(result)
        if issues:
            raise ValueError("invalid execution result: " + "; ".join(issues))
        self._results[cache_key] = result
        return result

    @staticmethod
    def _result(handoff: dict[str, Any], cache_key: str, state: str, outputs: list[dict[str, Any]], validation_status: str, blockers: list[str], retry: bool, provider_receipt: dict[str, Any], error_category: str | None) -> dict[str, Any]:
        output_hashes = sorted(item["sha256"] for item in outputs if isinstance(item, dict) and isinstance(item.get("sha256"), str))
        provisional = {
            "contract_version": "execution-result.v1",
            "handoff_reference": {"handoff_id": handoff.get("handoff_id"), "sha256": handoff.get("handoff_sha256")},
            "provider": handoff.get("provider"), "package": handoff.get("package"),
            "state": state, "output_artifact_references": outputs,
            "validation_status": validation_status, "errors_and_blockers": blockers,
            "error_category": error_category,
            "retry_eligible": retry, "output_hashes": output_hashes,
            "provider_receipt": {"sha256": digest(provider_receipt), "version": provider_receipt.get("provider_receipt_version")} if provider_receipt else None,
            "idempotency_key_sha256": hashlib.sha256(cache_key.encode()).hexdigest(),
        }
        return {**provisional, "execution_id": f"fmrx_{digest(provisional)[:24]}"}


DEFAULT_ORCHESTRATOR = ExecutionOrchestrator()
