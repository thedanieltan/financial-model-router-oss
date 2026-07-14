from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fmr.core.handoffs import digest
from fmr.core.jobs import ModelJob
from fmr.core.receipts import validate_artifact_contract, validate_execution_result, validate_provider_handoff
from fmr.provider_plugins import PluginCatalog
from fmr.registry import ProviderRegistry


@dataclass(frozen=True)
class OutputPolicy:
    mode: str
    directory: str | None
    overwrite: bool
    publish: bool

    @classmethod
    def from_mapping(cls, value: Any) -> "OutputPolicy":
        if not isinstance(value, dict):
            raise ValueError("output_policy must be an object")
        if set(value) - {"mode", "directory", "overwrite", "publish"}:
            raise ValueError("output_policy contains unsupported fields")
        mode = value.get("mode")
        if mode not in {"managed", "specified_directory"}:
            raise ValueError("output_policy.mode must be managed or specified_directory")
        directory = value.get("directory")
        if mode == "specified_directory" and (not isinstance(directory, str) or not directory.strip()):
            raise ValueError("specified_directory output policy requires directory")
        if mode == "managed" and directory is not None:
            raise ValueError("managed output policy must not declare directory")
        overwrite = value.get("overwrite", False)
        publish = value.get("publish", False)
        if not isinstance(overwrite, bool) or not isinstance(publish, bool):
            raise ValueError("output_policy overwrite and publish must be booleans")
        if overwrite:
            raise ValueError("output overwrite is not supported")
        if publish:
            raise ValueError("output publication is not supported")
        return cls(mode, directory, overwrite, publish)

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "directory": self.directory, "overwrite": self.overwrite, "publish": self.publish}


@dataclass(frozen=True)
class ExecutionRequest:
    handoff: dict[str, Any]
    idempotency_key: str
    execution_mode: str
    timeout_seconds: int
    secret_references: tuple[str, ...]
    output_policy: OutputPolicy
    contract_version: str = "execution-request.v1"

    @classmethod
    def from_mapping(cls, value: Any) -> "ExecutionRequest":
        if not isinstance(value, dict) or value.get("contract_version") != "execution-request.v1":
            raise ValueError("execution-request.v1 is required")
        allowed = {"contract_version", "handoff", "idempotency_key", "execution_mode", "timeout_seconds", "secret_references", "output_policy"}
        if set(value) - allowed:
            raise ValueError("execution request contains unsupported fields")
        key = value.get("idempotency_key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency_key is required")
        mode = value.get("execution_mode")
        if mode not in {"local", "remote", "handoff_only"}:
            raise ValueError("execution_mode is not supported")
        timeout = value.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1 or timeout > 86_400:
            raise ValueError("timeout_seconds must be between 1 and 86400")
        references = value.get("secret_references")
        if not isinstance(references, list) or not all(isinstance(item, str) and item.strip() for item in references) or len(set(references)) != len(references):
            raise ValueError("secret_references must be a unique array of non-empty strings")
        handoff = value.get("handoff")
        if not isinstance(handoff, dict):
            raise ValueError("handoff must be an object")
        return cls(handoff, key.strip(), mode, timeout, tuple(references), OutputPolicy.from_mapping(value.get("output_policy")))


