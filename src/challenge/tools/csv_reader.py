"""CSVReaderTool - reads account context from CSV data files.

This tool gives agents access to the shared data context. Each CSV file
represents a table in the system (billing, support tickets, product usage, etc.).
Agents use this tool to query the data they need for their tasks.
"""

from __future__ import annotations

import csv
from pathlib import Path

from smolagents import Tool

# Root data directory (resolved relative to project root)
DATA_DIR = Path(__file__).resolve().parents[3] / "data"

# Registry of available data sources and their CSV files
DATA_SOURCES: dict[str, str] = {
    "accounts": "accounts.csv",
    "billing": "billing.csv",
    "product_usage": "product_usage.csv",
    "support_tickets": "support_tickets.csv",
    "crm_interactions": "crm_interactions.csv",
    "emails": "emails.csv",
    "contracts": "contracts.csv",
    "purchase_orders": "purchase_orders.csv",
}


def read_csv_source(
    source: str,
    account_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, str]]:
    """Read rows from a CSV data source, optionally filtering by account_id."""
    if source not in DATA_SOURCES:
        raise ValueError(f"Unknown source '{source}'. Available: {sorted(DATA_SOURCES.keys())}")

    csv_path = DATA_DIR / DATA_SOURCES[source]
    if not csv_path.exists():
        raise FileNotFoundError(f"Data file not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filter by account_id if the column exists and a filter is given
            if account_id and "account_id" in row:
                if row["account_id"] != account_id:
                    continue
            rows.append(dict(row))
            if len(rows) >= limit:
                break

    return rows


class CSVReaderTool(Tool):
    """Tool for agents to query the shared CSV data context."""

    name = "read_context"
    description = (
        "Read data from the shared context. Returns rows from a CSV data source.\n"
        "Available sources: accounts, billing, product_usage, support_tickets, "
        "crm_interactions, emails, contracts, purchase_orders.\n"
        "Use account_id to filter rows for a specific account (e.g. 'MERID-001')."
    )
    inputs = {
        "source": {
            "type": "string",
            "description": (
                "The data source to read. One of: accounts, billing, product_usage, "
                "support_tickets, crm_interactions, emails, contracts, purchase_orders."
            ),
        },
        "account_id": {
            "type": "string",
            "description": "Filter rows by account_id (e.g. 'MERID-001'). Optional.",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Max rows to return. Default: 50.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(
        self,
        source: str,
        account_id: str | None = None,
        limit: int | None = None,
    ) -> str:
        effective_limit = limit if limit is not None else 50
        try:
            rows = read_csv_source(source, account_id=account_id, limit=effective_limit)
        except (ValueError, FileNotFoundError) as exc:
            return f"ERROR: {exc}"

        if not rows:
            return f"No rows found in '{source}'" + (
                f" for account_id='{account_id}'" if account_id else ""
            )

        # Format as a readable text table
        headers = list(rows[0].keys())
        lines = [" | ".join(headers)]
        lines.append("-+-".join("-" * len(h) for h in headers))
        for row in rows:
            lines.append(" | ".join(row.get(h, "") for h in headers))

        return f"({len(rows)} rows from '{source}')\n" + "\n".join(lines)
