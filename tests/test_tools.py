"""Tests for the CSV reader and PDF report tools."""

import csv
import json

import challenge.tools.billing as billing_module
from challenge.tools.billing import (
    aggregate_billing_summary,
    build_billing_pdf_sections,
    build_invoice_case_documents,
    inspect_billing_range,
    list_invoice_cases,
    read_billing_context,
    save_invoice_case,
    verify_billing_summary,
)
from challenge.tools.csv_reader import CSVReaderTool, read_csv_source
from challenge.tools.pdf_report import PDFReportTool


class TestCSVReader:
    def test_list_sources(self):
        """CSVReaderTool returns error with available sources for unknown source."""
        tool = CSVReaderTool()
        result = tool.forward(source="nonexistent")
        assert "ERROR" in result
        assert "accounts" in result

    def test_read_accounts(self):
        """Can read the accounts CSV."""
        rows = read_csv_source("accounts")
        assert len(rows) > 0
        assert "account_id" in rows[0]

    def test_read_accounts_tool(self):
        """CSVReaderTool returns formatted output for accounts."""
        tool = CSVReaderTool()
        result = tool.forward(source="accounts")
        assert "MERID-001" in result
        assert "rows from 'accounts'" in result

    def test_filter_by_account_id(self):
        """Can filter rows by account_id."""
        rows = read_csv_source("accounts", account_id="MERID-001")
        assert len(rows) == 1
        assert rows[0]["account_id"] == "MERID-001"

    def test_read_billing(self):
        """Can read billing data."""
        rows = read_csv_source("billing", limit=5)
        assert len(rows) <= 5
        assert len(rows) > 0

    def test_limit(self):
        """Limit parameter caps the number of rows."""
        rows = read_csv_source("billing", limit=3)
        assert len(rows) <= 3

    def test_all_sources_readable(self):
        """All registered data sources can be read."""
        from challenge.tools.csv_reader import DATA_SOURCES

        for source_name in DATA_SOURCES:
            rows = read_csv_source(source_name, limit=1)
            assert len(rows) >= 1, f"Source '{source_name}' returned no rows"


class TestPDFReport:
    def test_create_simple_report(self, tmp_path):
        """PDFReportTool creates a PDF file."""
        tool = PDFReportTool()

        # Override output dir for test
        import challenge.tools.pdf_report as pdf_module

        original_dir = pdf_module.OUTPUT_DIR
        pdf_module.OUTPUT_DIR = tmp_path

        try:
            sections = [
                {"type": "heading", "text": "Test Report"},
                {"type": "paragraph", "text": "This is a test paragraph."},
                {
                    "type": "table",
                    "headers": ["Name", "Value"],
                    "rows": [["Alpha", "100"], ["Beta", "200"]],
                },
            ]
            result = tool.forward(
                title="Test Report",
                filename="test_report.pdf",
                content_sections_json=json.dumps(sections),
            )
            assert "Report saved" in result
            assert (tmp_path / "test_report.pdf").exists()
            assert (tmp_path / "test_report.pdf").stat().st_size > 0
        finally:
            pdf_module.OUTPUT_DIR = original_dir


