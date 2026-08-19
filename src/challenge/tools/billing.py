"""Deterministic billing helpers and tools for the billing summary workflow."""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from challenge.tools.base import Tool

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
ACCOUNTS_CSV = DATA_DIR / "accounts.csv"
BILLING_CSV = DATA_DIR / "billing.csv"
CASE_DOCS_DIR = Path(__file__).resolve().parents[3] / "output" / "billing_case_documents"
INVOICE_RE = re.compile(r"^INV-")
CREDIT_NOTE_RE = re.compile(r"^CN-")

MONEY_FIELDS = {
    "amount",
    "tax_amount",
    "fx_original_amount",
}
DECIMAL_FIELDS = {
    "fx_rate",
    "tax_rate_pct",
}
INT_FIELDS = {
    "days_past_due",
}

REQUIRED_CASE_FIELDS = {
    "invoice_id",
    "analysis_status",
    "case_labels",
    "case_summary",
    "canonical_invoice_event_id",
    "lifecycle_event_ids",
    "payment_status",
    "timing_status",
}
OPTIONAL_CASE_FIELDS = {
    "abnormal_tags",
    "payment_amount_event_ids",
    "refund_amount_event_ids",
    "credit_amount_event_ids",
    "adjustment_amount_event_ids",
    "duplicate_payment_event_ids",
    "settlement_adjustment_cents",
    "settlement_adjustment_event_ids",
    "settlement_adjustment_reason",
    "excluded_event_ids",
    "attached_missing_invoice_id_event_ids",
    "unassigned_missing_invoice_id_event_ids",
    "notes",
}
ALLOWED_CASE_FIELDS = REQUIRED_CASE_FIELDS | OPTIONAL_CASE_FIELDS
MAX_SETTLEMENT_ADJUSTMENT_CENTS = 1000


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_date(value: str | None) -> date | None:
    value = _clean(value)
    if value is None:
        return None
    return date.fromisoformat(value[:10])