class SqliteExecutionLedger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path(tempfile.gettempdir()) / "fmr-execution-ledger-v1.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS executions_v2 "
                "(cache_key TEXT PRIMARY KEY, state TEXT NOT NULL, claimed_at REAL NOT NULL, "
                "result_json TEXT, updated_at REAL, detail_code TEXT)"
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(executions_v2)")}
            if "updated_at" not in columns:
                connection.execute("ALTER TABLE executions_v2 ADD COLUMN updated_at REAL")
            if "detail_code" not in columns:
                connection.execute("ALTER TABLE executions_v2 ADD COLUMN detail_code TEXT")
            connection.execute("UPDATE executions_v2 SET updated_at = claimed_at WHERE updated_at IS NULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS execution_events_v1 "
                "(event_id INTEGER PRIMARY KEY AUTOINCREMENT, cache_key TEXT NOT NULL, "
                "state TEXT NOT NULL, occurred_at REAL NOT NULL, detail_code TEXT NOT NULL)"
            )

    def claim(self, cache_key: str, *, stale_after_seconds: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state, claimed_at, result_json FROM executions_v2 WHERE cache_key = ?", (cache_key,)).fetchone()
            if row is None:
                now = time.time()
                connection.execute(
                    "INSERT INTO executions_v2(cache_key, state, claimed_at, result_json, updated_at, detail_code) "
                    "VALUES (?, 'running', ?, NULL, ?, 'claimed')",
                    (cache_key, now, now),
                )
                self._event(connection, cache_key, "running", "claimed", now)
                return None
            if row[0] == "completed" and row[2]:
                return json.loads(row[2])
            if row[0] == "running" and time.time() - float(row[1]) > stale_after_seconds:
                now = time.time()
                connection.execute(
                    "UPDATE executions_v2 SET claimed_at = ?, updated_at = ?, detail_code = 'stale_reclaimed' "
                    "WHERE cache_key = ?",
                    (now, now, cache_key),
                )
                self._event(connection, cache_key, "running", "stale_reclaimed", now)
                return None
            if row[0] in {"abandoned", "pruned"}:
                now = time.time()
                connection.execute(
                    "UPDATE executions_v2 SET state = 'running', claimed_at = ?, result_json = NULL, "
                    "updated_at = ?, detail_code = 'reclaimed' WHERE cache_key = ?",
                    (now, now, cache_key),
                )
                self._event(connection, cache_key, "running", "reclaimed", now)
                return None
            raise RuntimeError("an execution with this handoff and idempotency key is already in progress")

    def complete(self, cache_key: str, result: dict[str, Any]) -> None:
        with self._connect() as connection:
            now = time.time()
            connection.execute(
                "UPDATE executions_v2 SET state = 'completed', result_json = ?, updated_at = ?, "
                "detail_code = 'completed' WHERE cache_key = ?",
                (json.dumps(result, sort_keys=True), now, cache_key),
            )
            self._event(connection, cache_key, "completed", "completed", now)

    def abandon(self, cache_key: str) -> None:
        with self._connect() as connection:
            now = time.time()
            connection.execute(
                "UPDATE executions_v2 SET state = 'abandoned', result_json = NULL, updated_at = ?, "
                "detail_code = 'abandoned' WHERE cache_key = ?",
                (now, cache_key),
            )
            self._event(connection, cache_key, "abandoned", "abandoned", now)

    def recover_stale(self, *, stale_after_seconds: int, now: float | None = None) -> tuple[str, ...]:
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")
        cutoff = (time.time() if now is None else now) - stale_after_seconds
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            keys = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT cache_key FROM executions_v2 WHERE state = 'running' AND claimed_at < ? ORDER BY cache_key",
                    (cutoff,),
                )
            )
            occurred_at = time.time() if now is None else now
            for cache_key in keys:
                connection.execute(
                    "UPDATE executions_v2 SET state = 'abandoned', result_json = NULL, updated_at = ?, "
                    "detail_code = 'stale_recovered' WHERE cache_key = ?",
                    (occurred_at, cache_key),
                )
                self._event(connection, cache_key, "abandoned", "stale_recovered", occurred_at)
            return keys

    def operational_status(self, *, stale_after_seconds: int = 300) -> dict[str, Any]:
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")
        with self._connect() as connection:
            counts = {row[0]: row[1] for row in connection.execute(
                "SELECT state, COUNT(*) FROM executions_v2 GROUP BY state ORDER BY state"
            )}
            stale = connection.execute(
                "SELECT COUNT(*) FROM executions_v2 WHERE state = 'running' AND claimed_at < ?",
                (time.time() - stale_after_seconds,),
            ).fetchone()[0]
            events = connection.execute("SELECT COUNT(*) FROM execution_events_v1").fetchone()[0]
        return {
            "contract_version": "execution-operations-status.v1",
            "ledger": "sqlite",
            "states": counts,
            "stale_running": stale,
            "event_count": events,
            "database_size_bytes": self.path.stat().st_size if self.path.exists() else 0,
        }

    def backup(self, destination: str | Path) -> dict[str, Any]:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError("backup destination already exists")
        with self._connect() as source, sqlite3.connect(target) as backup:
            source.backup(backup)
        payload = target.read_bytes()
        return {
            "contract_version": "execution-ledger-backup.v1",
            "path": str(target),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }

    def completed_before(self, cutoff: float) -> tuple[tuple[str, dict[str, Any]], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT cache_key, result_json FROM executions_v2 "
                "WHERE state = 'completed' AND updated_at < ? AND result_json IS NOT NULL ORDER BY cache_key",
                (cutoff,),
            )
            return tuple((row[0], json.loads(row[1])) for row in rows)

    def execution_result(self, execution_id: str) -> dict[str, Any] | None:
        if not isinstance(execution_id, str) or not execution_id:
            raise ValueError("execution_id is required")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT result_json FROM executions_v2 WHERE state = 'completed' AND result_json IS NOT NULL ORDER BY cache_key"
            )
            for row in rows:
                result = json.loads(row[0])
                if result.get("execution_id") == execution_id:
                    return result
        return None

    def mark_pruned(self, cache_key: str) -> None:
        with self._connect() as connection:
            now = time.time()
            connection.execute(
                "UPDATE executions_v2 SET state = 'pruned', result_json = NULL, updated_at = ?, "
                "detail_code = 'retention_pruned' WHERE cache_key = ? AND state = 'completed'",
                (now, cache_key),
            )
            self._event(connection, cache_key, "pruned", "retention_pruned", now)

    @staticmethod
    def _event(connection: sqlite3.Connection, cache_key: str, state: str, detail_code: str, occurred_at: float) -> None:
        connection.execute(
            "INSERT INTO execution_events_v1(cache_key, state, occurred_at, detail_code) VALUES (?, ?, ?, ?)",
            (cache_key, state, occurred_at, detail_code),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection


class EnvironmentSecretResolver:
    """Resolve only explicitly allowlisted environment references."""

    def __init__(self, allowed_references: tuple[str, ...], *, prefix: str = "") -> None:
        if len(set(allowed_references)) != len(allowed_references) or not all(
            isinstance(item, str) and item.strip() for item in allowed_references
        ):
            raise ValueError("allowed secret references must be unique non-empty strings")
        self.allowed_references = frozenset(allowed_references)
        self.prefix = prefix

    def __call__(self, reference: str) -> str:
        if reference not in self.allowed_references:
            raise ValueError("secret reference is not allowlisted")
        value = os.environ.get(self.prefix + reference)
        if value is None or value == "":
            raise ValueError("secret reference is unavailable")
        return value


class ManagedArtifactRetention:
    """Prune completed managed outputs without following paths outside the managed root."""

    def __init__(self, ledger: SqliteExecutionLedger, managed_output_root: str | Path) -> None:
        self.ledger = ledger
        self.root = Path(managed_output_root).resolve()

    def prune(self, *, older_than_seconds: int, dry_run: bool = True, now: float | None = None) -> dict[str, Any]:
        if older_than_seconds < 1:
            raise ValueError("older_than_seconds must be positive")
        current = time.time() if now is None else now
        candidates = self.ledger.completed_before(current - older_than_seconds)
        selected: list[dict[str, Any]] = []
        for cache_key, result in candidates:
            paths = [Path(item["path"]).resolve() for item in result.get("output_artifact_references", [])]
            if not paths or any(self.root not in path.parents for path in paths):
                continue
            directories = {path.parent for path in paths}
            if len(directories) != 1:
                continue
            directory = directories.pop()
            if directory == self.root:
                continue
            selected.append({"cache_key_sha256": hashlib.sha256(cache_key.encode()).hexdigest(), "artifact_count": len(paths)})
            if not dry_run:
                shutil.rmtree(directory)
                self.ledger.mark_pruned(cache_key)
        return {
            "contract_version": "artifact-retention-result.v1",
            "dry_run": dry_run,
            "candidate_count": len(candidates),
            "pruned_count": 0 if dry_run else len(selected),
            "selected": selected,
        }


def _execute_with_timeout(entry_point: str, handoff: dict[str, Any], output_dir: Path, secrets: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    request = json.dumps({"entry_point": entry_point, "handoff": handoff, "output_dir": str(output_dir), "secrets": secrets})
    try:
        process = subprocess.run(
            [sys.executable, "-m", "fmr.provider_runner"], input=request,
            text=True, capture_output=True, timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError(f"provider execution timed out after {timeout_seconds} seconds") from exc
    try:
        message = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"provider process returned an invalid response (exit code {process.returncode})") from exc
    if process.returncode != 0 or message.get("status") != "ok":
        error_type = message.get("error_type")
        error = _redact_secret_values(str(message.get("error", "provider process failed")), secrets)
        if error_type in {"ValueError", "JSONDecodeError", "KeyError"}:
            raise ValueError(error)
        raise RuntimeError(error)
    receipt = message.get("receipt")
    if not isinstance(receipt, dict):
        raise RuntimeError("provider process returned no receipt")
    serialized_receipt = json.dumps(receipt, sort_keys=True)
    if any(secret and secret in serialized_receipt for secret in secrets.values()):
        raise RuntimeError("provider receipt contains resolved secret material")
    return receipt


def _redact_secret_values(message: str, secrets: dict[str, str]) -> str:
    redacted = message
    for secret in secrets.values():
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


class ExecutionOrchestrator:
    def __init__(
        self,
        *,
        registry: ProviderRegistry | None = None,
        ledger: SqliteExecutionLedger | None = None,
        managed_output_root: str | Path | None = None,
        secret_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self.registry = registry or ProviderRegistry.builtins()
        self.ledger = ledger or SqliteExecutionLedger()
        self.managed_output_root = Path(managed_output_root or Path(tempfile.gettempdir()) / "fmr-managed-outputs")
        self.secret_resolver = secret_resolver

    def execute_request(self, request: ExecutionRequest | dict[str, Any]) -> dict[str, Any]:
        value = ExecutionRequest.from_mapping(request) if isinstance(request, dict) else request
        handoff = value.handoff
        issues = validate_provider_handoff(handoff, registry=self.registry)
        if issues:
            raise ValueError("invalid provider handoff: " + "; ".join(issues))
        registered = self.registry.package(handoff["provider"]["provider_id"], handoff["package"]["package_id"])
        if handoff["status"] == "ready":
            adapter = PluginCatalog.installed().adapter(registered.package.adapter_entry_point)
            expected_payload = adapter.compile(ModelJob.from_mapping(handoff["job"]), registered)
            if expected_payload != handoff.get("provider_payload"):
                raise ValueError("provider payload does not match trusted adapter compilation")
        if value.execution_mode != registered.provider.execution_mode:
            raise ValueError("requested execution_mode does not match selected provider mode")
        if set(value.secret_references) != set(registered.provider.secret_requirements):
            raise ValueError("secret references do not match provider manifest requirements")
        if value.secret_references and self.secret_resolver is None:
            raise ValueError("a secret resolver is required for declared secret references")
        secrets = {name: self.secret_resolver(name) for name in value.secret_references} if self.secret_resolver else {}
        output_root = self.managed_output_root if value.output_policy.mode == "managed" else Path(value.output_policy.directory or "")
        cache_key = hashlib.sha256((handoff["handoff_sha256"] + "\0" + value.idempotency_key).encode()).hexdigest()
        cached = self.ledger.claim(cache_key, stale_after_seconds=value.timeout_seconds + 30)
        if cached is not None:
            cached_issues = validate_execution_result(cached, handoff=handoff, registry=self.registry, verify_artifacts=True)
            if cached_issues:
                self.ledger.abandon(cache_key)
                raise RuntimeError("cached execution result is no longer valid: " + "; ".join(cached_issues))
            return cached
        provider_output_dir: Path | None = None
        try:
            idempotency_key_sha256 = hashlib.sha256(value.idempotency_key.encode()).hexdigest()
            if handoff["status"] != "ready":
                result = self._result(handoff, idempotency_key_sha256, "blocked", [], "blocked", list(handoff["unresolved_requirements"]), False, None, "invalid_input")
            else:
                provider_output_dir = output_root / cache_key[:16]
                try:
                    provider_receipt = _execute_with_timeout(registered.provider.executor_entry_point, handoff, provider_output_dir, secrets, value.timeout_seconds)
                    outputs = provider_receipt.get("output_artifacts", [])
                    artifact_issues = validate_artifact_contract(outputs, handoff["expected_outputs"], verify_files=True)
                    validation = provider_receipt.get("validation", {}).get("status")
                    if artifact_issues or validation != "passed":
                        details = [*artifact_issues]
                        if validation != "passed":
                            details.append(f"validation_status:{validation}")
                        raise RuntimeError("provider output contract failed: " + "; ".join(details))
                    result = self._result(handoff, idempotency_key_sha256, "completed", outputs, "passed", [], False, provider_receipt, None)
                except ValueError as exc:
                    shutil.rmtree(provider_output_dir, ignore_errors=True)
                    result = self._result(handoff, idempotency_key_sha256, "failed", [], "failed", [str(exc)], False, None, "invalid_input")
                except (OSError, RuntimeError) as exc:
                    shutil.rmtree(provider_output_dir, ignore_errors=True)
                    result = self._result(handoff, idempotency_key_sha256, "failed", [], "failed", [str(exc)], True, None, "provider_failure")
            result_issues = validate_execution_result(result, handoff=handoff, registry=self.registry, verify_artifacts=True)
            if result_issues:
                raise ValueError("invalid execution result: " + "; ".join(result_issues))
            self.ledger.complete(cache_key, result)
            return result
        except Exception:
            if provider_output_dir is not None:
                shutil.rmtree(provider_output_dir, ignore_errors=True)
            self.ledger.abandon(cache_key)
            raise

    def execute(
        self,
        handoff: dict[str, Any],
        *,
        idempotency_key: str,
        output_dir: str | Path = ".",
        timeout_seconds: int = 120,
        secret_references: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        mode = handoff.get("execution_configuration", {}).get("mode")
        return self.execute_request({
            "contract_version": "execution-request.v1", "handoff": handoff,
            "idempotency_key": idempotency_key, "execution_mode": mode,
            "timeout_seconds": timeout_seconds, "secret_references": list(secret_references),
            "output_policy": {"mode": "specified_directory", "directory": str(output_dir), "overwrite": False, "publish": False},
        })

    @staticmethod
    def _result(handoff: dict[str, Any], idempotency_key_sha256: str, state: str, outputs: list[dict[str, Any]], validation_status: str, blockers: list[str], retry: bool, provider_receipt: dict[str, Any] | None, error_category: str | None) -> dict[str, Any]:
        output_hashes = sorted(item["sha256"] for item in outputs if isinstance(item, dict) and isinstance(item.get("sha256"), str))
        receipt = None
        if provider_receipt:
            receipt = {"sha256": digest(provider_receipt), "version": provider_receipt.get("provider_receipt_version"), "payload": provider_receipt}
        provisional = {
            "contract_version": "execution-result.v1",
            "handoff_reference": {"handoff_id": handoff.get("handoff_id"), "sha256": handoff.get("handoff_sha256")},
            "provider": handoff.get("provider"), "package": handoff.get("package"),
            "state": state, "output_artifact_references": outputs,
            "validation_status": validation_status, "errors_and_blockers": blockers,
            "error_category": error_category, "retry_eligible": retry, "output_hashes": output_hashes,
            "provider_receipt": receipt,
            "idempotency_key_sha256": idempotency_key_sha256,
        }
        return {**provisional, "execution_id": f"fmrx_{digest(provisional)[:24]}"}


DEFAULT_ORCHESTRATOR = ExecutionOrchestrator()
