"""ActorAgent - a task-oriented agent with shared context access."""

from __future__ import annotations

import logging

from smolagents import CodeAgent

from challenge.tools import (
    AggregateBillingSummaryTool,
    BillingContextTool,
    BuildBillingPDFSectionsTool,
    BuildInvoiceCaseDocumentsTool,
    CalculateBillingTool,
    CSVReaderTool,
    InspectBillingRangeTool,
    ListInvoiceCasesTool,
    PDFReportTool,
    SaveInvoiceCaseTool,
    ScanMissingInvoiceIdsTool,
    VerifyBillingSummaryTool,
)

logger = logging.getLogger(__name__)


INSTRUCTIONS_TEMPLATE = """\
You are an ActorAgent, an autonomous analyst that accomplishes tasks by reading
data from a shared context and producing reports.

## Your identity
- Name: {agent_name}
- Role: {role}

## Available data sources
You have access to CSV data via the `read_context` tool. Available sources:
  - accounts: customer master data (account_id, name, industry, segment, etc.)
  - billing: invoicing events, payments, amounts, statuses
  - product_usage: weekly product usage metrics per department
  - support_tickets: support interactions and ticket history
  - crm_interactions: CRM activity log (calls, meetings, notes)
  - emails: email communications
  - contracts: pricing and contract terms
  - purchase_orders: purchase order records

## How to work
1. Read the task carefully.
2. Use `read_context` to gather the data you need. Filter by account_id when relevant.
3. Analyze the data in code: compute aggregates, find patterns, identify issues.
4. Use `create_report` to produce a PDF with your findings.
5. Return a short summary of what you found.

## Rules
- Always ground your analysis in the actual data. Never fabricate numbers.
- When creating reports, include relevant data tables and charts.
- Be concise in your summaries.
"""


BILLING_INSTRUCTIONS = """\

## Billing workflow
For billing_summary tasks, use the deterministic billing tools instead of
manually parsing large raw CSV text.
These tools return JSON strings. In generated Python code, call `json.loads(...)`
before treating a tool result as a dictionary or list.

Required sequence:
1. Call `inspect_billing_range` for the target account.
2. Call `list_invoice_cases` to get the complete INV-* invoice checklist.
3. Call `build_invoice_case_documents` to create draft case documents in bulk.
   Do not manually print or save every generated case document.
4. Review only cases listed in `requires_agent_review`. Call `save_invoice_case`
   only when you need to correct one reviewed case. Include event IDs, not
   copied monetary totals, in financial event reference fields.
5. Call `scan_missing_invoice_ids` before aggregation. Assign a missing-ID event
   to an invoice only when the evidence is clear; otherwise leave it unassigned.
6. Call `aggregate_billing_summary` with `use_case_documents=True` and use its
   totals as the source of truth.
7. Call `verify_billing_summary` on the aggregate JSON.
8. Only after verification passes, call `build_billing_pdf_sections`.
9. Call `create_report` with the returned title, filename, and
   content_sections_json.

Use `read_billing_context` for invoice-level or nearby-row investigation when
you need narrative detail. It returns structured JSON and does not silently
truncate rows. Use `calculate_billing` for exact arithmetic over source event
IDs. Do not recalculate total invoiced, total paid, or outstanding amounts
independently after `aggregate_billing_summary` has produced them.

Structured Invoice Case Documents require these fields:
`invoice_id`, `analysis_status`, `case_labels`, `case_summary`,
`canonical_invoice_event_id`, `lifecycle_event_ids`, `payment_status`, and
`timing_status`. Optional financial fields include
`payment_amount_event_ids`, `refund_amount_event_ids`, `credit_amount_event_ids`,
`adjustment_amount_event_ids`, and `duplicate_payment_event_ids`.

Final PDF requirements:
- Use the sections from `build_billing_pdf_sections`. You may pass
  `include_chart=True` only when a chart materially improves readability; a
  chart is optional and should not be added by default.
- The invoice table must have exactly these five columns: Invoice ID,
  Amount (EUR), Valid Paid (EUR), Outstanding (EUR), Status.
- Do not include timing classifications, case labels, event IDs, dispute IDs,
  internal workflow states, account profile fields, annual revenue, website,
  contacts, city/country, or Agent reasoning in the PDF.
- Keep anomalies as concise customer-facing Notable Findings after the invoice
  table.
"""


class ActorAgent:
    """A task-oriented agent that reads shared context and produces reports."""

    def __init__(
        self,
        name: str,
        role: str,
        model: object,
        tools: list | None = None,
        max_steps: int = 15,
    ):
        self.name = name
        self.role = role

        default_tools = [
            CSVReaderTool(),
            BillingContextTool(),
            InspectBillingRangeTool(),
            ListInvoiceCasesTool(),
            CalculateBillingTool(),
            BuildInvoiceCaseDocumentsTool(),
            SaveInvoiceCaseTool(),
            ScanMissingInvoiceIdsTool(),
            AggregateBillingSummaryTool(),
            VerifyBillingSummaryTool(),
            BuildBillingPDFSectionsTool(),
            PDFReportTool(),
        ]
        all_tools = default_tools + (tools or [])

        instructions = INSTRUCTIONS_TEMPLATE
        if "billing" in f"{name} {role}".lower():
            instructions += BILLING_INSTRUCTIONS

        self.agent = CodeAgent(
            tools=all_tools,
            model=model,
            instructions=instructions.format(agent_name=name, role=role),
            additional_authorized_imports=[
                "json",
                "csv",
                "datetime",
                "collections",
                "statistics",
                "math",
                "re",
            ],
            max_steps=max_steps,
        )

    def run(self, task: str) -> str:
        """Execute a task and return the agent's response."""
        logger.info("[%s] Starting task: %s", self.name, task[:100])
        result = self.agent.run(task)
        logger.info("[%s] Task completed", self.name)
        return result
