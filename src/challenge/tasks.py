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
        "prompt": (
            "Analyze the billing history for account MERID-001 (Meridian Health).\n"
            "1. Read the billing data and summarize total invoiced vs total paid.\n"
            "2. Identify any late payments or outstanding invoices.\n"
            "3. Create a PDF report called 'billing_summary_merid001.pdf' with:\n"
            "   - A summary paragraph of the billing relationship\n"
            "   - A table of all invoices with their status and amounts\n"
            "   - Any notable findings (disputes, credits, late payments)"
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
