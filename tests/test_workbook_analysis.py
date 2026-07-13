from __future__ import annotations

import unittest

from fmr.types import ModelRequest
from fmr.workbook import (
    WorkbookMap,
    analyse_workbook_map,
    derive_workbook_evidence,
    inspect_workbook_bytes,
)
from tests.xlsx_factory import build_xlsx, financial_workbook


class WorkbookAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workbook_map = inspect_workbook_bytes(
            financial_workbook(),
            filename="synthetic.xlsx",
        )

    def test_evidence_is_conservative_and_auditable(self) -> None:
        evidence = derive_workbook_evidence(self.workbook_map)
        self.assertEqual(
            set(evidence.available_data),
            {"income_statement_history", "balance_sheet_history"},
        )
        self.assertEqual(
            set(evidence.workbook_capabilities),
            {
                "assumptions_section",
                "existing_formulas",
                "forecast_periods",
                "historical_periods",
            },
        )
        self.assertTrue(all(item.evidence for item in evidence.items))

    def test_analysis_merges_explicit_and_derived_inputs(self) -> None:
        request = ModelRequest(
            objective="value an operating company using a DCF",
            role="finance_manager",
            available_data=(
                "cash_flow_history",
                "revenue_drivers",
                "capital_expenditure_schedule",
                "working_capital_schedule",
                "net_debt",
            ),
            workbook_capabilities=(),
            assumptions=(
                "forecast_horizon",
                "tax_rate",
                "discount_rate",
                "terminal_value_assumption",
            ),
        )
        analysis = analyse_workbook_map(self.workbook_map, request)
        self.assertTrue(analysis.recommendation.readiness.ready)
        self.assertTrue(analysis.transformation_plan.ready_to_apply)
        self.assertIn(
            "income_statement_history",
            analysis.effective_request.available_data,
        )
        self.assertIn(
            "balance_sheet_history",
            analysis.effective_request.available_data,
        )
        self.assertEqual(analysis.effective_request.assumptions, request.assumptions)

    def test_assumptions_are_never_derived(self) -> None:
        request = ModelRequest(
            objective="value an operating company using a DCF",
            role="finance_manager",
            available_data=(),
            workbook_capabilities=(),
            assumptions=(),
        )
        analysis = analyse_workbook_map(self.workbook_map, request)
        self.assertEqual(analysis.effective_request.assumptions, ())
        self.assertIn(
            "missing_assumption:discount_rate",
            analysis.recommendation.readiness.blockers,
        )

    def test_workbook_map_round_trip_is_stable(self) -> None:
        parsed = WorkbookMap.from_mapping(self.workbook_map.to_dict())
        self.assertEqual(parsed, self.workbook_map)

    def test_workbook_map_can_report_more_sheets_than_it_maps(self) -> None:
        payload = self.workbook_map.to_dict()
        payload["workbook"]["sheet_count"] += 1
        parsed = WorkbookMap.from_mapping(payload)
        self.assertEqual(parsed.sheet_count, len(parsed.sheets) + 1)

    def test_workbook_map_rejects_non_hexadecimal_sha256(self) -> None:
        payload = self.workbook_map.to_dict()
        payload["source"]["sha256"] = "z" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 hex string"):
            WorkbookMap.from_mapping(payload)

    def test_net_debt_requires_two_historical_periods(self) -> None:
        workbook_map = inspect_workbook_bytes(
            build_xlsx(
                [
                    {
                        "name": "Balance Sheet",
                        "cells": {
                            "A1": "Balance Sheet",
                            "B2": 2025,
                            "A3": "Cash",
                            "B3": 50,
                            "A4": "Debt",
                            "B4": 100,
                            "A5": "Total Assets",
                            "B5": 200,
                            "A6": "Total Liabilities",
                            "B6": 120,
                        },
                    }
                ]
            ),
            filename="single-period.xlsx",
        )
        evidence = derive_workbook_evidence(workbook_map)
        self.assertNotIn("net_debt", evidence.available_data)
        self.assertNotIn("balance_sheet_history", evidence.available_data)

    def test_analysis_contract_is_self_contained(self) -> None:
        request = ModelRequest(
            objective="build a budget forecast",
            role="finance_manager",
            available_data=(
                "balance_sheet_history",
                "revenue_drivers",
                "operating_cost_drivers",
            ),
            workbook_capabilities=(),
            assumptions=("forecast_horizon",),
        )
        payload = analyse_workbook_map(self.workbook_map, request).to_dict()
        self.assertEqual(payload["contract_version"], "workbook-analysis.v1")
        self.assertEqual(payload["workbook_map"]["contract_version"], "workbook-map.v1")
        self.assertEqual(
            payload["effective_request"]["contract_version"],
            "model-request.v1",
        )
        self.assertEqual(
            payload["recommendation"]["contract_version"],
            "model-recommendation.v1",
        )
        self.assertEqual(
            payload["transformation_plan"]["contract_version"],
            "transformation-plan.v1",
        )


if __name__ == "__main__":
    unittest.main()