def _parse_timestamp(value: str | None) -> datetime | None:
    value = _clean(value)
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _parse_decimal(value: str | None) -> Decimal | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _decimal_to_cents(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int((value * Decimal("100")).quantize(Decimal("1")))


def _cents_to_amount(cents: int) -> float:
    return float((Decimal(cents) / Decimal("100")).quantize(Decimal("0.01")))


def _parse_int(value: str | None) -> int | None:
    value = _clean(value)
    if value is None:
        return None
    return int(value)


def _read_raw_billing_rows() -> list[dict[str, str]]:
    with open(BILLING_CSV, newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _account_name(account_id: str) -> str:
    with open(ACCOUNTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("account_id") == account_id:
                return row.get("customer_name") or account_id
    return account_id


def _invoice_account_index(raw_rows: list[dict[str, str]]) -> dict[str, str]:
    invoice_accounts: dict[str, set[str]] = {}
    for row in raw_rows:
        invoice_id = _clean(row.get("invoice_id"))
        account_id = _clean(row.get("account_id"))
        if invoice_id and account_id:
            invoice_accounts.setdefault(invoice_id, set()).add(account_id)

    resolved: dict[str, str] = {}
    for invoice_id, account_ids in invoice_accounts.items():
        if len(account_ids) == 1:
            resolved[invoice_id] = next(iter(account_ids))
    return resolved


def load_billing_events() -> list[dict[str, Any]]:
    """Load billing.csv with basic typing and deterministic account resolution."""
    raw_rows = _read_raw_billing_rows()
    account_by_invoice = _invoice_account_index(raw_rows)
    events: list[dict[str, Any]] = []

    for row_number, row in enumerate(raw_rows, start=1):
        event: dict[str, Any] = {field: _clean(value) for field, value in row.items()}
        original_account_id = event.get("account_id")
        invoice_id = event.get("invoice_id")
        resolved_account_id = original_account_id or account_by_invoice.get(invoice_id or "")

        event["row_number"] = row_number
        event["account_id_original"] = original_account_id
        event["account_id"] = resolved_account_id
        event["account_id_was_missing"] = original_account_id is None
        event["account_id_resolved"] = (
            original_account_id is None and resolved_account_id is not None
        )

        timestamp = _parse_timestamp(event.get("timestamp"))
        event["timestamp_date"] = timestamp.date().isoformat() if timestamp else None

        for field in MONEY_FIELDS:
            value = _parse_decimal(event.get(field))
            event[field] = _decimal_to_float(value)
            event[f"{field}_cents"] = _decimal_to_cents(value)

        for field in DECIMAL_FIELDS:
            event[field] = _decimal_to_float(_parse_decimal(event.get(field)))

        for field in INT_FIELDS:
            event[field] = _parse_int(event.get(field))

        events.append(event)

    return events


def _event_date(event: dict[str, Any]) -> date | None:
    return _parse_date(event.get("timestamp_date"))


def filter_billing_events(
    account_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    invoice_id: str | None = None,
    missing_invoice_id_only: bool = False,
) -> list[dict[str, Any]]:
    events = load_billing_events()
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    filtered: list[dict[str, Any]] = []

    for event in events:
        if account_id and event.get("account_id") != account_id:
            continue
        if invoice_id and event.get("invoice_id") != invoice_id:
            continue
        if missing_invoice_id_only and event.get("invoice_id") is not None:
            continue
        event_date = _event_date(event)
        if start and event_date and event_date < start:
            continue
        if end and event_date and event_date > end:
            continue
        filtered.append(event)

    return filtered


def inspect_billing_range(account_id: str | None = None) -> dict[str, Any]:
    events = filter_billing_events(account_id=account_id)
    dates = [event["timestamp_date"] for event in events if event.get("timestamp_date")]
    return {
        "account_id": account_id,
        "row_count": len(events),
        "start_date": min(dates) if dates else None,
        "end_date": max(dates) if dates else None,
        "first_timestamp": events[0].get("timestamp") if events else None,
        "last_timestamp": events[-1].get("timestamp") if events else None,
    }


def read_billing_context(
    account_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    invoice_id: str | None = None,
    around_event_id: str | None = None,
    neighbor_rows: int = 3,
    missing_invoice_id_only: bool = False,
) -> dict[str, Any]:
    if around_event_id:
        all_events = load_billing_events()
        matching_indexes = [
            index
            for index, event in enumerate(all_events)
            if event.get("event_id") == around_event_id
        ]
        if not matching_indexes:
            return {"error": f"Unknown event_id: {around_event_id}", "rows": []}
        center = matching_indexes[0]
        start_index = max(0, center - neighbor_rows)
        end_index = min(len(all_events), center + neighbor_rows + 1)
        events = all_events[start_index:end_index]
    else:
        events = filter_billing_events(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            invoice_id=invoice_id,
            missing_invoice_id_only=missing_invoice_id_only,
        )

    dates = [event["timestamp_date"] for event in events if event.get("timestamp_date")]
    return {
        "account_id": account_id,
        "start_date": start_date,
        "end_date": end_date,
        "invoice_id": invoice_id,
        "missing_invoice_id_only": missing_invoice_id_only,
        "row_count": len(events),
        "returned_start_date": min(dates) if dates else None,
        "returned_end_date": max(dates) if dates else None,
        "truncated": False,
        "rows": events,
    }


def list_invoice_cases(
    account_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    events = filter_billing_events(account_id=account_id, start_date=start_date, end_date=end_date)
    case_map: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        invoice_id = event.get("invoice_id")
        if isinstance(invoice_id, str) and INVOICE_RE.match(invoice_id):
            case_map.setdefault(invoice_id, []).append(event)

    cases = []
    for invoice_id, case_events in sorted(
        case_map.items(), key=lambda item: min(event.get("timestamp") or "" for event in item[1])
    ):
        invoice_events = [
            event for event in case_events if event.get("event_type") == "invoice_issued"
        ]
        cases.append(
            {
                "invoice_id": invoice_id,
                "event_count": len(case_events),
                "first_timestamp": min(event.get("timestamp") or "" for event in case_events),
                "last_timestamp": max(event.get("timestamp") or "" for event in case_events),
                "invoice_issued_event_ids": [
                    event.get("event_id") for event in invoice_events if event.get("event_id")
                ],
            }
        )

    return {
        "account_id": account_id,
        "invoice_case_count": len(cases),
        "invoice_cases": cases,
    }


def calculate_billing(event_ids: list[str], operation: str = "sum_amount") -> dict[str, Any]:
    event_by_id = {event.get("event_id"): event for event in load_billing_events()}
    selected_events = []
    missing_event_ids = []
    for event_id in event_ids:
        event = event_by_id.get(event_id)
        if event is None:
            missing_event_ids.append(event_id)
            continue
        selected_events.append(event)

    if operation != "sum_amount":
        return {"error": f"Unsupported operation: {operation}"}

    total_cents = sum(event.get("amount_cents") or 0 for event in selected_events)
    return {
        "operation": operation,
        "event_ids": event_ids,
        "missing_event_ids": missing_event_ids,
        "amount": _cents_to_amount(total_cents),
        "amount_cents": total_cents,
        "events": selected_events,
    }


def _account_case_dir(account_id: str) -> Path:
    return CASE_DOCS_DIR / account_id


def _case_doc_path(account_id: str, invoice_id: str) -> Path:
    return _account_case_dir(account_id) / f"{invoice_id}.json"


def _scan_doc_path(account_id: str) -> Path:
    return _account_case_dir(account_id) / "missing_invoice_id_scan.json"


def _event_by_id() -> dict[str, dict[str, Any]]:
    return {event.get("event_id"): event for event in load_billing_events()}


def _validate_string_list(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of strings.")


def validate_invoice_case_document(
    case_doc: dict[str, Any],
    account_id: str,
) -> dict[str, Any]:
    """Validate the fixed structured invoice case schema."""
    errors: list[str] = []
    unknown_fields = sorted(set(case_doc) - ALLOWED_CASE_FIELDS)
    missing_fields = sorted(REQUIRED_CASE_FIELDS - set(case_doc))
    event_by_id = _event_by_id()

    if unknown_fields:
        errors.append(f"Unknown fields: {unknown_fields}")
    if missing_fields:
        errors.append(f"Missing required fields: {missing_fields}")

    invoice_id = case_doc.get("invoice_id")
    if not isinstance(invoice_id, str) or not INVOICE_RE.match(invoice_id):
        errors.append("invoice_id must be an INV-* string.")

    if case_doc.get("analysis_status") != "complete":
        errors.append("analysis_status must be 'complete'.")

    for field in [
        "abnormal_tags",
        "case_labels",
        "lifecycle_event_ids",
        "payment_amount_event_ids",
        "refund_amount_event_ids",
        "credit_amount_event_ids",
        "adjustment_amount_event_ids",
        "duplicate_payment_event_ids",
        "settlement_adjustment_event_ids",
        "excluded_event_ids",
        "attached_missing_invoice_id_event_ids",
        "unassigned_missing_invoice_id_event_ids",
    ]:
        if field in case_doc:
            _validate_string_list(case_doc[field], field, errors)

    for field in ["case_summary", "canonical_invoice_event_id", "payment_status", "timing_status"]:
        if field in case_doc and not isinstance(case_doc[field], str):
            errors.append(f"{field} must be a string.")

    settlement_adjustment_cents = case_doc.get("settlement_adjustment_cents", 0)
    if not isinstance(settlement_adjustment_cents, int):
        errors.append("settlement_adjustment_cents must be an integer number of cents.")
        settlement_adjustment_cents = 0
    if settlement_adjustment_cents:
        if abs(settlement_adjustment_cents) > MAX_SETTLEMENT_ADJUSTMENT_CENTS:
            errors.append("settlement_adjustment_cents must not exceed €10.00 in absolute value.")
        if not case_doc.get("abnormal_tags"):
            errors.append("non-zero settlement_adjustment_cents requires abnormal_tags.")
        if not case_doc.get("settlement_adjustment_event_ids"):
            errors.append(
                "non-zero settlement_adjustment_cents requires settlement_adjustment_event_ids."
            )
        reason = case_doc.get("settlement_adjustment_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                "non-zero settlement_adjustment_cents requires settlement_adjustment_reason."
            )

    referenced_fields = [
        "canonical_invoice_event_id",
        "lifecycle_event_ids",
        "payment_amount_event_ids",
        "refund_amount_event_ids",
        "credit_amount_event_ids",
        "adjustment_amount_event_ids",
        "duplicate_payment_event_ids",
        "settlement_adjustment_event_ids",
        "excluded_event_ids",
        "attached_missing_invoice_id_event_ids",
        "unassigned_missing_invoice_id_event_ids",
    ]
    referenced_event_ids: list[str] = []
    for field in referenced_fields:
        value = case_doc.get(field)
        if isinstance(value, str):
            referenced_event_ids.append(value)
        elif isinstance(value, list):
            referenced_event_ids.extend(value)

    for event_id in referenced_event_ids:
        event = event_by_id.get(event_id)
        if event is None:
            errors.append(f"Unknown event_id: {event_id}")
            continue
        event_invoice_id = event.get("invoice_id")
        if (
            invoice_id
            and isinstance(event_invoice_id, str)
            and INVOICE_RE.match(event_invoice_id)
            and event_invoice_id != invoice_id
        ):
            errors.append(f"{event_id} belongs to {event_invoice_id}, not {invoice_id}.")
        if event.get("account_id") not in {account_id, None}:
            errors.append(
                f"{event_id} belongs to account {event.get('account_id')}, not {account_id}."
            )

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "invoice_id": invoice_id,
    }


def save_invoice_case(case_doc: dict[str, Any], account_id: str) -> dict[str, Any]:
    validation = validate_invoice_case_document(case_doc, account_id=account_id)
    if validation["status"] != "PASS":
        return validation

    output_dir = _account_case_dir(account_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = _case_doc_path(account_id, case_doc["invoice_id"])
    output_path.write_text(_json(case_doc) + "\n", encoding="utf-8")

    return {
        "status": "PASS",
        "invoice_id": case_doc["invoice_id"],
        "path": str(output_path),
    }


def load_invoice_case_documents(account_id: str) -> list[dict[str, Any]]:
    case_dir = _account_case_dir(account_id)
    if not case_dir.exists():
        return []
    case_docs = []
    for path in sorted(case_dir.glob("INV-*.json")):
        case_docs.append(json.loads(path.read_text(encoding="utf-8")))
    return case_docs


def _event_ids(case_doc: dict[str, Any], field: str) -> list[str]:
    value = case_doc.get(field, [])
    return value if isinstance(value, list) else []


def _event_ids_to_events(
    event_by_id: dict[str, dict[str, Any]], event_ids: list[str]
) -> list[dict[str, Any]]:
    return [event_by_id[event_id] for event_id in event_ids if event_id in event_by_id]


def _canonical_invoice_event(case_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    invoice_events = [
        event for event in case_events if event.get("event_type") == "invoice_issued"
    ]
    corrected_events = [
        event for event in case_events if event.get("event_type") == "invoice_corrected"
    ]
    if corrected_events:
        return _latest(corrected_events)
    if not invoice_events:
        return None
    return sorted(invoice_events, key=lambda event: event.get("timestamp") or "")[0]


def _analysis_end_date_for_events(events: list[dict[str, Any]]) -> str | None:
    return max(
        [event["timestamp_date"] for event in events if event.get("timestamp_date")], default=None
    )


def _split_settlement_payments(
    payment_events: list[dict[str, Any]],
    invoice_amount_cents: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split payments into valid settlement events and duplicate/overpayment events."""
    valid_payments: list[dict[str, Any]] = []
    duplicate_payments: list[dict[str, Any]] = []
    cumulative_cents = 0

    for event in sorted(payment_events, key=lambda item: item.get("timestamp") or ""):
        amount_cents = event.get("amount_cents") or 0
        if cumulative_cents >= invoice_amount_cents:
            duplicate_payments.append(event)
            continue
        valid_payments.append(event)
        cumulative_cents += amount_cents

    return valid_payments, duplicate_payments


def _derive_case_financials(
    canonical_event: dict[str, Any],
    valid_payment_events: list[dict[str, Any]],
    analysis_end_date: str | None,
) -> dict[str, Any]:
    invoice_amount_cents = canonical_event.get("amount_cents") or 0
    valid_payment_events = sorted(
        valid_payment_events, key=lambda event: event.get("timestamp") or ""
    )
    valid_paid_raw_cents = sum(event.get("amount_cents") or 0 for event in valid_payment_events)
    valid_paid_cents = min(max(valid_paid_raw_cents, 0), invoice_amount_cents)
    outstanding_cents = max(invoice_amount_cents - valid_paid_cents, 0)

    paid_date = None
    cumulative_cents = 0
    for event in valid_payment_events:
        cumulative_cents += event.get("amount_cents") or 0
        if cumulative_cents >= invoice_amount_cents:
            paid_date = event.get("paid_date") or event.get("timestamp_date")
            break

    due_date = canonical_event.get("due_date")
    days_past_due = None
    if due_date:
        end_for_delta = paid_date if paid_date else analysis_end_date
        if end_for_delta:
            days_past_due = (_parse_date(end_for_delta) - _parse_date(due_date)).days

    if outstanding_cents == 0:
        payment_status = "fully_paid"
    elif valid_paid_cents > 0:
        payment_status = "partially_paid"
    else:
        payment_status = "outstanding"

    if days_past_due is None:
        timing_status = "unknown"
    elif days_past_due > 0:
        timing_status = "late"
    elif payment_status == "fully_paid":
        timing_status = "on_time_or_early"
    else:
        timing_status = "unpaid"

    return {
        "invoice_amount_cents": invoice_amount_cents,
        "valid_paid_amount_cents": valid_paid_cents,
        "base_outstanding_amount_cents": outstanding_cents,
        "effective_outstanding_amount_cents": outstanding_cents,
        "outstanding_amount_cents": outstanding_cents,
        "settlement_adjustment_cents": 0,
        "settlement_status": "settled" if outstanding_cents == 0 else "open",
        "paid_date": paid_date,
        "days_past_due": days_past_due,
        "payment_status": payment_status,
        "timing_status": timing_status,
    }


def _apply_settlement_adjustment(
    financials: dict[str, Any],
    settlement_adjustment_cents: int = 0,
) -> dict[str, Any]:
    adjusted = dict(financials)
    base_outstanding_cents = adjusted["base_outstanding_amount_cents"]
    effective_outstanding_cents = base_outstanding_cents + settlement_adjustment_cents
    adjusted["settlement_adjustment_cents"] = settlement_adjustment_cents
    adjusted["effective_outstanding_amount_cents"] = effective_outstanding_cents
    adjusted["outstanding_amount_cents"] = effective_outstanding_cents
    if effective_outstanding_cents == 0:
        adjusted["settlement_status"] = "settled"
    elif adjusted["valid_paid_amount_cents"] > 0 or settlement_adjustment_cents:
        adjusted["settlement_status"] = "partially_settled"
    else:
        adjusted["settlement_status"] = "open"
    return adjusted


def _financials_to_case_row(
    invoice_id: str,
    canonical_event: dict[str, Any],
    financials: dict[str, Any],
    case_labels: list[str],
    event_ids: list[str],
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "invoice_id": invoice_id,
        "canonical_invoice_event_id": canonical_event["event_id"],
        "invoice_amount": _cents_to_amount(financials["invoice_amount_cents"]),
        "invoice_amount_cents": financials["invoice_amount_cents"],
        "valid_paid_amount": _cents_to_amount(financials["valid_paid_amount_cents"]),
        "valid_paid_amount_cents": financials["valid_paid_amount_cents"],
        "base_outstanding_amount": _cents_to_amount(financials["base_outstanding_amount_cents"]),
        "base_outstanding_amount_cents": financials["base_outstanding_amount_cents"],
        "settlement_adjustment": _cents_to_amount(financials["settlement_adjustment_cents"]),
        "settlement_adjustment_cents": financials["settlement_adjustment_cents"],
        "effective_outstanding_amount": _cents_to_amount(
            financials["effective_outstanding_amount_cents"]
        ),
        "effective_outstanding_amount_cents": financials["effective_outstanding_amount_cents"],
        "outstanding_amount": _cents_to_amount(financials["outstanding_amount_cents"]),
        "outstanding_amount_cents": financials["outstanding_amount_cents"],
        "due_date": canonical_event.get("due_date"),
        "paid_date": financials["paid_date"],
        "days_past_due": financials["days_past_due"],
        "payment_status": financials["payment_status"],
        "settlement_status": financials["settlement_status"],
        "timing_status": financials["timing_status"],
        "case_labels": case_labels,
        "event_ids": event_ids,
    }
    if extra_fields:
        row.update(extra_fields)
    return row


def _scan_missing_invoice_ids(
    account_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    missing_events = filter_billing_events(
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        missing_invoice_id_only=True,
    )
    known_event_ids = {event["event_id"] for event in missing_events if event.get("event_id")}
    assignments = assignments or []
    assignment_errors = []

    for assignment in assignments:
        event_id = assignment.get("event_id")
        invoice_id = assignment.get("invoice_id")
        if event_id not in known_event_ids:
            assignment_errors.append(
                f"{event_id} is not a missing-invoice-id event for {account_id}."
            )
        if invoice_id is not None and (
            not isinstance(invoice_id, str) or not INVOICE_RE.match(invoice_id)
        ):
            assignment_errors.append(f"{event_id} assignment invoice_id must be INV-* or null.")

    scan_doc = {
        "account_id": account_id,
        "start_date": start_date,
        "end_date": end_date,
        "scan_completed": True,
        "missing_invoice_id_event_count": len(missing_events),
        "missing_invoice_id_event_ids": [
            event.get("event_id") for event in missing_events if event.get("event_id")
        ],
        "assignments": assignments,
        "unassigned_event_ids": [
            event.get("event_id")
            for event in missing_events
            if event.get("event_id")
            and event.get("event_id")
            not in {assignment.get("event_id") for assignment in assignments}
        ],
        "errors": assignment_errors,
    }

    output_dir = _account_case_dir(account_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    _scan_doc_path(account_id).write_text(_json(scan_doc) + "\n", encoding="utf-8")
    _apply_missing_invoice_assignments(account_id, assignments)
    return scan_doc


def _apply_missing_invoice_assignments(account_id: str, assignments: list[dict[str, Any]]) -> None:
    assignments_by_invoice: dict[str, list[str]] = {}
    unassigned: list[str] = []
    for assignment in assignments:
        event_id = assignment.get("event_id")
        invoice_id = assignment.get("invoice_id")
        if not isinstance(event_id, str):
            continue
        if isinstance(invoice_id, str) and INVOICE_RE.match(invoice_id):
            assignments_by_invoice.setdefault(invoice_id, []).append(event_id)
        elif invoice_id is None:
            unassigned.append(event_id)

    for invoice_id, event_ids in assignments_by_invoice.items():
        path = _case_doc_path(account_id, invoice_id)
        if not path.exists():
            continue
        case_doc = json.loads(path.read_text(encoding="utf-8"))
        existing = set(case_doc.get("attached_missing_invoice_id_event_ids", []))
        case_doc["attached_missing_invoice_id_event_ids"] = sorted(existing | set(event_ids))
        path.write_text(_json(case_doc) + "\n", encoding="utf-8")

    if unassigned:
        for path in sorted(_account_case_dir(account_id).glob("INV-*.json")):
            case_doc = json.loads(path.read_text(encoding="utf-8"))
            existing = set(case_doc.get("unassigned_missing_invoice_id_event_ids", []))
            case_doc["unassigned_missing_invoice_id_event_ids"] = sorted(
                existing | set(unassigned)
            )
            path.write_text(_json(case_doc) + "\n", encoding="utf-8")


def _requires_agent_review(case_events: list[dict[str, Any]], financials: dict[str, Any]) -> bool:
    event_types = {event.get("event_type") for event in case_events}
    if len([event for event in case_events if event.get("event_type") == "payment_received"]) > 1:
        return True
    if "refund_initiated" in event_types or "refund_completed" in event_types:
        return True
    if len([event for event in case_events if event.get("event_type") == "invoice_issued"]) > 1:
        return True
    if "dispute_opened" in event_types or "dispute_resolved" in event_types:
        return True
    if "invoice_corrected" in event_types:
        return True
    if (
        any(event.get("credit_note_ref") for event in case_events)
        or "credit_applied" in event_types
    ):
        return True
    if any(
        event.get("account_id_was_missing") or event.get("invoice_id") is None
        for event in case_events
    ):
        return True
    if "reconciliation_manual" in event_types:
        return True
    if "adjustment" in event_types:
        return True
    return financials["payment_status"] != "fully_paid"


def _draft_case_summary(invoice_id: str, financials: dict[str, Any], labels: list[str]) -> str:
    if labels == ["normal"]:
        return f"{invoice_id} follows a normal invoice, payment, and reconciliation lifecycle."
    return (
        f"{invoice_id} draft case includes: {', '.join(labels)}. "
        "Review semantic labels and narrative before customer-facing use."
    )


def _draft_settlement_adjustment(
    case_events: list[dict[str, Any]],
    financials: dict[str, Any],
) -> dict[str, Any]:
    base_outstanding_cents = financials["base_outstanding_amount_cents"]
    if base_outstanding_cents <= 0 or base_outstanding_cents > MAX_SETTLEMENT_ADJUSTMENT_CENTS:
        return {}

    adjustment_events = [
        event
        for event in case_events
        if event.get("event_type") == "adjustment"
        and abs(event.get("amount_cents") or 0) <= MAX_SETTLEMENT_ADJUSTMENT_CENTS
    ]
    writeoff_events = [
        event
        for event in adjustment_events
        if any(
            marker in f"{event.get('description') or ''} {event.get('notes') or ''}".lower()
            for marker in ["write-off", "writeoff", "rounding"]
        )
    ]
    if not writeoff_events:
        return {}

    supported_cents = sum(abs(event.get("amount_cents") or 0) for event in writeoff_events)
    if supported_cents < base_outstanding_cents:
        return {}

    return {
        "abnormal_tags": ["rounding_writeoff"],
        "settlement_adjustment_cents": -base_outstanding_cents,
        "settlement_adjustment_event_ids": [
            event["event_id"] for event in writeoff_events if event.get("event_id")
        ],
        "settlement_adjustment_reason": (
            f"{_format_eur(base_outstanding_cents)} residual balance was written off "
            "by a small rounding adjustment."
        ),
    }


def build_invoice_case_documents(
    account_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    events = filter_billing_events(account_id=account_id, start_date=start_date, end_date=end_date)
    analysis_end_date = _analysis_end_date_for_events(events)
    case_listing = list_invoice_cases(
        account_id=account_id, start_date=start_date, end_date=end_date
    )
    requires_review: list[str] = []
    errors: list[str] = []
    saved_count = 0

    for case in case_listing["invoice_cases"]:
        invoice_id = case["invoice_id"]
        case_events = [event for event in events if event.get("invoice_id") == invoice_id]
        canonical_event = _canonical_invoice_event(case_events)
        if canonical_event is None:
            errors.append(f"{invoice_id} has no canonical invoice event.")
            continue

        payment_events = [
            event for event in case_events if event.get("event_type") == "payment_received"
        ]
        valid_payments, duplicate_payments = _split_settlement_payments(
            payment_events,
            canonical_event.get("amount_cents") or 0,
        )
        financials = _derive_case_financials(
            canonical_event,
            valid_payments,
            analysis_end_date=analysis_end_date,
        )
        settlement_adjustment = _draft_settlement_adjustment(case_events, financials)
        labels = _case_labels_for_financials(
            case_events,
            valid_payments,
            duplicate_payments,
        ) or ["normal"]
        if settlement_adjustment:
            labels = sorted(set(labels) | set(settlement_adjustment["abnormal_tags"]))
        refund_completed_ids = [
            event["event_id"]
            for event in case_events
            if event.get("event_type") == "refund_completed"
        ]
        adjustment_ids = [
            event["event_id"] for event in case_events if event.get("event_type") == "adjustment"
        ]
        case_doc = {
            "invoice_id": invoice_id,
            "analysis_status": "complete",
            "case_labels": labels,
            "case_summary": _draft_case_summary(invoice_id, financials, labels),
            "canonical_invoice_event_id": canonical_event["event_id"],
            "lifecycle_event_ids": [
                event["event_id"] for event in case_events if event.get("event_id")
            ],
            "payment_amount_event_ids": [
                event["event_id"] for event in valid_payments if event.get("event_id")
            ],
            "refund_amount_event_ids": refund_completed_ids,
            "duplicate_payment_event_ids": [
                event["event_id"] for event in duplicate_payments if event.get("event_id")
            ],
            "adjustment_amount_event_ids": adjustment_ids,
            "payment_status": financials["payment_status"],
            "timing_status": financials["timing_status"],
        }
        case_doc.update(settlement_adjustment)
        save_result = save_invoice_case(case_doc, account_id=account_id)
        if save_result["status"] == "PASS":
            saved_count += 1
        else:
            errors.extend(save_result["errors"])

        if _requires_agent_review(case_events, financials):
            requires_review.append(invoice_id)

    return {
        "status": "PASS" if not errors else "FAIL",
        "account_id": account_id,
        "case_document_count": saved_count,
        "case_document_dir": str(_account_case_dir(account_id)),
        "requires_agent_review": requires_review,
        "errors": errors,
    }


def aggregate_billing_summary_from_case_documents(
    account_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    case_docs = load_invoice_case_documents(account_id)
    event_by_id = _event_by_id()
    analysis_end_date = end_date or inspect_billing_range(account_id=account_id)["end_date"]
    invoice_cases = []
    realized_refund_cents = 0

    for case_doc in case_docs:
        if case_doc.get("analysis_status") != "complete":
            continue
        invoice_id = case_doc["invoice_id"]
        canonical_event = event_by_id.get(case_doc["canonical_invoice_event_id"])
        if canonical_event is None:
            continue

        payment_events = _event_ids_to_events(
            event_by_id, _event_ids(case_doc, "payment_amount_event_ids")
        )
        refund_events = _event_ids_to_events(
            event_by_id, _event_ids(case_doc, "refund_amount_event_ids")
        )
        financials = _derive_case_financials(
            canonical_event,
            payment_events,
            analysis_end_date=analysis_end_date,
        )
        settlement_adjustment_cents = case_doc.get("settlement_adjustment_cents") or 0
        financials = _apply_settlement_adjustment(
            financials,
            settlement_adjustment_cents=settlement_adjustment_cents,
        )
        realized_refund_cents += sum(
            abs(event.get("amount_cents") or 0) for event in refund_events
        )

        invoice_cases.append(
            _financials_to_case_row(
                invoice_id=invoice_id,
                canonical_event=canonical_event,
                financials=financials,
                case_labels=case_doc["case_labels"],
                event_ids=case_doc["lifecycle_event_ids"],
                extra_fields={
                    "abnormal_tags": case_doc.get("abnormal_tags", []),
                    "payment_amount_event_ids": _event_ids(case_doc, "payment_amount_event_ids"),
                    "settlement_adjustment_event_ids": _event_ids(
                        case_doc, "settlement_adjustment_event_ids"
                    ),
                    "settlement_adjustment_reason": case_doc.get("settlement_adjustment_reason"),
                },
            )
        )

    total_invoiced_cents = sum(case["invoice_amount_cents"] for case in invoice_cases)
    total_paid_cents = sum(case["valid_paid_amount_cents"] for case in invoice_cases)
    total_outstanding_cents = sum(case["outstanding_amount_cents"] for case in invoice_cases)
    paid_late_cases = [
        case
        for case in invoice_cases
        if case["payment_status"] == "fully_paid" and (case.get("days_past_due") or 0) > 0
    ]
    overdue_outstanding_cases = [
        case
        for case in invoice_cases
        if case["outstanding_amount_cents"] > 0 and (case.get("days_past_due") or 0) > 0
    ]
    not_yet_due_outstanding_cases = [
        case
        for case in invoice_cases
        if case["outstanding_amount_cents"] > 0 and (case.get("days_past_due") or 0) <= 0
    ]
    scan_path = _scan_doc_path(account_id)
    scan_doc = json.loads(scan_path.read_text(encoding="utf-8")) if scan_path.exists() else {}

    return {
        "account_id": account_id,
        "source": "billing_case_documents",
        "start_date": start_date,
        "end_date": end_date,
        "source_case_document_count": len(case_docs),
        "invoice_count": len(invoice_cases),
        "total_invoiced": _cents_to_amount(total_invoiced_cents),
        "total_invoiced_cents": total_invoiced_cents,
        "total_valid_paid": _cents_to_amount(total_paid_cents),
        "total_valid_paid_cents": total_paid_cents,
        "total_outstanding": _cents_to_amount(total_outstanding_cents),
        "total_outstanding_cents": total_outstanding_cents,
        "late_invoice_count": len(
            [case for case in invoice_cases if case["timing_status"] == "late"]
        ),
        "paid_late_invoice_count": len(paid_late_cases),
        "outstanding_invoice_count": len(
            [case for case in invoice_cases if case["outstanding_amount_cents"] > 0]
        ),
        "overdue_outstanding_invoice_count": len(overdue_outstanding_cases),
        "not_yet_due_outstanding_invoice_count": len(not_yet_due_outstanding_cases),
        "missing_invoice_id_scan_completed": bool(scan_doc.get("scan_completed")),
        "missing_invoice_id_event_count": scan_doc.get("missing_invoice_id_event_count", 0),
        "missing_invoice_id_event_ids": scan_doc.get("missing_invoice_id_event_ids", []),
        "realized_refund_total": _cents_to_amount(realized_refund_cents),
        "realized_refund_total_cents": realized_refund_cents,
        "invoice_cases": invoice_cases,
    }


def _latest(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    return sorted(events, key=lambda event: event.get("timestamp") or "")[-1]


def _case_labels(events: list[dict[str, Any]]) -> list[str]:
    event_types = {event.get("event_type") for event in events}
    statuses = {event.get("status") for event in events}
    labels: set[str] = set()

    if any((event.get("days_past_due") or 0) > 0 for event in events):
        labels.add("late_payment")
    if "payment_reminder_sent" in event_types:
        labels.add("payment_reminder")
    if "reconciliation_exception" in event_types:
        labels.add("reconciliation_exception")
    if "reconciliation_manual" in event_types:
        labels.add("manual_reconciliation")
    if "refund_completed" in event_types or "refund_initiated" in event_types:
        labels.add("refund")
    if "dispute_opened" in event_types or "dispute_resolved" in event_types:
        labels.add("dispute")
    if "invoice_corrected" in event_types:
        labels.add("invoice_correction")
    if any(event.get("credit_note_ref") for event in events):
        labels.add("credit_applied")
    if len([event for event in events if event.get("event_type") == "invoice_issued"]) > 1:
        labels.add("duplicate_or_resubmitted_invoice")
    if "partial" in statuses:
        labels.add("partial_payment")
    if "adjustment" in event_types:
        labels.add("adjustment")

    return sorted(labels)


def _case_labels_for_financials(
    case_events: list[dict[str, Any]],
    valid_payments: list[dict[str, Any]],
    duplicate_payments: list[dict[str, Any]],
) -> list[str]:
    labels = set(_case_labels(case_events))
    refund_events = [
        event
        for event in case_events
        if event.get("event_type") in {"refund_initiated", "refund_completed"}
    ]

    if duplicate_payments and refund_events:
        labels.add("duplicate_payment")
    if len(valid_payments) > 1:
        labels.add("multiple_payments")

    return sorted(labels)


def aggregate_billing_summary(
    account_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    use_case_documents: bool = False,
) -> dict[str, Any]:
    if use_case_documents:
        return aggregate_billing_summary_from_case_documents(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
        )

    events = filter_billing_events(account_id=account_id, start_date=start_date, end_date=end_date)
    case_listing = list_invoice_cases(
        account_id=account_id, start_date=start_date, end_date=end_date
    )
    analysis_end_date = _analysis_end_date_for_events(events)

    invoice_cases = []
    for case in case_listing["invoice_cases"]:
        invoice_id = case["invoice_id"]
        case_events = [event for event in events if event.get("invoice_id") == invoice_id]
        canonical_event = _canonical_invoice_event(case_events)
        if canonical_event is None:
            continue

        payment_events = [
            event for event in case_events if event.get("event_type") == "payment_received"
        ]
        valid_payments, _duplicate_payments = _split_settlement_payments(
            payment_events,
            canonical_event.get("amount_cents") or 0,
        )
        financials = _derive_case_financials(
            canonical_event,
            valid_payments,
            analysis_end_date=analysis_end_date,
        )
        invoice_cases.append(
            _financials_to_case_row(
                invoice_id=invoice_id,
                canonical_event=canonical_event,
                financials=financials,
                case_labels=_case_labels_for_financials(
                    case_events,
                    valid_payments,
                    _duplicate_payments,
                ),
                event_ids=[event["event_id"] for event in case_events if event.get("event_id")],
            )
        )

    total_invoiced_cents = sum(case["invoice_amount_cents"] for case in invoice_cases)
    total_paid_cents = sum(case["valid_paid_amount_cents"] for case in invoice_cases)
    total_outstanding_cents = sum(case["outstanding_amount_cents"] for case in invoice_cases)
    paid_late_cases = [
        case
        for case in invoice_cases
        if case["payment_status"] == "fully_paid" and (case.get("days_past_due") or 0) > 0
    ]
    overdue_outstanding_cases = [
        case
        for case in invoice_cases
        if case["outstanding_amount_cents"] > 0 and (case.get("days_past_due") or 0) > 0
    ]
    not_yet_due_outstanding_cases = [
        case
        for case in invoice_cases
        if case["outstanding_amount_cents"] > 0 and (case.get("days_past_due") or 0) <= 0
    ]

    missing_invoice_events = filter_billing_events(
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        missing_invoice_id_only=True,
    )
    credit_note_events = [
        event
        for event in events
        if isinstance(event.get("invoice_id"), str) and CREDIT_NOTE_RE.match(event["invoice_id"])
    ]

    return {
        "account_id": account_id,
        "source": "billing.csv",
        "start_date": min(
            [event["timestamp_date"] for event in events if event.get("timestamp_date")],
            default=None,
        ),
        "end_date": max(
            [event["timestamp_date"] for event in events if event.get("timestamp_date")],
            default=None,
        ),
        "source_row_count": len(events),
        "invoice_count": len(invoice_cases),
        "total_invoiced": _cents_to_amount(total_invoiced_cents),
        "total_invoiced_cents": total_invoiced_cents,
        "total_valid_paid": _cents_to_amount(total_paid_cents),
        "total_valid_paid_cents": total_paid_cents,
        "total_outstanding": _cents_to_amount(total_outstanding_cents),
        "total_outstanding_cents": total_outstanding_cents,
        "late_invoice_count": len(
            [case for case in invoice_cases if case["timing_status"] == "late"]
        ),
        "paid_late_invoice_count": len(paid_late_cases),
        "outstanding_invoice_count": len(
            [case for case in invoice_cases if case["outstanding_amount_cents"] > 0]
        ),
        "overdue_outstanding_invoice_count": len(overdue_outstanding_cases),
        "not_yet_due_outstanding_invoice_count": len(not_yet_due_outstanding_cases),
        "credit_note_count": len(credit_note_events),
        "missing_invoice_id_scan_completed": True,
        "missing_invoice_id_event_count": len(missing_invoice_events),
        "missing_invoice_id_event_ids": [
            event.get("event_id") for event in missing_invoice_events if event.get("event_id")
        ],
        "invoice_cases": invoice_cases,
    }


def _format_eur(cents: int | None) -> str:
    return f"€{_cents_to_amount(cents or 0):,.2f}"


def _format_table_amount(cents: int | None) -> str:
    return f"{_cents_to_amount(cents or 0):,.2f}"


def _case_list(cases: list[dict[str, Any]]) -> str:
    return ", ".join(case["invoice_id"] for case in cases)


def _case_events(
    case: dict[str, Any],
    event_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return _event_ids_to_events(event_by_id, case.get("event_ids", []))


def _sentence(value: str | None) -> str | None:
    value = _clean(value)
    if value is None:
        return None
    return value.rstrip(".")


def _clip(value: str, max_length: int = 220) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def _is_credit_context(event: dict[str, Any]) -> bool:
    if event.get("credit_note_ref"):
        return True
    text = f"{event.get('description') or ''} {event.get('notes') or ''}".lower()
    return "not applied" in text or "will be applied" in text


def _describe_duplicate_payment_case(
    case: dict[str, Any],
    events: list[dict[str, Any]],
) -> str:
    duplicate_payments = [
        event
        for event in events
        if event.get("event_type") == "payment_received"
        and (
            event.get("status") == "overpayment"
            or "duplicate" in (event.get("description") or "").lower()
            or "duplicate" in (event.get("notes") or "").lower()
        )
    ]
    refunds = [
        event
        for event in events
        if event.get("event_type") == "refund_completed"
        or event.get("status") == "refund_complete"
    ]
    duplicate_text = (
        f"an extra payment of {_format_eur(duplicate_payments[0].get('amount_cents'))}"
        if duplicate_payments
        else "an extra payment"
    )
    refund_text = (
        f" and a refund of {_format_eur(abs(refunds[0].get('amount_cents') or 0))} "
        f"was completed on {refunds[0].get('timestamp_date')}"
        if refunds
        else ""
    )
    return (
        f"{case['invoice_id']}: the invoice was already settled, then {duplicate_text} "
        f"was received as a duplicate{refund_text}."
    )


def _describe_multi_payment_case(case: dict[str, Any], events: list[dict[str, Any]]) -> str:
    payments = [
        event
        for event in sorted(events, key=lambda item: item.get("timestamp") or "")
        if event.get("event_type") == "payment_received" and event.get("status") != "overpayment"
    ]
    amounts = ", ".join(_format_eur(event.get("amount_cents")) for event in payments)
    raw_notes = " ".join(
        event.get("notes") or event.get("description") or "" for event in payments
    ).lower()
    if "department" in raw_notes or "cost center" in raw_notes:
        note_text = " Payments came from separate departments or cost centers."
    elif "split" in raw_notes or "partial" in raw_notes:
        note_text = " The customer split one invoice settlement into multiple payments."
    else:
        note_text = ""
    return (
        f"{case['invoice_id']}: the invoice was settled through "
        f"{len(payments)} valid payments ({amounts}), so this is a multi-payment "
        f"settlement rather than a duplicate payment.{note_text}"
    )


def _describe_dispute_case(case: dict[str, Any], events: list[dict[str, Any]]) -> str:
    dispute = next(
        (event for event in events if event.get("event_type") == "dispute_opened"),
        None,
    )
    correction = next(
        (event for event in events if event.get("event_type") == "invoice_corrected"),
        None,
    )
    details = _sentence((dispute or {}).get("description") or (dispute or {}).get("notes"))
    correction_text = ""
    if correction:
        correction_text = (
            f" A corrected invoice was issued for {_format_eur(correction.get('amount_cents'))}."
        )
    return f"{case['invoice_id']}: {details or 'invoice dispute was opened'}.{correction_text}"


def _describe_resubmitted_invoice_case(
    case: dict[str, Any],
    events: list[dict[str, Any]],
) -> str:
    invoice_events = [
        event
        for event in sorted(events, key=lambda item: item.get("timestamp") or "")
        if event.get("event_type") == "invoice_issued"
    ]
    if len(invoice_events) < 2:
        return f"{case['invoice_id']}: duplicate or resubmitted invoice event was identified."
    original = invoice_events[0]
    resubmitted = invoice_events[-1]
    return (
        f"{case['invoice_id']}: the original invoice amount was "
        f"{_format_eur(original.get('amount_cents'))}; a later AP-portal resubmission "
        f"showed {_format_eur(resubmitted.get('amount_cents'))}, but the valid settled "
        f"amount remains {_format_eur(case.get('invoice_amount_cents'))}."
    )


def _describe_credit_or_adjustment_case(
    case: dict[str, Any],
    events: list[dict[str, Any]],
) -> str | None:
    credit_events = [event for event in events if _is_credit_context(event)]
    adjustment_events = [event for event in events if event.get("event_type") == "adjustment"]
    parts: list[str] = []

    applied_credit = next((event for event in credit_events if event.get("credit_note_ref")), None)
    if applied_credit:
        note = _sentence(applied_credit.get("notes") or applied_credit.get("description"))
        parts.append(
            f"credit {applied_credit.get('credit_note_ref')} was applied, producing a net "
            f"invoice amount of {_format_eur(applied_credit.get('amount_cents'))}"
            + (f"; {note}" if note else "")
        )
    elif credit_events:
        note = _sentence(credit_events[0].get("notes") or credit_events[0].get("description"))
        text = f"{credit_events[0].get('description') or ''} {credit_events[0].get('notes') or ''}"
        ref_match = re.search(r"CN-\d{4}-[A-Z]+-\d{3}", text)
        amount_match = re.search(r"€[0-9,.]+", text)
        if "not applied" in text.lower() and ref_match:
            amount_text = f" ({amount_match.group(0)})" if amount_match else ""
            parts.append(
                f"SLA credit {ref_match.group(0)}{amount_text} was not applied to this "
                "invoice and was deferred to the next invoice"
            )
        else:
            parts.append(_clip(note or "credit-related billing note was recorded"))

    for adjustment in adjustment_events:
        detail = _sentence(adjustment.get("description") or adjustment.get("notes"))
        amount_cents = adjustment.get("amount_cents") or 0
        if amount_cents < 0:
            adjustment_text = f"discount or reduction of {_format_eur(abs(amount_cents))}"
        else:
            adjustment_text = f"adjustment of {_format_eur(amount_cents)}"
        parts.append(f"{adjustment_text} was applied" + (f" for {detail}" if detail else ""))

    if not parts:
        return None
    return f"{case['invoice_id']}: {'; '.join(parts)}."


def build_billing_pdf_sections(
    summary: dict[str, Any],
    include_chart: bool = False,
) -> dict[str, Any]:
    """Build customer-facing billing PDF sections from a verified aggregate summary."""
    account_id = summary["account_id"]
    account_name = _account_name(account_id)
    invoice_cases = sorted(summary.get("invoice_cases", []), key=lambda case: case["invoice_id"])
    event_by_id = _event_by_id()
    billing_range = inspect_billing_range(account_id=account_id)
    start_date = summary.get("start_date") or billing_range.get("start_date")
    end_date = summary.get("end_date") or billing_range.get("end_date")

    paid_late_cases = [
        case
        for case in invoice_cases
        if case["payment_status"] == "fully_paid" and (case.get("days_past_due") or 0) > 0
    ]
    outstanding_cases = [
        case for case in invoice_cases if case.get("outstanding_amount_cents", 0) > 0
    ]
    overdue_outstanding_cases = [
        case for case in outstanding_cases if (case.get("days_past_due") or 0) > 0
    ]
    not_yet_due_outstanding_cases = [
        case for case in outstanding_cases if (case.get("days_past_due") or 0) <= 0
    ]

    rows = [
        [
            case["invoice_id"],
            _format_table_amount(case.get("invoice_amount_cents")),
            _format_table_amount(case.get("valid_paid_amount_cents")),
            _format_table_amount(case.get("outstanding_amount_cents")),
            case.get("settlement_status") or case["payment_status"],
        ]
        for case in invoice_cases
    ]

    summary_text = (
        f"{account_name} ({account_id}) billing data covers {start_date} through {end_date}. "
        f"The account has {summary['invoice_count']} invoices, with total invoiced of "
        f"{_format_eur(summary.get('total_invoiced_cents'))}, total valid paid of "
        f"{_format_eur(summary.get('total_valid_paid_cents'))}, and total outstanding of "
        f"{_format_eur(summary.get('total_outstanding_cents'))}. "
        f"{len(paid_late_cases)} invoices were eventually paid after their due dates. "
        f"{len(outstanding_cases)} invoices are currently outstanding: "
        f"{len(overdue_outstanding_cases)} overdue and "
        f"{len(not_yet_due_outstanding_cases)} not yet due at the data cutoff."
    )

    findings: list[str] = []
    if paid_late_cases:
        findings.append(
            f"Late-payment pattern: {len(paid_late_cases)} invoices were eventually "
            f"paid after the due date ({_case_list(paid_late_cases)})."
        )
    if outstanding_cases:
        parts = []
        for case in overdue_outstanding_cases:
            parts.append(
                f"{case['invoice_id']} is overdue with "
                f"{_format_eur(case.get('outstanding_amount_cents'))} outstanding"
            )
        for case in not_yet_due_outstanding_cases:
            parts.append(
                f"{case['invoice_id']} is unpaid but not yet due, with "
                f"{_format_eur(case.get('outstanding_amount_cents'))} outstanding"
            )
        findings.append(f"Outstanding invoices: {'; '.join(parts)}.")

    duplicate_cases = [
        case for case in invoice_cases if "duplicate_payment" in set(case.get("case_labels", []))
    ]
    if duplicate_cases:
        findings.append(
            "Duplicate payment requiring refund: "
            + " ".join(
                _describe_duplicate_payment_case(case, _case_events(case, event_by_id))
                for case in duplicate_cases
            )
        )

    multi_payment_cases = [
        case
        for case in invoice_cases
        if "multiple_payments" in set(case.get("case_labels", []))
        and "duplicate_payment" not in set(case.get("case_labels", []))
    ]
    if multi_payment_cases:
        findings.append(
            "Multi-payment settlements: "
            + " ".join(
                _describe_multi_payment_case(case, _case_events(case, event_by_id))
                for case in multi_payment_cases
            )
        )

    dispute_cases = [
        case
        for case in invoice_cases
        if {"dispute", "invoice_correction"}.intersection(set(case.get("case_labels", [])))
    ]
    if dispute_cases:
        findings.append(
            "Invoice disputes and corrections: "
            + " ".join(
                _describe_dispute_case(case, _case_events(case, event_by_id))
                for case in dispute_cases
            )
        )

    resubmitted_cases = [
        case
        for case in invoice_cases
        if "duplicate_or_resubmitted_invoice" in set(case.get("case_labels", []))
    ]
    if resubmitted_cases:
        findings.append(
            "Duplicate or resubmitted invoices: "
            + " ".join(
                _describe_resubmitted_invoice_case(case, _case_events(case, event_by_id))
                for case in resubmitted_cases
            )
        )

    credit_or_adjustment_findings = [
        finding
        for case in invoice_cases
        if (finding := _describe_credit_or_adjustment_case(case, _case_events(case, event_by_id)))
    ]
    if credit_or_adjustment_findings:
        findings.append("Credits and adjustments: " + " ".join(credit_or_adjustment_findings))

    if not findings:
        findings.append(
            "No material billing anomalies were identified beyond normal invoice settlement."
        )

    sections = [
        {"type": "heading", "text": "Billing Relationship Summary"},
        {"type": "paragraph", "text": summary_text},
        {"type": "heading", "text": "All Invoices"},
        {
            "type": "table",
            "headers": [
                "Invoice ID",
                "Amount (EUR)",
                "Valid Paid (EUR)",
                "Outstanding (EUR)",
                "Status",
            ],
            "rows": rows,
        },
    ]

    if include_chart:
        sections.append(
            {
                "type": "chart",
                "chart_type": "bar",
                "title": "Invoice Amounts and Outstanding Balances",
                "labels": [case["invoice_id"] for case in invoice_cases],
                "datasets": [
                    {
                        "label": "Amount (EUR)",
                        "data": [
                            _cents_to_amount(case.get("invoice_amount_cents") or 0)
                            for case in invoice_cases
                        ],
                    },
                    {
                        "label": "Outstanding (EUR)",
                        "data": [
                            _cents_to_amount(case.get("outstanding_amount_cents") or 0)
                            for case in invoice_cases
                        ],
                    },
                ],
            }
        )

    sections.extend(
        [
            {"type": "heading", "text": "Notable Findings"},
            *[{"type": "paragraph", "text": finding} for finding in findings],
        ]
    )

    return {
        "title": f"Billing Summary - {account_name} ({account_id})",
        "filename": f"billing_summary_{account_id.lower().replace('-', '')}.pdf",
        "content_sections": sections,
        "content_sections_json": json.dumps(sections, ensure_ascii=False),
    }


def verify_billing_summary(summary: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    cases = summary.get("invoice_cases", [])
    invoice_ids = [case.get("invoice_id") for case in cases]
    account_id = summary.get("account_id")
    event_by_id = _event_by_id()

    if len(invoice_ids) != len(set(invoice_ids)):
        errors.append("Each invoice case must appear exactly once.")
    if summary.get("invoice_count") != len(cases):
        errors.append("invoice_count does not match invoice_cases length.")
    if summary.get("source") == "billing_case_documents" and isinstance(account_id, str):
        expected_cases = list_invoice_cases(account_id=account_id)
        expected_invoice_ids = {
            case["invoice_id"] for case in expected_cases.get("invoice_cases", [])
        }
        missing_cases = sorted(expected_invoice_ids - set(invoice_ids))
        extra_cases = sorted(set(invoice_ids) - expected_invoice_ids)
        if missing_cases:
            errors.append(f"Missing invoice case documents: {missing_cases}")
        if extra_cases:
            errors.append(f"Unexpected invoice case documents: {extra_cases}")

    total_invoiced = sum(case.get("invoice_amount_cents") or 0 for case in cases)
    total_paid = sum(case.get("valid_paid_amount_cents") or 0 for case in cases)
    total_outstanding = sum(case.get("outstanding_amount_cents") or 0 for case in cases)

    if summary.get("total_invoiced_cents") != total_invoiced:
        errors.append("total_invoiced_cents does not match case totals.")
    if summary.get("total_valid_paid_cents") != total_paid:
        errors.append("total_valid_paid_cents does not match case totals.")
    if summary.get("total_outstanding_cents") != total_outstanding:
        errors.append("total_outstanding_cents does not match case totals.")
    if not summary.get("missing_invoice_id_scan_completed"):
        errors.append("missing_invoice_id scan was not completed.")

    for case in cases:
        settlement_adjustment_cents = case.get("settlement_adjustment_cents") or 0
        has_settlement_adjustment = settlement_adjustment_cents != 0
        if not case.get("canonical_invoice_event_id"):
            errors.append(f"{case.get('invoice_id')} has no canonical invoice event.")
        elif case.get("canonical_invoice_event_id") not in event_by_id:
            errors.append(f"{case.get('invoice_id')} references an unknown canonical event.")
        if case.get("outstanding_amount_cents", 0) < 0:
            errors.append(f"{case.get('invoice_id')} has a negative outstanding balance.")
        if (
            case.get("payment_status") == "fully_paid"
            and case.get("outstanding_amount_cents") != 0
        ):
            errors.append(f"{case.get('invoice_id')} is fully_paid with non-zero outstanding.")
        if (
            case.get("payment_status") == "partially_paid"
            and case.get("outstanding_amount_cents", 0) <= 0
            and not has_settlement_adjustment
        ):
            errors.append(f"{case.get('invoice_id')} is partially_paid without outstanding.")
        if (
            case.get("payment_status") == "outstanding"
            and case.get("valid_paid_amount_cents", 0) != 0
        ):
            errors.append(f"{case.get('invoice_id')} is outstanding but has valid paid amount.")
        for event_id in case.get("event_ids", []):
            if event_id not in event_by_id:
                errors.append(f"{case.get('invoice_id')} references unknown event {event_id}.")

        if has_settlement_adjustment:
            if abs(settlement_adjustment_cents) > MAX_SETTLEMENT_ADJUSTMENT_CENTS:
                errors.append(f"{case.get('invoice_id')} settlement adjustment exceeds €10.00.")
            if not case.get("abnormal_tags"):
                errors.append(
                    f"{case.get('invoice_id')} settlement adjustment requires abnormal_tags."
                )
            if not case.get("settlement_adjustment_reason"):
                errors.append(f"{case.get('invoice_id')} settlement adjustment requires a reason.")

            adjustment_event_ids = case.get("settlement_adjustment_event_ids", [])
            if not adjustment_event_ids:
                errors.append(
                    f"{case.get('invoice_id')} settlement adjustment requires event IDs."
                )
            adjustment_events = _event_ids_to_events(event_by_id, adjustment_event_ids)
            if len(adjustment_events) != len(adjustment_event_ids):
                errors.append(
                    f"{case.get('invoice_id')} settlement adjustment references unknown events."
                )
            supported_cents = sum(
                abs(event.get("amount_cents") or 0) for event in adjustment_events
            )
            if supported_cents < abs(settlement_adjustment_cents):
                errors.append(
                    f"{case.get('invoice_id')} settlement adjustment exceeds "
                    "referenced event amount."
                )
            lifecycle_event_ids = set(case.get("event_ids", []))
            for event in adjustment_events:
                event_invoice_id = event.get("invoice_id")
                event_attached_to_case = event.get(
                    "event_id"
                ) in lifecycle_event_ids or event_invoice_id == case.get("invoice_id")
                if not event_attached_to_case:
                    errors.append(
                        f"{case.get('invoice_id')} settlement adjustment event "
                        f"{event.get('event_id')} is not attached to this invoice."
                    )
            if not adjustment_events:
                errors.append(
                    f"{case.get('invoice_id')} settlement adjustment has no usable events."
                )

            canonical_event = event_by_id.get(case.get("canonical_invoice_event_id"))
            payment_events = _event_ids_to_events(
                event_by_id, case.get("payment_amount_event_ids", [])
            )
            if canonical_event is not None and payment_events:
                analysis_end_date = summary.get("end_date")
                if not analysis_end_date and isinstance(account_id, str):
                    analysis_end_date = inspect_billing_range(account_id=account_id)["end_date"]
                recalculated = _derive_case_financials(
                    canonical_event,
                    payment_events,
                    analysis_end_date=analysis_end_date,
                )
                base_outstanding_cents = recalculated["base_outstanding_amount_cents"]
                effective_outstanding_cents = base_outstanding_cents + settlement_adjustment_cents
                if case.get("base_outstanding_amount_cents") != base_outstanding_cents:
                    errors.append(
                        f"{case.get('invoice_id')} base outstanding failed recalculation."
                    )
                if case.get("outstanding_amount_cents") != effective_outstanding_cents:
                    errors.append(
                        f"{case.get('invoice_id')} effective outstanding failed recalculation."
                    )
                if effective_outstanding_cents < 0:
                    errors.append(
                        f"{case.get('invoice_id')} settlement adjustment creates "
                        "negative outstanding."
                    )

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": {
            "invoice_case_coverage": not any(
                error.startswith("Each invoice") or "invoice_count" in error for error in errors
            ),
            "aggregate_consistency": not any("total_" in error for error in errors),
            "missing_invoice_id_scan_completed": bool(
                summary.get("missing_invoice_id_scan_completed")
            ),
        },
    }


class InspectBillingRangeTool(Tool):
    name = "inspect_billing_range"
    description = "Inspect billing.csv and return the available billing date range as JSON."
    inputs = {
        "account_id": {
            "type": "string",
            "description": "Optional account_id filter, e.g. MERID-001.",
            "nullable": True,
        }
    }
    output_type = "string"

    def forward(self, account_id: str | None = None) -> str:
        return _json(inspect_billing_range(account_id=account_id))


class BillingContextTool(Tool):
    name = "read_billing_context"
    description = (
        "Read structured billing rows as JSON. Supports account_id, date range, invoice_id, "
        "nearby-row lookup, and missing-invoice-id scans. It does not silently truncate."
    )
    inputs = {
        "account_id": {"type": "string", "description": "Optional account_id.", "nullable": True},
        "start_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "end_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "invoice_id": {"type": "string", "description": "Optional invoice_id.", "nullable": True},
        "around_event_id": {
            "type": "string",
            "description": "Optional event_id for nearby-row inspection.",
            "nullable": True,
        },
        "neighbor_rows": {
            "type": "integer",
            "description": "Rows before and after around_event_id. Default: 3.",
            "nullable": True,
        },
        "missing_invoice_id_only": {
            "type": "boolean",
            "description": "Return only rows where invoice_id is missing.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(
        self,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        invoice_id: str | None = None,
        around_event_id: str | None = None,
        neighbor_rows: int | None = None,
        missing_invoice_id_only: bool | None = None,
    ) -> str:
        return _json(
            read_billing_context(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date,
                invoice_id=invoice_id,
                around_event_id=around_event_id,
                neighbor_rows=neighbor_rows if neighbor_rows is not None else 3,
                missing_invoice_id_only=bool(missing_invoice_id_only),
            )
        )


class ListInvoiceCasesTool(Tool):
    name = "list_invoice_cases"
    description = "List deterministic INV-* invoice cases for an account/date range as JSON."
    inputs = {
        "account_id": {"type": "string", "description": "Optional account_id.", "nullable": True},
        "start_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "end_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
    }
    output_type = "string"

    def forward(
        self,
        account_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        return _json(
            list_invoice_cases(account_id=account_id, start_date=start_date, end_date=end_date)
        )


class CalculateBillingTool(Tool):
    name = "calculate_billing"
    description = "Perform exact deterministic amount calculations from source event IDs."
    inputs = {
        "event_ids_json": {
            "type": "string",
            "description": 'JSON array of event IDs, e.g. ["BIL-5001", "BIL-5002"].',
        },
        "operation": {
            "type": "string",
            "description": "Calculation operation. Currently only sum_amount is supported.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, event_ids_json: str, operation: str | None = None) -> str:
        try:
            event_ids = json.loads(event_ids_json)
        except json.JSONDecodeError as exc:
            return _json({"error": f"Invalid event_ids_json: {exc}"})
        if not isinstance(event_ids, list) or not all(isinstance(item, str) for item in event_ids):
            return _json({"error": "event_ids_json must be a JSON array of strings."})
        return _json(calculate_billing(event_ids, operation=operation or "sum_amount"))


class SaveInvoiceCaseTool(Tool):
    name = "save_invoice_case"
    description = (
        "Validate and save one completed Structured Invoice Case Document as JSON. "
        "Required fields: invoice_id, analysis_status, case_labels, case_summary, "
        "canonical_invoice_event_id, lifecycle_event_ids, payment_status, timing_status."
    )
    inputs = {
        "account_id": {"type": "string", "description": "Required account_id."},
        "case_json": {"type": "string", "description": "Structured Invoice Case JSON object."},
    }
    output_type = "string"

    def forward(self, account_id: str, case_json: str) -> str:
        try:
            case_doc = json.loads(case_json)
        except json.JSONDecodeError as exc:
            return _json({"status": "FAIL", "errors": [f"Invalid case_json: {exc}"]})
        if not isinstance(case_doc, dict):
            return _json({"status": "FAIL", "errors": ["case_json must be an object."]})
        return _json(save_invoice_case(case_doc, account_id=account_id))


class ScanMissingInvoiceIdsTool(Tool):
    name = "scan_missing_invoice_ids"
    description = (
        "Perform the final missing-invoice-id scan and persist scan completion. "
        "Optionally pass assignments_json as a list of {event_id, invoice_id, rationale}; "
        "invoice_id may be null for genuinely unassigned events."
    )
    inputs = {
        "account_id": {"type": "string", "description": "Required account_id."},
        "start_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "end_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "assignments_json": {
            "type": "string",
            "description": "Optional JSON array of event assignments.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(
        self,
        account_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        assignments_json: str | None = None,
    ) -> str:
        assignments = None
        if assignments_json:
            try:
                assignments = json.loads(assignments_json)
            except json.JSONDecodeError as exc:
                return _json({"status": "FAIL", "errors": [f"Invalid assignments_json: {exc}"]})
            if not isinstance(assignments, list):
                return _json({"status": "FAIL", "errors": ["assignments_json must be an array."]})
        return _json(
            _scan_missing_invoice_ids(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date,
                assignments=assignments,
            )
        )


class BuildInvoiceCaseDocumentsTool(Tool):
    name = "build_invoice_case_documents"
    description = (
        "Build and save draft Structured Invoice Case Documents for every INV-* case. "
        "Returns only a compact summary and review checklist, not full case documents."
    )
    inputs = {
        "account_id": {"type": "string", "description": "Required account_id."},
        "start_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "end_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
    }
    output_type = "string"

    def forward(
        self,
        account_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        return _json(
            build_invoice_case_documents(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date,
            )
        )


class AggregateBillingSummaryTool(Tool):
    name = "aggregate_billing_summary"
    description = (
        "Deterministically aggregate invoice-level billing facts for the billing report. "
        "Use this as the source of financial totals."
    )
    inputs = {
        "account_id": {"type": "string", "description": "Required account_id."},
        "start_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "end_date": {"type": "string", "description": "Optional YYYY-MM-DD.", "nullable": True},
        "use_case_documents": {
            "type": "boolean",
            "description": "Aggregate saved invoice case documents instead of raw billing rows.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(
        self,
        account_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        use_case_documents: bool | None = None,
    ) -> str:
        return _json(
            aggregate_billing_summary(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date,
                use_case_documents=bool(use_case_documents),
            )
        )


class BuildBillingPDFSectionsTool(Tool):
    name = "build_billing_pdf_sections"
    description = (
        "Build standardized customer-facing PDF sections for billing_summary from "
        "verified aggregate_billing_summary JSON. The output uses a summary paragraph, "
        "a five-column invoice table, and concise notable findings. A chart can be included "
        "when include_chart is true. It never includes case labels, timing metadata, event IDs, "
        "or account profile fields."
    )
    inputs = {
        "summary_json": {
            "type": "string",
            "description": "JSON object returned by aggregate_billing_summary after verification.",
        },
        "include_chart": {
            "type": "boolean",
            "description": (
                "Optional. Include a concise chart when it materially improves readability."
            ),
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, summary_json: str, include_chart: bool | None = None) -> str:
        try:
            summary = json.loads(summary_json)
        except json.JSONDecodeError as exc:
            return _json({"status": "FAIL", "errors": [f"Invalid summary_json: {exc}"]})
        if not isinstance(summary, dict):
            return _json({"status": "FAIL", "errors": ["summary_json must be an object."]})
        return _json(build_billing_pdf_sections(summary, include_chart=bool(include_chart)))


class VerifyBillingSummaryTool(Tool):
    name = "verify_billing_summary"
    description = "Run deterministic consistency checks on aggregate_billing_summary JSON."
    inputs = {
        "summary_json": {
            "type": "string",
            "description": "JSON object returned by aggregate_billing_summary.",
        }
    }
    output_type = "string"

    def forward(self, summary_json: str) -> str:
        try:
            summary = json.loads(summary_json)
        except json.JSONDecodeError as exc:
            return _json({"status": "FAIL", "errors": [f"Invalid summary_json: {exc}"]})
        if not isinstance(summary, dict):
            return _json({"status": "FAIL", "errors": ["summary_json must be an object."]})
        return _json(verify_billing_summary(summary))
