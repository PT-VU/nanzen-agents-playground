"""Tests for the CSV reader and PDF report tools."""

import json

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
