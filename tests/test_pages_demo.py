from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _runtime() -> ModuleType:
    path = ROOT / "pages" / "demo_runtime.py"
    spec = importlib.util.spec_from_file_location("fmr_pages_demo_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Pages demo runtime")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PagesDemoTests(unittest.TestCase):
    def test_static_entrypoint_and_privacy_boundary_are_explicit(self) -> None:
        html = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Test the router without installing anything", html)
        self.assertIn("Inputs stay in the browser", html)
        self.assertIn(
            "Not accounting, tax, lending, valuation or investment advice",
            html,
        )
        self.assertNotIn("<form", html)

    def test_worker_uses_versioned_pyodide_and_packaged_wheel(self) -> None:
        worker = (ROOT / "pages" / "worker.js").read_text(encoding="utf-8")
        self.assertIn('PYODIDE_VERSION = "0.29.4"', worker)
        self.assertIn("build.wheel_asset", worker)
        self.assertIn("micropip.install", worker)
        self.assertNotIn("/api/", worker)

    def test_demo_runtime_imports_actual_fmr_paths(self) -> None:
        runtime_path = ROOT / "pages" / "demo_runtime.py"
        ast.parse(runtime_path.read_text(encoding="utf-8"))
        runtime = runtime_path.read_text(encoding="utf-8")
        self.assertIn("from fmr.workflow import compile_workflow", runtime)
        self.assertIn("from fmr.provider_service import prepare_handoff", runtime)
        self.assertIn("PythonForecastExecutor", runtime)
        self.assertIn("create_statement_csv_workflow_source", runtime)
        self.assertIn('"production_accepted": False', runtime)
        self.assertIn('"provider_subprocess_isolation": False', runtime)

    def test_supported_workflow_compiles_to_python_forecast(self) -> None:
        result = _runtime().run_demo(
            {
                "case_id": "monthly_forecast",
                "assumptions": {
                    "forecast_horizon": 3,
                    "revenue_growth_rate": "0.09",
                    "operating_cost_growth_rate": "0.04",
                    "scenario": "base",
                    "scenario_adjustments": {
                        "base": {
                            "revenue_growth_delta": "0",
                            "operating_cost_growth_delta": "0",
                        }
                    },
                },
            },
            execute=False,
        )
        self.assertNotEqual(result["plan"]["status"], "blocked")
        model_steps = [
            step for step in result["plan"]["steps"] if step["kind"] == "model"
        ]
        self.assertTrue(
            any(step["provider_id"] == "python-forecast" for step in model_steps)
        )
        self.assertTrue(result["boundary"]["browser_only"])

    def test_dcf_executes_real_built_in_provider(self) -> None:
        result = _runtime().run_demo(
            {
                "case_id": "operating_valuation",
                "assumptions": {
                    "forecast_horizon": 5,
                    "revenue_growth_rate": "0.08",
                    "operating_margin_rate": "0.20",
                    "discount_rate": "0.10",
                    "terminal_growth_rate": "0.02",
                    "net_debt": "300000",
                },
            },
            execute=True,
        )
        self.assertEqual(result["execution"]["state"], "completed")
        self.assertEqual(result["execution"]["provider_id"], "python-forecast")
        self.assertEqual(
            result["execution"]["package_id"],
            "python-forecast/operating-company-dcf",
        )
        self.assertEqual(result["execution"]["validation"]["status"], "passed")
        self.assertIn("enterprise_value", result["artifact"])
        self.assertIn("equity_value", result["artifact"])

    def test_unsupported_project_finance_case_remains_blocked(self) -> None:
        result = _runtime().run_demo(
            {"case_id": "project_finance", "assumptions": {}},
            execute=False,
        )
        self.assertEqual(result["plan"]["status"], "blocked")
        self.assertTrue(result["plan"]["missing_requirements"])
        self.assertIsNone(result["execution"])

    def test_pages_builder_emits_complete_static_site(self) -> None:
        from scripts.build_pages_site import main  # type: ignore[import-not-found]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wheel = root / "financial_model_router-1.0.0a1-py3-none-any.whl"
            wheel.write_bytes(b"synthetic-wheel")
            output = root / "site"
            with patch.object(
                sys,
                "argv",
                [
                    "build_pages_site.py",
                    "--wheel",
                    str(wheel),
                    "--output",
                    str(output),
                    "--revision",
                    "abc123",
                ],
            ):
                main()
            self.assertTrue((output / "index.html").is_file())
            self.assertEqual((output / wheel.name).read_bytes(), b"synthetic-wheel")
            self.assertTrue((output / ".nojekyll").is_file())
            build = json.loads((output / "version.json").read_text(encoding="utf-8"))
            self.assertEqual(build["wheel_asset"], wheel.name)
            self.assertEqual(build["revision"], "abc123")

    def test_pages_workflow_has_required_permissions_and_deploy_actions(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "pages.yml"
        ).read_text(encoding="utf-8")
        for expected in (
            "pull_request:",
            "pages: write",
            "id-token: write",
            "actions/configure-pages@v5",
            "actions/upload-pages-artifact@v4",
            "actions/deploy-pages@v4",
        ):
            self.assertIn(expected, workflow)


if __name__ == "__main__":
    unittest.main()
