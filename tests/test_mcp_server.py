from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fmr.mcp_server import PROTOCOL_VERSION, handle_message
from tests.test_provider_router import _job


class McpServerTests(unittest.TestCase):
    def test_initialize_and_tool_discovery(self) -> None:
        initialized = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        self.assertEqual(initialized["result"]["protocolVersion"], PROTOCOL_VERSION)
        listed = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual({item["name"] for item in listed["result"]["tools"]}, {"discover_providers", "route_job", "prepare_handoff", "execute_job", "validate_job_result", "get_execution_receipt"})

    def test_route_tool_matches_python_api(self) -> None:
        from fmr import route_job
        job = _job(output_formats=["json"])
        response = handle_message({"jsonrpc": "2.0", "id": "route", "method": "tools/call", "params": {"name": "route_job", "arguments": {"job": job, "policy": "json-first"}}})
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"], route_job(job, policy=__import__("fmr").routing_policy("json-first")))

    def test_tool_errors_are_structured(self) -> None:
        response = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_execution_receipt", "arguments": {"execution_id": "missing", "ledger_path": str(Path(tempfile.gettempdir()) / "missing-fmr-ledger.sqlite3")}}})
        self.assertTrue(response["result"]["isError"])
        self.assertIn("not found", json.loads(response["result"]["content"][0]["text"])["error"])

    def test_notifications_do_not_emit_responses(self) -> None:
        self.assertIsNone(handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}))


if __name__ == "__main__":
    unittest.main()
