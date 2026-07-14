from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from fmr.execution import EnvironmentSecretResolver, ManagedArtifactRetention, SqliteExecutionLedger, _execute_with_timeout
from fmr.provider_dispatch import run_provider_command


class ExecutionOperationsTests(unittest.TestCase):
    def test_existing_ledger_is_migrated_without_losing_completed_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE executions_v2 (cache_key TEXT PRIMARY KEY, state TEXT NOT NULL, claimed_at REAL NOT NULL, result_json TEXT)"
                )
                connection.execute(
                    "INSERT INTO executions_v2 VALUES ('existing', 'completed', 1, ?)",
                    (json.dumps({"state": "completed"}),),
                )
            ledger = SqliteExecutionLedger(path)
            self.assertEqual(ledger.claim("existing", stale_after_seconds=30), {"state": "completed"})
            with sqlite3.connect(path) as connection:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(executions_v2)")}
            self.assertTrue({"updated_at", "detail_code"}.issubset(columns))

    def test_stale_recovery_and_status_are_value_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.sqlite3"
            ledger = SqliteExecutionLedger(path)
            self.assertIsNone(ledger.claim("sensitive-cache-key", stale_after_seconds=30))
            with self.assertRaisesRegex(RuntimeError, "already in progress"):
                SqliteExecutionLedger(path).claim("sensitive-cache-key", stale_after_seconds=30)
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE executions_v2 SET claimed_at = 1, updated_at = 1")
            status = ledger.operational_status(stale_after_seconds=1)
            self.assertEqual(status["stale_running"], 1)
            self.assertNotIn("sensitive-cache-key", json.dumps(status))
            self.assertEqual(ledger.recover_stale(stale_after_seconds=1, now=100), ("sensitive-cache-key",))
            self.assertEqual(ledger.operational_status()["states"], {"abandoned": 1})
            self.assertIsNone(ledger.claim("sensitive-cache-key", stale_after_seconds=30))

    def test_provider_errors_redact_secrets_and_receipts_cannot_echo_them(self) -> None:
        failed = subprocess.CompletedProcess(
            args=["provider"], returncode=1,
            stdout=json.dumps({"status": "error", "error_type": "RuntimeError", "error": "token secret-value rejected"}),
            stderr="",
        )
        with mock.patch("fmr.execution.subprocess.run", return_value=failed):
            with self.assertRaises(RuntimeError) as raised:
                _execute_with_timeout("provider", {}, Path("output"), {"TOKEN": "secret-value"}, 30)
        self.assertNotIn("secret-value", str(raised.exception))
        echoed = subprocess.CompletedProcess(
            args=["provider"], returncode=0,
            stdout=json.dumps({"status": "ok", "receipt": {"provider_receipt_version": "v1", "note": "secret-value"}}),
            stderr="",
        )
        with mock.patch("fmr.execution.subprocess.run", return_value=echoed):
            with self.assertRaisesRegex(RuntimeError, "secret material"):
                _execute_with_timeout("provider", {}, Path("output"), {"TOKEN": "secret-value"}, 30)

    def test_sqlite_backup_is_hash_pinned_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SqliteExecutionLedger(root / "ledger.sqlite3")
            ledger.claim("job", stale_after_seconds=30)
            backup = ledger.backup(root / "backups" / "ledger.sqlite3")
            data = Path(backup["path"]).read_bytes()
            self.assertEqual(backup["sha256"], hashlib.sha256(data).hexdigest())
            with self.assertRaisesRegex(ValueError, "already exists"):
                ledger.backup(backup["path"])

    def test_environment_secret_resolver_is_explicit_and_fail_closed(self) -> None:
        resolver = EnvironmentSecretResolver(("MODEL_API_KEY",), prefix="FMR_")
        with mock.patch.dict(os.environ, {"FMR_MODEL_API_KEY": "secret-value"}, clear=True):
            self.assertEqual(resolver("MODEL_API_KEY"), "secret-value")
            with self.assertRaisesRegex(ValueError, "allowlisted"):
                resolver("OTHER_KEY")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                resolver("MODEL_API_KEY")

    def test_retention_is_dry_run_by_default_and_confined_to_managed_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            managed = root / "managed"
            artifact_dir = managed / "execution"
            artifact_dir.mkdir(parents=True)
            artifact = artifact_dir / "result.json"
            artifact.write_text("{}", encoding="utf-8")
            ledger = SqliteExecutionLedger(root / "ledger.sqlite3")
            ledger.claim("cache-key", stale_after_seconds=30)
            ledger.complete("cache-key", {"output_artifact_references": [{"path": str(artifact)}]})
            with sqlite3.connect(ledger.path) as connection:
                connection.execute("UPDATE executions_v2 SET updated_at = 1")
            retention = ManagedArtifactRetention(ledger, managed)
            preview = retention.prune(older_than_seconds=1, now=100)
            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["pruned_count"], 0)
            self.assertTrue(artifact.exists())
            applied = retention.prune(older_than_seconds=1, dry_run=False, now=100)
            self.assertEqual(applied["pruned_count"], 1)
            self.assertFalse(artifact_dir.exists())
            self.assertEqual(ledger.operational_status()["states"], {"pruned": 1})

    def test_operations_cli_exposes_status_recovery_backup_and_retention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger_path = root / "ledger.sqlite3"
            ledger = SqliteExecutionLedger(ledger_path)
            ledger.claim("stale", stale_after_seconds=30)
            with sqlite3.connect(ledger_path) as connection:
                connection.execute("UPDATE executions_v2 SET claimed_at = 1, updated_at = 1")
            status = root / "status.json"
            self.assertEqual(run_provider_command(["operations-status", "--ledger", str(ledger_path), "--output", str(status)]), 0)
            self.assertEqual(json.loads(status.read_text())["states"], {"running": 1})
            recovery = root / "recovery.json"
            self.assertEqual(run_provider_command(["recover-executions", "--ledger", str(ledger_path), "--stale-after", "1", "--output", str(recovery)]), 0)
            self.assertEqual(json.loads(recovery.read_text())["recovered_count"], 1)
            receipt = root / "backup.json"
            backup = root / "backup.sqlite3"
            self.assertEqual(run_provider_command(["backup-execution-ledger", "--ledger", str(ledger_path), str(backup), "--output", str(receipt)]), 0)
            self.assertTrue(backup.exists())


if __name__ == "__main__":
    unittest.main()