class TestBillingTools:
    def test_inspect_billing_range_resolves_missing_account_rows(self):
        result = inspect_billing_range(account_id="MERID-001")
        assert result["row_count"] == 155
        assert result["start_date"] == "2023-11-01"
        assert result["end_date"] == "2026-03-01"

    def test_read_billing_context_is_structured_and_not_truncated(self):
        result = read_billing_context(account_id="MERID-001")
        assert result["row_count"] == 155
        assert result["truncated"] is False
        assert isinstance(result["rows"], list)
        assert isinstance(result["rows"][0]["amount_cents"], int | type(None))

    def test_read_billing_context_resolves_missing_account_id_before_filtering(self):
        result = read_billing_context(account_id="MERID-001", invoice_id="INV-2025-MH-024")
        resolved_rows = [row for row in result["rows"] if row["event_id"] == "BIL-5204"]
        assert len(resolved_rows) == 1
        assert resolved_rows[0]["account_id"] == "MERID-001"
        assert resolved_rows[0]["account_id_resolved"] is True

    def test_list_invoice_cases_excludes_credit_notes_and_deduplicates_invoice_events(self):
        result = list_invoice_cases(account_id="MERID-001")
        invoice_ids = [case["invoice_id"] for case in result["invoice_cases"]]
        assert result["invoice_case_count"] == 28
        assert "CN-2025-MH-001" not in invoice_ids
        assert "CN-2025-MH-002" not in invoice_ids
        assert invoice_ids.count("INV-2025-MH-022") == 1

    def test_aggregate_billing_summary_outputs_verified_invoice_table(self):
        summary = aggregate_billing_summary(account_id="MERID-001")
        verification = verify_billing_summary(summary)
        invoice_by_id = {case["invoice_id"]: case for case in summary["invoice_cases"]}

        assert verification["status"] == "PASS"
        assert summary["invoice_count"] == 28
        assert summary["missing_invoice_id_scan_completed"] is True
        assert summary["missing_invoice_id_event_count"] == 13
        assert invoice_by_id["INV-2025-MH-024"]["valid_paid_amount_cents"] > 0
        assert invoice_by_id["INV-2025-MH-024"]["outstanding_amount_cents"] == 0

    def test_save_invoice_case_validates_required_schema(self, tmp_path, monkeypatch):
        monkeypatch.setattr(billing_module, "CASE_DOCS_DIR", tmp_path)
        case_doc = {
            "invoice_id": "INV-2025-MH-024",
            "analysis_status": "complete",
            "case_labels": ["payment_reminder"],
            "case_summary": "Paid before due date after a reminder event.",
            "canonical_invoice_event_id": "BIL-5201",
            "lifecycle_event_ids": ["BIL-5201", "BIL-5202", "BIL-5203", "BIL-5204", "BIL-5205"],
            "payment_amount_event_ids": ["BIL-5204"],
            "payment_status": "fully_paid",
            "timing_status": "on_time_or_early",
        }

        result = save_invoice_case(case_doc, account_id="MERID-001")

        assert result["status"] == "PASS"
        assert (tmp_path / "MERID-001" / "INV-2025-MH-024.json").exists()

    def test_case_document_aggregation_and_missing_id_scan(self, tmp_path, monkeypatch):
        monkeypatch.setattr(billing_module, "CASE_DOCS_DIR", tmp_path)
        direct_summary = aggregate_billing_summary(account_id="MERID-001")

        for case in direct_summary["invoice_cases"]:
            rows = read_billing_context(account_id="MERID-001", invoice_id=case["invoice_id"])[
                "rows"
            ]
            payment_ids = [
                row["event_id"] for row in rows if row["event_type"] == "payment_received"
            ]
            refund_ids = [
                row["event_id"] for row in rows if row["event_type"] == "refund_completed"
            ]
            adjustment_ids = [row["event_id"] for row in rows if row["event_type"] == "adjustment"]
            case_doc = {
                "invoice_id": case["invoice_id"],
                "analysis_status": "complete",
                "case_labels": case["case_labels"] or ["normal"],
                "case_summary": f"Structured case for {case['invoice_id']}.",
                "canonical_invoice_event_id": case["canonical_invoice_event_id"],
                "lifecycle_event_ids": case["event_ids"],
                "payment_amount_event_ids": payment_ids,
                "refund_amount_event_ids": refund_ids,
                "adjustment_amount_event_ids": adjustment_ids,
                "payment_status": case["payment_status"],
                "timing_status": case["timing_status"],
            }
            assert save_invoice_case(case_doc, account_id="MERID-001")["status"] == "PASS"

        scan_result = billing_module._scan_missing_invoice_ids(account_id="MERID-001")
        document_summary = aggregate_billing_summary(
            account_id="MERID-001",
            use_case_documents=True,
        )
        verification = verify_billing_summary(document_summary)

        assert scan_result["scan_completed"] is True
        assert document_summary["source"] == "billing_case_documents"
        assert document_summary["invoice_count"] == direct_summary["invoice_count"]
        assert document_summary["total_invoiced_cents"] == direct_summary["total_invoiced_cents"]
        assert (
            document_summary["total_valid_paid_cents"] == direct_summary["total_valid_paid_cents"]
        )
        assert (
            document_summary["total_outstanding_cents"]
            == direct_summary["total_outstanding_cents"]
        )
        assert verification["status"] == "PASS"

    def test_build_invoice_case_documents_returns_compact_summary(self, tmp_path, monkeypatch):
        monkeypatch.setattr(billing_module, "CASE_DOCS_DIR", tmp_path)

        result = build_invoice_case_documents(account_id="MERID-001")

        assert result["status"] == "PASS"
        assert result["case_document_count"] == 28
        assert "invoice_cases" not in result
        assert "rows" not in result
        assert "INV-2024-MH-006" in result["requires_agent_review"]
        assert "INV-2025-MH-022" in result["requires_agent_review"]
        assert (tmp_path / "MERID-001" / "INV-2024-MH-006.json").exists()

    def test_case_document_aggregation_excludes_duplicate_payment_from_outstanding(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(billing_module, "CASE_DOCS_DIR", tmp_path)
        build_invoice_case_documents(account_id="MERID-001")
        billing_module._scan_missing_invoice_ids(account_id="MERID-001")

        summary = aggregate_billing_summary(account_id="MERID-001", use_case_documents=True)
        invoice_by_id = {case["invoice_id"]: case for case in summary["invoice_cases"]}
        duplicate_case = json.loads(
            (tmp_path / "MERID-001" / "INV-2024-MH-006.json").read_text(encoding="utf-8")
        )

        assert duplicate_case["payment_amount_event_ids"] == ["BIL-5024"]
        assert duplicate_case["duplicate_payment_event_ids"] == ["BIL-5144"]
        assert duplicate_case["refund_amount_event_ids"] == ["BIL-5146"]
        assert invoice_by_id["INV-2024-MH-006"]["valid_paid_amount_cents"] == 1815000
        assert invoice_by_id["INV-2024-MH-006"]["outstanding_amount_cents"] == 0
        assert invoice_by_id["INV-2024-MH-006"]["paid_date"] == "2024-05-19"
        assert (
            summary["total_valid_paid_cents"]
            == aggregate_billing_summary(account_id="MERID-001")["total_valid_paid_cents"]
        )
        assert verify_billing_summary(summary)["status"] == "PASS"

    def test_verifier_rejects_fully_paid_case_with_outstanding_balance(self):
        summary = aggregate_billing_summary(account_id="MERID-001")
        summary["invoice_cases"][0]["outstanding_amount_cents"] = 1
        summary["total_outstanding_cents"] += 1

        result = verify_billing_summary(summary)

        assert result["status"] == "FAIL"
        assert "fully_paid with non-zero outstanding" in " ".join(result["errors"])

    def test_build_billing_pdf_sections_uses_customer_facing_format(self):
        summary = aggregate_billing_summary(account_id="MERID-001")
        report = build_billing_pdf_sections(summary)
        sections = report["content_sections"]
        table = next(section for section in sections if section["type"] == "table")
        section_text = json.dumps(sections, ensure_ascii=False)

        assert report["filename"] == "billing_summary_merid001.pdf"
        assert summary["paid_late_invoice_count"] == 10
        assert table["headers"] == [
            "Invoice ID",
            "Amount (EUR)",
            "Valid Paid (EUR)",
            "Outstanding (EUR)",
            "Status",
        ]
        assert len(table["rows"]) == 28
        assert all(len(row) == 5 for row in table["rows"])
        assert not any(section["type"] == "chart" for section in sections)
        assert "Case Labels" not in section_text
        assert "Timing" not in section_text
        assert "annual_revenue" not in section_text

    def test_build_billing_pdf_sections_can_optionally_include_chart(self):
        summary = aggregate_billing_summary(account_id="MERID-001")
        report = build_billing_pdf_sections(summary, include_chart=True)
        charts = [section for section in report["content_sections"] if section["type"] == "chart"]

        assert len(charts) == 1
        assert charts[0]["title"] == "Invoice Amounts and Outstanding Balances"

    def test_final_pdf_findings_separate_duplicate_from_multi_payment(self, tmp_path, monkeypatch):
        monkeypatch.setattr(billing_module, "CASE_DOCS_DIR", tmp_path)
        build_invoice_case_documents(account_id="MERID-001")
        billing_module._scan_missing_invoice_ids(account_id="MERID-001")
        summary = aggregate_billing_summary(account_id="MERID-001", use_case_documents=True)
        report = build_billing_pdf_sections(summary)
        paragraphs = [
            section["text"]
            for section in report["content_sections"]
            if section["type"] == "paragraph"
        ]
        section_text = "\n".join(paragraphs)
        cases = {case["invoice_id"]: case for case in summary["invoice_cases"]}
        duplicate_paragraph = next(
            paragraph
            for paragraph in paragraphs
            if paragraph.startswith("Duplicate payment requiring refund:")
        )
        multi_payment_paragraph = next(
            paragraph
            for paragraph in paragraphs
            if paragraph.startswith("Multi-payment settlements:")
        )
        credits_paragraph = next(
            paragraph
            for paragraph in paragraphs
            if paragraph.startswith("Credits and adjustments:")
        )

        assert "duplicate_payment" in cases["INV-2024-MH-006"]["case_labels"]
        assert "multiple_payments" not in cases["INV-2024-MH-006"]["case_labels"]
        assert "multiple_payments" in cases["INV-2025-MH-021"]["case_labels"]
        assert "duplicate_payment" not in cases["INV-2025-MH-021"]["case_labels"]
        assert "INV-2024-MH-006" in duplicate_paragraph
        assert "INV-2025-MH-021" not in duplicate_paragraph
        assert "INV-2025-MH-021" in multi_payment_paragraph
        assert "Manual reconciliation" not in section_text
        assert "INV-2024-MH-005" in credits_paragraph
        assert "INV-2025-MH-015" in credits_paragraph
        assert "INV-2026-MH-026" in credits_paragraph
        assert "INV-2026-MH-027" in credits_paragraph
        assert "INV-2023-MH-001" not in credits_paragraph

    def test_small_writeoff_settlement_delta_reconciles_effective_outstanding(
        self, tmp_path, monkeypatch
    ):
        with open(billing_module.BILLING_CSV, newline="", encoding="utf-8") as f:
            fieldnames = next(csv.reader(f))

        test_billing_csv = tmp_path / "billing.csv"
        base_row = {field: "" for field in fieldnames}
        rows = [
            {
                **base_row,
                "event_id": "BIL-T001",
                "account_id": "MERID-001",
                "timestamp": "2025-01-01 09:00:00",
                "event_type": "invoice_issued",
                "invoice_id": "INV-TEST-001",
                "description": "Test invoice",
                "amount": "100.00",
                "currency": "EUR",
                "due_date": "2025-01-31",
                "status": "issued",
            },
            {
                **base_row,
                "event_id": "BIL-T002",
                "account_id": "MERID-001",
                "timestamp": "2025-01-20 09:00:00",
                "event_type": "payment_received",
                "invoice_id": "INV-TEST-001",
                "description": "Payment received via SEPA Credit Transfer",
                "amount": "99.99",
                "currency": "EUR",
                "due_date": "2025-01-31",
                "paid_date": "2025-01-20",
                "days_past_due": "-11",
                "status": "partial",
            },
            {
                **base_row,
                "event_id": "BIL-T003",
                "account_id": "MERID-001",
                "timestamp": "2025-01-21 09:00:00",
                "event_type": "adjustment",
                "invoice_id": "INV-TEST-001",
                "description": "Write-off of €0.01 rounding difference. Approved per policy.",
                "amount": "0.01",
                "currency": "EUR",
                "status": "reconciled",
            },
        ]
        with open(test_billing_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        monkeypatch.setattr(billing_module, "BILLING_CSV", test_billing_csv)
        monkeypatch.setattr(billing_module, "CASE_DOCS_DIR", tmp_path / "case_docs")

        build_invoice_case_documents(account_id="MERID-001")
        billing_module._scan_missing_invoice_ids(account_id="MERID-001")
        summary = aggregate_billing_summary(account_id="MERID-001", use_case_documents=True)
        verification = verify_billing_summary(summary)
        invoice_case = summary["invoice_cases"][0]
        case_doc = json.loads(
            (tmp_path / "case_docs" / "MERID-001" / "INV-TEST-001.json").read_text(
                encoding="utf-8"
            )
        )
        report = build_billing_pdf_sections(summary)
        table = next(
            section for section in report["content_sections"] if section["type"] == "table"
        )

        assert verification["status"] == "PASS"
        assert case_doc["abnormal_tags"] == ["rounding_writeoff"]
        assert case_doc["settlement_adjustment_cents"] == -1
        assert case_doc["settlement_adjustment_event_ids"] == ["BIL-T003"]
        assert invoice_case["valid_paid_amount_cents"] == 9999
        assert invoice_case["base_outstanding_amount_cents"] == 1
        assert invoice_case["effective_outstanding_amount_cents"] == 0
        assert invoice_case["outstanding_amount_cents"] == 0
        assert invoice_case["settlement_status"] == "settled"
        assert summary["total_outstanding_cents"] == 0
        assert table["rows"][0] == ["INV-TEST-001", "100.00", "99.99", "0.00", "settled"]


class TestPDFReportValidation:
    def test_invalid_json(self):
        """PDFReportTool handles invalid JSON gracefully."""
        tool = PDFReportTool()
        result = tool.forward(
            title="Test",
            filename="test.pdf",
            content_sections_json="not valid json",
        )
        assert "ERROR" in result

    def test_non_array_json(self):
        """PDFReportTool rejects non-array JSON."""
        tool = PDFReportTool()
        result = tool.forward(
            title="Test",
            filename="test.pdf",
            content_sections_json='{"type": "heading"}',
        )
        assert "ERROR" in result

    def test_report_with_chart(self, tmp_path):
        """PDFReportTool can render charts."""
        tool = PDFReportTool()

        import challenge.tools.pdf_report as pdf_module

        original_dir = pdf_module.OUTPUT_DIR
        pdf_module.OUTPUT_DIR = tmp_path

        try:
            sections = [
                {"type": "heading", "text": "Chart Report"},
                {
                    "type": "chart",
                    "chart_type": "bar",
                    "title": "Test Chart",
                    "labels": ["Q1", "Q2", "Q3"],
                    "datasets": [{"label": "Revenue", "data": [100, 150, 200]}],
                },
            ]
            result = tool.forward(
                title="Chart Report",
                filename="chart_report.pdf",
                content_sections_json=json.dumps(sections),
            )
            assert "Report saved" in result
            assert (tmp_path / "chart_report.pdf").exists()
        finally:
            pdf_module.OUTPUT_DIR = original_dir
