"""Task definitions for ActorAgents.

Each task is a dict with:
  - name: identifier for the task
  - agent_name: name of the ActorAgent that will handle it
  - role: the agent's role description
  - prompt: the task prompt sent to the agent

Add your own tasks below or modify the existing ones.
"""

TASKS: list[dict] = [
    {
        "name": "billing_summary",
        "agent_name": "BillingAnalyst",
        "role": "Billing and payment analysis specialist",
        "expected_report": "billing_summary_merid001.pdf",
        "max_steps": 30,
        "prompt": (
            "Analyze the billing history for account MERID-001 (Meridian Health).\n"
            "1. Use the deterministic billing tools to inspect the full billing range, "
            "list invoice cases, and read invoice case details.\n"
            "2. Use build_invoice_case_documents to bulk-create Structured Invoice Case "
            "Documents, then review only cases listed in requires_agent_review.\n"
            "3. Perform the final missing-invoice-id scan.\n"
            "4. Aggregate totals with aggregate_billing_summary(use_case_documents=True) "
            "and verify the summary.\n"
            "5. Summarize total invoiced, total valid paid, and outstanding amount from "
            "aggregate_billing_summary only.\n"
            "6. Identify late payments, outstanding invoices, and notable anomalies.\n"
            "7. After verification passes, call build_billing_pdf_sections and use its "
            "title, filename, and content_sections_json to create the PDF report.\n"
            "8. The PDF report must contain:\n"
            "   - A summary paragraph of the billing relationship\n"
            "   - A five-column invoice table: Invoice ID, Amount (EUR), "
            "Valid Paid (EUR), Outstanding (EUR), Status\n"
            "   - Concise notable findings (disputes, credits, late payments)\n"
            "A chart is optional; include one only if it materially improves readability. "
            "Do not include case labels, timing-status columns, event IDs, "
            "internal workflow metadata, or unrelated customer profile fields in the PDF."
        ),
    },
    {
        "name": "usage_trends",
        "agent_name": "UsageAnalyst",
        "role": "Product usage and adoption analyst",
        "prompt": (
            "Analyze product usage trends for account MERID-001 (Meridian Health).\n"
            "1. Read the product_usage data.\n"
            "2. Identify trends: is usage growing, flat, or declining?\n"
            "3. Break down usage by department if possible.\n"
            "4. Create a PDF report called 'usage_trends_merid001.pdf' with:\n"
            "   - A summary of overall usage trends\n"
            "   - A table showing usage over time\n"
            "   - A chart visualizing the trend"
        ),
    },
    {
        "name": "support_health",
        "agent_name": "SupportAnalyst",
        "role": "Customer support and satisfaction analyst",
        "prompt": (
            "Analyze support ticket history for account MERID-001 (Meridian Health).\n"
            "1. Read the support_tickets data.\n"
            "2. Categorize tickets by type/severity.\n"
            "3. Assess resolution times and identify recurring issues.\n"
            "4. Create a PDF report called 'support_health_merid001.pdf' with:\n"
            "   - A summary of support health\n"
            "   - A table of tickets with status and resolution\n"
            "   - Recommendations for improvement"
        ),
    },
    # -----------------------------------------------------------------------
    # TODO: Add your own tasks here during the live coding session.
    # Example:
    # {
    #     "name": "account_risk_assessment",
    #     "agent_name": "RiskAnalyst",
    #     "role": "Account risk and churn prediction analyst",
    #     "prompt": "...",
    # },
    # -----------------------------------------------------------------------
]
