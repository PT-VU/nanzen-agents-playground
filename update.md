下面这份可以直接保存成例如 `BILLING_AGENT_UPGRADE_PLAN.md` 交给本地 Codex。内容只包含我们已经讨论并确认的设计，没有引入新的架构层或额外规则。

````markdown
# Billing Agent Upgrade Plan

## 1. Purpose

This document defines the required upgrade of the existing billing analysis Agent in `nanzen-agents-playground`.

The current baseline Agent can run the `billing_summary` task, but the baseline execution exposed several reliability problems:

- `read_context` converts CSV rows into a large pipe-delimited string, forcing the Agent to reconstruct structured data manually.
- Billing data can be silently truncated by the row `limit`, causing the Agent to analyze only part of the customer's billing history.
- Rows with missing `account_id` can be incorrectly excluded even when their `invoice_id` clearly links them to the target account.
- The Agent currently analyzes raw rows globally rather than treating each invoice as an independent billing case.
- Precise financial calculations are currently generated dynamically by the Agent as Python code.
- The CodeAgent sandbox does not support every normal Python builtin. The baseline run wasted multiple steps debugging unsupported or unexpected execution behavior.
- The Agent can reach `max_steps` without producing the required PDF while the outer runner still considers the execution successful.
- There is currently no deterministic final verification step between Agent reasoning and PDF generation.

The goal of this upgrade is **not** to redesign the repository into a general finance platform.

The goal is specifically to make the existing `billing_summary` workflow reliable for the provided billing dataset while keeping the implementation small and understandable.

The central design principle is:

> The Agent is responsible for semantic interpretation of individual invoice cases and abnormal billing behavior.  
> Deterministic tools are responsible for structured retrieval, precise calculation, aggregation, schema enforcement, and final consistency checks.

---

# 2. Final Business Objective

The billing task is:

> Analyze the complete billing history for account `MERID-001` (Meridian Health) and generate a customer-ready billing summary PDF.

The final PDF must answer four primary business questions:

1. How much has Meridian Health been invoiced, how much has actually been paid, and how much remains outstanding?
2. What happened to every invoice in the analyzed billing history?
3. Which invoices were paid late or remain outstanding?
4. Which billing cases contained notable abnormalities such as disputes, credits, refunds, duplicate payments, invoice corrections, partial payments, or other abnormal billing behavior?

The required PDF should therefore contain the following information.

## 2.1 Overall Billing Summary

The beginning of the report should clearly state:

- analyzed billing date range;
- total number of invoices;
- total invoiced;
- total valid paid amount;
- current outstanding amount.

The numbers in this section must come from deterministic aggregation of the completed Invoice Case Documents.

The Agent must not recalculate these totals independently while writing the PDF.

## 2.2 Complete Invoice Table

The report must contain one row for every real invoice included in the analyzed billing history.

The table should provide the information needed to understand the final state of each invoice, including:

- Invoice ID;
- invoice amount;
- valid payment amount;
- due date;
- paid date where applicable;
- final payment status;
- timing status;
- relevant Case labels / notable status.

The table represents the final interpreted state of each invoice rather than simply reproducing all raw billing events.

## 2.3 Late Payments

The report must explicitly identify invoices that were paid after their due date.

For each relevant invoice, the report should make clear:

- Invoice ID;
- due date;
- paid date;
- days past due;
- whether the invoice was eventually fully paid.

A late invoice that was later fully paid must not be confused with an outstanding invoice.

## 2.4 Outstanding Invoices

The report must explicitly identify invoices that remain unpaid or partially unpaid.

The report should state:

- number of outstanding invoices;
- total outstanding amount;
- Invoice ID;
- invoice amount;
- valid paid amount;
- remaining outstanding balance;
- due date;
- current status.

## 2.5 Notable Billing Findings

The report must summarize notable abnormal billing cases found in the data.

Examples already present in `billing.csv` include:

- late payment;
- reconciliation exception;
- rounding adjustment;
- duplicate payment;
- refund;
- manual reconciliation;
- incorrect remittance information;
- dispute;
- invoice correction;
- credit note;
- delayed credit application;
- partial payment;
- planned split payment;
- duplicate/resubmitted invoice event;
- unmatched payment;
- post-settlement adjustment.

The report does not need to reproduce every raw event.

It should explain:

- what happened;
- whether the issue was resolved;
- whether and how it affected financial totals.

Where relevant, the final structured summary may also expose aggregate refund, credit, or other abnormal amounts required for the report.

---

# 3. Overall Target Workflow

The upgraded billing workflow should follow this sequence:

```text
Billing Task
    ↓
Inspect available billing date range
    ↓
Resolve missing account_id where invoice_id provides the linkage
    ↓
Read complete billing data for target account and target date range
    ↓
List all real Invoice Cases
    ↓
Analyze each Invoice Case independently
    ↓
If information appears incomplete:
    read nearby rows and investigate possible missing invoice_id records
    ↓
Agent classifies the Case
    ↓
Agent uses deterministic calculation tool when precise arithmetic is needed
    ↓
Agent saves a structured Invoice Case Document
    ↓
Repeat until all Invoice Cases are analyzed
    ↓
Final scan of rows with missing invoice_id
    ↓
Attach missed events to an Invoice Case where justified,
or leave them unassigned when they genuinely do not belong to an invoice
    ↓
Update affected Invoice Case Documents if necessary
    ↓
Deterministic Summary Aggregation
    ↓
Agent reviews the structured overall summary
    ↓
Deterministic Verifier
    ↓
If verification passes:
    generate PDF
````

---

# 4. Data Retrieval Upgrade

## 4.1 Structured Tool Output

The current `read_context` behavior that converts CSV data into a pipe-delimited text table must be replaced.

The Tool should return structured data.

The Agent must not need to perform:

```text
splitlines()
split("|")
header reconstruction
manual CSV parsing
manual conversion of basic field types
```

The Tool should perform basic parsing before returning data.

Examples:

```text
amount          → numeric value
days_past_due   → integer when present
timestamp       → normalized date/time representation
empty values    → null / None
```

The exact internal Python numeric representation may follow the implementation, but monetary data must be returned as a machine-readable value suitable for deterministic calculation rather than left as free-form text.

The Tool output should remain directly usable by the Agent as structured Python/JSON-like data.

---

# 5. Data Completeness

The billing Agent must know what time range it is expected to cover.

Before beginning Invoice Case analysis, the Agent must inspect the billing source to determine its available start and end dates.

A dedicated Tool should provide the available billing date range.

Example conceptual output:

```json
{
  "start_date": "2023-11-01",
  "end_date": "2026-03-01"
}
```

The exact dates must be derived from the actual dataset.

The billing reader must support:

```text
account_id
start_date
end_date
invoice_id
```

The Tool must guarantee that when a date range is requested, all rows matching the requested range and filters are returned.

There must not be a hidden `50` or `100` row truncation that silently makes the result incomplete.

The Tool should also return the actual first and last timestamp of the returned records so the Agent can understand the data range it has received.

For this challenge, the CSV data should be treated as static.

Do not introduce:

* cursors;
* snapshot/version management;
* matched-row / processed-row accounting systems;
* dynamic database consistency mechanisms.

These are outside the intended scope.

---

# 6. Missing `account_id` Resolution

The dataset contains rows where `account_id` is missing even though the `invoice_id` clearly identifies the owning account.

Example:

```text
event_id   = BIL-5204
account_id = missing
invoice_id = INV-2025-MH-024
```

Other events for `INV-2025-MH-024` clearly belong to `MERID-001`.

The system therefore requires deterministic resolution of missing `account_id` based on `invoice_id`.

The resolver's current responsibility is intentionally narrow:

```text
missing account_id
        ↓
invoice_id
        ↓
find a valid invoice/event with the same invoice_id
        ↓
determine account_id
```

Do not add confidence scoring.

## Critical Ordering Requirement

Resolution must occur before account filtering causes the row to disappear.

Do **not** implement:

```text
filter account_id = MERID-001
        ↓
resolve missing account_id
```

because a row such as `BIL-5204` would already have been excluded.

The system must instead behave logically as:

```text
raw billing data
        ↓
resolve missing account_id using invoice linkage
        ↓
apply target-account filtering
```

or implement equivalent behavior inside the billing reader.

The important requirement is that a valid event must not be lost simply because its `account_id` field is blank when its `invoice_id` provides a deterministic link to the target account.

---

# 7. Invoice Case Definition

The upgraded Agent must no longer analyze billing history mainly as a flat sequence of independent rows.

The primary unit of Agent reasoning must be an **Invoice Case**.

Example:

```text
INV-2024-MH-006
├── invoice_issued
├── email_sent
├── payment_received
├── reconciled
├── duplicate payment_received
├── refund_initiated
└── refund_completed
```

All relevant events for one invoice should be analyzed together.

## 7.1 What Counts as an Invoice Case

A real Invoice Case is a real invoice identifier:

```text
INV-*
```

Do not treat every non-empty value in the CSV `invoice_id` column as an Invoice Case.

The dataset also stores other billing document identifiers in this column.

For example:

```text
CN-2025-MH-001
```

is a Credit Note, not an invoice.

Therefore:

```text
INV-* → Invoice Case

CN-*  → related credit document / event,
        not an independent Invoice Case
```

A Credit Note should instead be related to the Invoice Case that ultimately uses or is affected by that credit.

---

# 8. Credit Note Example and Required Interpretation

`CN-2025-MH-001` is a concrete example of why `CN-*` must not become its own Invoice Case.

The underlying event represents:

```text
event_type = credit_note_issued
credit note = CN-2025-MH-001
amount = -3600
```

The credit was created after an SLA outage and was intended to reduce a later invoice.

A later real invoice:

```text
INV-2025-MH-015
```

references:

```text
credit_note_ref = CN-2025-MH-001
```

and applies the credit to that invoice.

Therefore the logical relationship is:

```text
SLA incident
    ↓
Credit Note CN-2025-MH-001
    ↓
credit later applied
    ↓
Invoice Case INV-2025-MH-015
```

The Credit Note is related financial information for an Invoice Case.

It must not be counted as a second invoice.

---

# 9. Invoice Case Analysis Strategy

The Agent must process Invoice Cases one at a time.

The intended pattern is:

```text
read one Invoice Case
        ↓
understand its event lifecycle
        ↓
classify normal / abnormal behavior
        ↓
identify relevant event IDs
        ↓
call deterministic calculation when needed
        ↓
produce structured Invoice Case Document
        ↓
save it
        ↓
move to the next Invoice Case
```

Do not return to the baseline behavior of loading a large raw billing table and reasoning over all rows simultaneously.

---

# 10. Local Investigation When a Case Appears Incomplete

If an Invoice Case appears to be missing an expected event, the Agent may investigate nearby rows.

Example:

```text
invoice exists
payment seems missing
```

The Agent may request rows near the relevant time/event and inspect whether a payment or other related action exists but has a missing or incorrect `invoice_id`.

The billing reader must therefore support local neighboring-row inspection.

Conceptually:

```text
around_event_id
neighbor_rows
```

The Agent may use nearby information such as:

* timestamp;
* amount;
* description;
* payment reference;
* surrounding invoice events;

to determine whether a row with a missing `invoice_id` belongs to the current Invoice Case.

This is an Agent semantic decision.

It should not be replaced by a large deterministic matching engine.

---

# 11. Final Missing-Invoice-ID Scan

Before the Agent declares Invoice Case analysis complete and enters Summary Aggregation, it must perform one final scan of all relevant rows where:

```text
invoice_id is missing
```

The purpose is to ensure that no important:

* payment;
* refund;
* credit-related action;
* adjustment;
* other monetary billing event;

was excluded from Invoice Case analysis only because its `invoice_id` was missing.

The Agent must inspect these rows and decide whether each relevant event:

### A. Belongs to an existing Invoice Case

If yes:

```text
attach the event to the correct Invoice Case
↓
update the Structured Case Document
```

### B. Genuinely does not belong to any invoice

If the evidence indicates the event is genuinely independent of an invoice, do not invent an invoice association.

A real example in `billing.csv` is the unmatched `€847.50` payment that Meridian sent to the wrong vendor and which was later returned.

That event has no invoice because it genuinely does not belong to an invoice.

Such an event should remain unassigned and may appear as a notable billing anomaly rather than being forced into an Invoice Case.

Only after this final scan is complete may the system proceed to Summary Aggregation.

---

# 12. Known Billing Lifecycle Guidance

The Agent system prompt should contain domain guidance explaining expected billing lifecycles.

These patterns are **guidance**, not an exhaustive deterministic rule engine.

A Case may have multiple labels.

If a Case does not fit known patterns, the Agent may classify it as `unknown_anomaly`.

---

# 13. Normal Invoice Case

Typical normal lifecycle:

```text
invoice_issued
    ↓
email_sent
    ↓
payment_received
    ↓
reconciled
```

Payment may occur:

```text
early
on time
late
```

For a normal fully paid Invoice:

```text
canonical invoice amount
=
valid payment amount

outstanding = 0
```

---

# 14. Known Abnormal Case Patterns

## 14.1 Late Payment

Typical pattern:

```text
invoice_issued
    ↓
email_sent
    ↓
due date passes
    ↓
payment reminder(s)
    ↓
payment_received
    ↓
reconciled
```

Expected interpretation:

```text
include invoice in Total Invoiced
include valid payment in Total Paid
count as Late Payment
do not count as Outstanding if later fully paid
```

---

## 14.2 Rounding / Reconciliation Exception

Example pattern found in `INV-2024-MH-005`:

```text
invoice
    ↓
payment
    ↓
reconciliation_exception
    ↓
small adjustment
    ↓
reconciled
```

The Agent should recognize the reconciliation exception and related adjustment.

The valid invoice and valid payment still participate in the normal invoice/payment totals.

The adjustment should be represented separately in the Case where relevant.

---

## 14.3 Duplicate Payment + Refund

Example: `INV-2024-MH-006`.

Pattern:

```text
invoice
    ↓
normal payment
    ↓
reconciled
    ↓
duplicate payment
    ↓
refund initiated
    ↓
refund completed
```

The duplicate payment must not be treated as a second valid invoice settlement.

The Case should distinguish:

```text
normal payment event
duplicate payment event
refund event
```

---

## 14.4 Manual Reconciliation / Incorrect Remittance

Example patterns include:

```text
invoice
    ↓
payment
    ↓
remittance reference cannot be auto-matched
    ↓
manual reconciliation
```

or payment references containing an incorrect invoice number but being matched through the surrounding evidence.

The financial payment may still be valid.

The Case should be labeled with the relevant manual reconciliation / remittance abnormality.

---

## 14.5 Invoice Correction + Dispute

Example: `INV-2024-MH-013`.

Pattern:

```text
invoice_issued
    ↓
customer identifies incorrect information
    ↓
dispute_opened
    ↓
invoice_corrected
    ↓
dispute_resolved
    ↓
payment_received
    ↓
reconciled
```

Multiple events describing the same invoice must not be counted as multiple invoices.

The Agent must identify the event representing the final canonical invoice state.

---

## 14.6 Credit / Credit Application

A typical credit pattern is:

```text
credit_note_issued
    ↓
later invoice references credit
    ↓
credit applied
    ↓
reduced invoice
    ↓
payment
    ↓
reconciled
```

Credits can also have delayed application.

Example:

```text
credit created
    ↓
expected on January invoice
    ↓
not applied
    ↓
customer raises issue
    ↓
agreement to pay January in full
    ↓
credit moved to February
    ↓
credit applied in February
```

The Agent should reason over the relevant relationship between the credit document and affected Invoice Cases.

Do not treat the Credit Note itself as an Invoice Case.

---

## 14.7 Partial Payment

Example: `INV-2025-MH-021`.

Pattern:

```text
invoice
    ↓
partial payment
    ↓
second payment
    ↓
invoice fully paid
    ↓
reconciled
```

A Case may simultaneously be:

```json
[
  "late_payment",
  "partial_payment"
]
```

Multiple payment rows can settle one invoice.

---

## 14.8 Planned Split Payment

Later Meridian invoices show a planned split-payment pattern:

```text
Engineering department payment
+
Marketing department payment
=
single invoice settlement
```

This is different from accidentally incomplete payment.

Multiple payment events must still be aggregated into the settlement of one Invoice Case.

---

## 14.9 Duplicate / Resubmitted Invoice Event

Example: `INV-2025-MH-022`.

The dataset contains multiple `invoice_issued` events for the same Invoice ID.

The amounts are not identical.

The Agent must analyze the complete Case and determine which event represents the canonical invoice for reporting.

The system must not simply sum every `invoice_issued` event.

This is intentionally an Agent semantic reasoning responsibility.

The deterministic Verifier does not attempt to independently re-decide which invoice event is canonical.

---

## 14.10 Missing `account_id`

This is treated as a data-quality issue before Invoice Case analysis.

Where `invoice_id` provides a deterministic link to a known account:

```text
invoice_id
    ↓
resolve account_id
```

Once resolved, the event participates normally in the relevant Invoice Case.

---

## 14.11 Missing `invoice_id`

A missing `invoice_id` is investigated through:

```text
local neighboring-row inspection
+
final missing-invoice-id scan
```

The Agent may determine that the event belongs to an Invoice Case.

However, the Agent must not force an Invoice association where the evidence shows that none exists.

---

## 14.12 Post-Settlement Adjustment

Example: `INV-2026-MH-027`.

An adjustment may appear after the invoice has already been paid and reconciled.

The adjustment must not automatically overwrite the payment history.

It should be represented as a separate abnormal financial event associated with the Case, and the Agent should interpret its role based on the supplied evidence.

---

# 15. Unknown Anomaly

The system must support a generic:

```text
unknown_anomaly
```

Case label.

The purpose is to preserve Agent robustness rather than reducing the system to a predefined deterministic taxonomy.

If a Case does not fit the known lifecycle patterns, the Agent may:

```text
classify it as unknown_anomaly
↓
reason from the actual evidence
↓
decide which events should participate in each PDF-target statistic
```

Example conceptual structure:

```json
{
  "case_labels": [
    "unknown_anomaly"
  ],

  "aggregation_decision": {
    "include_in_total_invoiced": true,
    "payment_event_ids_for_total_paid": [
      "BIL-X"
    ],
    "refund_event_ids_for_refund_total": [],
    "count_as_late_payment": false,
    "count_as_outstanding": false
  },

  "decision_reason": "Explanation based on the case evidence."
}
```

The Agent may determine **which events count**.

The Agent must not invent or manually alter monetary values.

The deterministic tools continue to read the actual amount from the referenced Event IDs and perform the arithmetic.

Known Case patterns are guidance.

They must not be written into the prompt as exhaustive mandatory rules that prevent the Agent from recognizing unfamiliar behavior.

---

# 16. Structured Invoice Case Document

Every completed Invoice Case must produce a structured document.

This document is the contract between:

```text
Agent semantic reasoning
        ↓
deterministic aggregation
```

The schema must be fixed.

However:

> Not every field in the schema must appear in every Invoice Case.

Fields that are irrelevant to a particular Case should be omitted.

For example:

```text
Case has refund
→ include refund_amount_event_ids

Case has no refund
→ refund_amount_event_ids does not need to appear
```

The Agent must not create alternative or synonymous field names.

For example, do not allow different Cases to invent:

```text
refund_amount
refund_event
refund_events
refund_ids
```

when the defined schema field is:

```text
refund_amount_event_ids
```

---

# 17. Required Base Fields

Every Invoice Case Document must contain the following base information:

```json
{
  "invoice_id": "INV-...",

  "analysis_status": "complete",

  "case_labels": [
    "normal"
  ],

  "case_summary": "Short semantic summary of what happened.",

  "canonical_invoice_event_id": "BIL-...",

  "lifecycle_event_ids": [
    "BIL-...",
    "BIL-..."
  ],

  "payment_status": "paid",

  "timing_status": "early"
}
```

## `invoice_id`

The real `INV-*` identifier of the Invoice Case.

## `analysis_status`

Expected completed value:

```text
complete
```

If the Agent believes important information is still missing, it should continue investigating before saving the Case as complete.

## `case_labels`

Multi-label classification.

Examples:

```json
["normal"]
```

```json
["late_payment"]
```

```json
[
  "late_payment",
  "partial_payment"
]
```

```json
[
  "duplicate_payment",
  "refund"
]
```

```json
[
  "unknown_anomaly"
]
```

## `case_summary`

A concise natural-language explanation of what happened in the Invoice Case.

This is semantic interpretation.

It should not be used as the numerical source for deterministic aggregation.

## `canonical_invoice_event_id`

The event the Agent considers to represent the correct invoice state used for financial reporting.

For straightforward cases this is normally the relevant `invoice_issued` event.

For correction/resubmission cases the Agent must determine which event is canonical.

## `lifecycle_event_ids`

All significant Event IDs the Agent used when understanding the Case.

This provides traceability from the structured interpretation back to the original billing data.

## `payment_status`

Examples:

```text
paid
partial
unpaid
```

## `timing_status`

Examples:

```text
early
on_time
late
not_due
```

An unpaid invoice that is not yet due must not automatically be treated as an overdue outstanding invoice.

---

# 18. Optional Financial Event Reference Fields

The schema must support optional fields corresponding to different financial roles.

These fields contain **Event IDs**, not Agent-copied monetary values.

Possible fields include:

```json
{
  "payment_amount_event_ids": [
    "BIL-..."
  ],

  "refund_amount_event_ids": [
    "BIL-..."
  ],

  "credit_amount_event_ids": [
    "BIL-..."
  ],

  "adjustment_amount_event_ids": [
    "BIL-..."
  ],

  "duplicate_payment_event_ids": [
    "BIL-..."
  ]
}
```

Only fields relevant to the current Case need to be present.

The purpose is to allow one Invoice Case to contain several distinct monetary categories without mixing their meanings.

For example, a duplicate payment Case may contain:

```json
{
  "payment_amount_event_ids": [
    "BIL-NORMAL-PAYMENT"
  ],

  "duplicate_payment_event_ids": [
    "BIL-DUPLICATE-PAYMENT"
  ],

  "refund_amount_event_ids": [
    "BIL-REFUND"
  ]
}
```

This allows deterministic aggregation to understand that the three amounts have different financial roles.

---

# 19. Example Structured Case

Conceptual example:

```json
{
  "invoice_id": "INV-2024-MH-006",

  "analysis_status": "complete",

  "case_labels": [
    "duplicate_payment",
    "refund"
  ],

  "case_summary": "The invoice was paid normally, then accidentally paid a second time. The duplicate payment was later fully refunded.",

  "canonical_invoice_event_id": "BIL-5022",

  "lifecycle_event_ids": [
    "BIL-5022",
    "BIL-5023",
    "BIL-5024",
    "BIL-5025",
    "BIL-5144",
    "BIL-5145",
    "BIL-5146"
  ],

  "payment_amount_event_ids": [
    "BIL-5024"
  ],

  "duplicate_payment_event_ids": [
    "BIL-5144"
  ],

  "refund_amount_event_ids": [
    "BIL-5146"
  ],

  "payment_status": "paid",

  "timing_status": "early"
}
```

The numeric amounts remain in the source events.

The Agent identifies the semantic roles of the events.

The deterministic calculator and aggregator read the source amounts.

---

# 20. Required Tools

The upgraded system requires the following tool capabilities.

Do not add additional architecture unless required to implement these capabilities.

---

## Tool 1 — `inspect_billing_range`

Purpose:

Determine the available billing time range before detailed analysis begins.

Conceptual input:

```text
source = billing
```

Conceptual output:

```json
{
  "start_date": "...",
  "end_date": "..."
}
```

The Agent should call this before starting the complete billing analysis.

---

## Tool 2 — `resolve_missing_account_id`

Purpose:

Resolve rows with missing `account_id` when the row contains an `invoice_id` that can be linked deterministically to the correct account.

Core rule:

```text
invoice_id
    ↓
find valid same-invoice records
    ↓
derive account_id
```

This resolution must logically happen before unresolved rows would be removed by account filtering.

Do not add confidence scoring.

---

## Tool 3 — Upgraded `read_context`

The existing Tool should be improved rather than replaced unnecessarily.

It must support structured output and billing-focused retrieval parameters.

Required capabilities include:

```text
source
account_id
start_date
end_date
invoice_id
missing_invoice_id
around_event_id
neighbor_rows
```

The Tool should be capable of:

### Reading an Invoice Case

```text
invoice_id = INV-...
```

### Reading a complete date range

```text
start_date
end_date
```

### Reading nearby rows

```text
around_event_id
neighbor_rows
```

### Reading all rows with missing Invoice ID

```text
missing_invoice_id = true
```

The Tool must return structured data and must not silently truncate a requested date-range result because of the old default row limit.

---

## Tool 4 — `list_invoice_cases`

Purpose:

Provide the deterministic checklist of real Invoice Cases that must be analyzed.

Input:

```text
account_id
start_date
end_date
```

Output:

```json
[
  "INV-...",
  "INV-...",
  "INV-..."
]
```

Only real:

```text
INV-*
```

identifiers count as Invoice Cases.

Do not include:

```text
CN-*
```

Credit Notes as Invoice Cases.

The Agent should use this list as its work checklist.

The Verifier should later use the same deterministic list when checking Case coverage.

---

## Tool 5 — `calculate_billing`

Purpose:

Perform precise arithmetic using actual source Event IDs.

The Agent should not perform critical financial arithmetic itself when a deterministic calculation can be requested.

Conceptual usage:

```text
event_ids
operation
```

Example:

```text
payment event A
+
payment event B
```

The Tool reads the actual source amounts referenced by those Event IDs and performs the calculation.

Important responsibility split:

```text
Agent:
determines which events represent valid payment / refund / credit / etc.

Calculation Tool:
reads their real values and performs exact arithmetic.
```

The Tool does not decide the business meaning of an Event.

---

## Tool 6 — `save_invoice_case`

Purpose:

Save the Agent-produced Structured Invoice Case Document.

Responsibilities:

```text
validate fixed schema
validate required fields
validate field names
save document
allow later update when missing-invoice-id scan finds relevant evidence
```

The Tool must allow optional schema fields to be omitted.

The Tool must not require every optional financial category to exist in every Case.

---

## Tool 7 — `aggregate_billing_summary`

Purpose:

Deterministically aggregate all completed Invoice Case Documents.

The Tool should:

```text
read saved Case Documents
        ↓
read referenced source Event IDs
        ↓
retrieve real monetary values
        ↓
perform deterministic sums / counts
        ↓
produce structured Billing Summary
```

The structured result should provide the information needed for the target PDF, including:

```text
total invoiced
total valid paid
total outstanding
invoice count
late invoice count
refund information where applicable
credit information where applicable
Case-level results required for the invoice table
abnormal Case statistics required for notable findings
```

The Agent should not independently recompute these totals after aggregation.

---

## Tool 8 — `verify_billing_summary`

Purpose:

Perform simple deterministic consistency checks before the PDF is generated.

The Verifier does **not** redo Agent semantic reasoning.

It should not attempt to decide whether the Agent selected the correct canonical event in a complex ambiguous Case.

That local semantic decision belongs to the Agent.

The Verifier should check deterministic consistency only.

Required checks are described later in this document.

---

## Tool 9 — Existing `create_report`

The existing PDF generation Tool should remain the final report renderer.

The intended sequence is:

```text
aggregation
    ↓
Agent review
    ↓
verification
    ↓
PASS
    ↓
create_report
```

A failed verification result should prevent the system from treating the report generation stage as successfully complete.

---

# 21. Agent System Prompt Changes

The Agent system instructions should be expanded to describe the billing-specific workflow.

The purpose is to guide Agent behavior while leaving semantic case interpretation to the Agent.

The prompt should contain the following requirements.

---

## 21.1 Explain the Final Business Goal

The Agent must understand that it needs to produce a trustworthy customer billing summary answering:

```text
total invoiced
total paid
outstanding
late payments
status of every invoice
disputes
credits
refunds
other notable abnormalities
```

---

## 21.2 Require Invoice-Case-Based Analysis

The Agent should reason about one Invoice Case at a time.

Do not encourage global row-by-row analysis of the full billing CSV.

---

## 21.3 Provide Known Lifecycle Guidance

The Agent should be informed about:

```text
normal invoice lifecycle
late payment
reconciliation exception
duplicate payment / refund
manual reconciliation
dispute / correction
credit application
partial / split payment
resubmitted invoice
post-settlement adjustment
```

These are examples and known patterns.

They are not an exhaustive deterministic taxonomy.

---

## 21.4 Allow Multi-Label Cases

The Agent must understand that a Case can simultaneously contain multiple conditions.

Example:

```json
[
  "late_payment",
  "partial_payment"
]
```

---

## 21.5 Allow `unknown_anomaly`

The Agent must be explicitly allowed to classify a Case as:

```text
unknown_anomaly
```

when the observed lifecycle does not fit known patterns.

For an unknown anomaly, the Agent must explicitly determine which Event IDs should participate in each target statistic.

---

## 21.6 Require Local Investigation for Missing Information

When a Case appears incomplete, the Agent should use nearby-row retrieval rather than immediately assuming that the information does not exist.

This is particularly important when the source may contain rows with missing `invoice_id`.

---

## 21.7 Require Deterministic Calculation

The Agent should be instructed:

> Use the deterministic billing calculation Tool whenever precise financial arithmetic is required.

Do not spend Agent steps manually implementing critical billing calculations in generated Python code.

---

## 21.8 Require Structured Case Output

Every analyzed Invoice Case must result in a Structured Case Document following the fixed schema.

Natural-language Case summaries alone are insufficient.

---

## 21.9 Require Final Missing-Invoice-ID Scan

Before calling Summary Aggregation, the Agent must perform the final scan of missing-`invoice_id` rows.

Only after these rows have been reviewed may the Agent proceed.

---

## 21.10 Preserve Task Completion Priority

The Agent should remain focused on producing the required business deliverable.

The baseline run wasted several steps repeatedly debugging a non-critical Python execution issue and ultimately reached `max_steps` before generating the PDF.

The prompt should explicitly instruct the Agent to:

```text
avoid repeatedly retrying the same failed implementation approach;

switch to a simpler valid approach when a non-critical execution method repeatedly fails;

reserve enough progress to complete the required report;

verify that the required business deliverable has actually been produced.
```

This does not mean correctness is less important than completion.

The requirement is:

> Avoid wasting the limited Agent step budget on non-essential implementation debugging when another valid path exists.

---

# 22. CodeAgent Sandbox Guidance

The baseline Agent generated Python containing `repr(...)`, but the current smolagents restricted Python execution environment does not allow every normal Python builtin.

Create a repository-local Markdown reference describing the relevant execution capabilities available to generated Agent Python code.

The exact repository file path may be chosen during implementation, but the Agent instructions must clearly reference it.

The document should explain:

```text
commonly allowed builtins
unsupported / forbidden operations relevant to this Agent
authorized imports already configured in the Agent
```

The Agent should consult this capability reference before relying on custom generated Python behavior.

The goal is to reduce wasted steps caused by generating code incompatible with the current sandbox.

Do not turn this into a new execution framework.

---

# 23. Deterministic Responsibilities

The following responsibilities must not depend only on prompt compliance.

They should be enforced by deterministic code.

## Data structure

CSV parsing and basic field parsing happen before the Agent receives the data.

## Complete date-range retrieval

A requested date range must not be silently truncated.

## Missing-account resolution

`invoice_id → account_id` resolution must occur before the missing row can be lost through filtering.

## Invoice Case list

The deterministic system defines which `INV-*` Invoice Cases exist.

The Agent should not have to remember or infer whether it covered every Invoice ID.

## Structured schema

`save_invoice_case` enforces the fixed field names and required fields.

Optional fields remain optional.

## Financial arithmetic

Exact monetary arithmetic is performed by Tools.

## Final aggregation

Final sums and counts come from deterministic aggregation.

## Verification

The deterministic Verifier checks the relationship between analyzed Case Documents and final aggregate results.

## PDF completion gate

The system should not consider the billing task successfully complete merely because the Agent returned a final text answer.

Successful task completion requires that the verified report workflow reaches the PDF stage and the required report is actually produced.

---

# 24. Agent Responsibility Boundary

The following decisions intentionally remain Agent responsibilities:

* understanding an Invoice Case lifecycle;
* deciding whether the Case is normal or abnormal;
* assigning one or more Case labels;
* deciding whether an abnormal Case fits a known pattern;
* recognizing an `unknown_anomaly`;
* interpreting nearby missing-ID rows;
* deciding whether a missing-`invoice_id` event belongs to an Invoice Case;
* determining the canonical Invoice Event when multiple conflicting invoice events exist;
* determining which Event IDs represent valid payment, refund, credit, adjustment, duplicate payment, etc.;
* interpreting the business meaning of the final structured Billing Summary.

The deterministic system must not attempt to completely reproduce this reasoning.

The design intentionally trusts Agent intelligence for these local semantic decisions.

---

# 25. Verifier Scope

The Verifier must remain intentionally simple.

It should verify the execution and aggregation consistency of the Agent's decisions.

It should **not** independently judge whether the Agent's semantic interpretation was correct.

For example:

If the Agent selects one of two conflicting `invoice_issued` events as the canonical invoice event, the Verifier may check:

```text
the referenced Event ID exists;
the Event belongs to the relevant Invoice Case;
the aggregator used the referenced Event consistently.
```

The Verifier should not attempt to independently decide whether a different invoice event should have been selected.

That would require reproducing Agent-level reasoning and is outside the intended deterministic scope.

---

# 26. Required Verifier Checks

## 26.1 Invoice Case Coverage

Use the deterministic Invoice Case list.

Check that every required `INV-*` Case has one completed Structured Case Document.

Each Invoice Case should be represented exactly once at the final Case level.

---

## 26.2 Referenced Event Integrity

Check that Event IDs referenced by Case Documents actually exist.

Where the schema claims an Event belongs to a specific Invoice Case, verify the basic relationship where available.

---

## 26.3 Receivable / Payment Handling

Every invoice receivable must have an interpreted outcome.

For example:

```text
fully paid
partially paid
outstanding
not yet due
```

A missing payment must not simply disappear from the final result.

If no valid payment exists, the Case should reflect the appropriate unpaid/outstanding state.

---

## 26.4 Classification-to-Aggregation Consistency

If an Agent Case is classified with a known abnormality that requires a target statistic, the final aggregate must reflect that classification.

Examples:

```text
late_payment Case
→ included in late-payment statistics

refund Case
→ relevant refund Event IDs included in refund statistics

outstanding Case
→ represented in outstanding statistics
```

The purpose is to verify:

```text
Agent Case interpretation
        ↓
was correctly carried into
        ↓
deterministic aggregation
```

The Verifier is not deciding whether the original Agent classification itself was correct.

---

## 26.5 Final Missing-Invoice-ID Scan Completed

The workflow must confirm that the final missing-`invoice_id` scan occurred before aggregation.

Important missing-ID monetary events must not be silently ignored.

---

# 27. Summary Aggregation and Agent Review

Once all Case Documents are complete and the final missing-`invoice_id` scan is finished:

```text
aggregate_billing_summary
```

produces the structured overall Billing Summary.

The Agent then performs a second-level review.

This review is different from the earlier Case-level reasoning.

## First Agent reasoning stage

```text
Invoice Case
→ semantic interpretation
```

## Second Agent reasoning stage

```text
all aggregated billing facts
→ overall relationship interpretation
→ report narrative
```

The Agent should check for obvious inconsistencies between:

```text
its individual Case interpretations
and
the final aggregate summary
```

However, it should not manually recalculate the aggregate totals.

---

# 28. PDF Generation

Only after:

```text
all Invoice Cases analyzed
        ↓
missing-invoice-id scan complete
        ↓
aggregation complete
        ↓
Agent overall review complete
        ↓
Verifier PASS
```

should `create_report` be called.

The report should use the deterministic structured Billing Summary as the source for financial facts.

The Agent may write the explanatory narrative around those facts.

The expected report filename remains:

```text
billing_summary_merid001.pdf
```

---

# 29. Expected Final Architecture

The intended architecture after the upgrade is:

```text
Raw billing.csv
      ↓
Structured Data Reading
      ↓
Missing Account Resolution
      ↓
Target Account + Date Range
      ↓
Deterministic Invoice Case List
      ↓
┌──────────────────────────────────────┐
│ Agent analyzes each Invoice Case     │
│                                      │
│ lifecycle                            │
│ normal / abnormal                    │
│ multi-label classification           │
│ event-role selection                 │
│ nearby-row investigation if needed   │
│ deterministic calculation calls      │
└──────────────────────────────────────┘
      ↓
Structured Invoice Case Documents
      ↓
Final Missing-Invoice-ID Scan
      ↓
Case corrections / additions if needed
      ↓
Deterministic Summary Aggregation
      ↓
Structured Billing Summary
      ↓
Agent Overall Review
      ↓
Simple Deterministic Verifier
      ↓
PDF Report
```

---

# 30. Explicit Non-Goals

Do not expand this challenge into a larger platform redesign.

Do not introduce the following unless they are strictly required by the existing implementation:

```text
database migration
vector database
cursor-based dynamic pagination
source snapshot/version architecture
resolution confidence scoring
second semantic-verification Agent
supervisor / worker multi-Agent architecture
policy engine
general accounting rules engine
new orchestration framework
LangGraph migration
large-scale finance platform abstractions
```

The objective is to repair and strengthen the existing small repository, not to replace it.

---

# 31. Expected Behavioral Improvement Versus Baseline

The upgraded system should eliminate the baseline behavior:

```text
read 100 raw rows as a giant text table
        ↓
Agent reconstructs CSV manually
        ↓
Agent writes temporary parsing helpers
        ↓
Agent writes financial arithmetic
        ↓
Agent repeatedly debugs Python
        ↓
context grows rapidly
        ↓
max_steps reached
        ↓
PDF not produced
        ↓
runner still displays OK
```

The desired behavior is:

```text
inspect scope
        ↓
retrieve structured data
        ↓
analyze one Invoice Case
        ↓
save structured interpretation
        ↓
repeat
        ↓
scan missing-ID events
        ↓
deterministically aggregate
        ↓
verify
        ↓
produce PDF
```

---

# 32. Implementation Priorities

When modifying the repository, prioritize the work in this logical order:

```text
1. structured billing retrieval and basic type parsing

2. complete date-range retrieval without silent truncation

3. missing account_id resolution before filtering

4. Invoice Case listing and INV-* / CN-* distinction

5. Invoice Case structured schema and persistence

6. deterministic calculation capability

7. Agent billing workflow / lifecycle instructions

8. case-by-case Agent analysis

9. missing-invoice-id final scan

10. deterministic aggregation

11. simple verifier

12. PDF generation gate and final report
```

Do not spend the implementation effort on unrelated architectural improvements.

---

# 33. Existing Data Cases That Must Be Handled

The implementation should be able to reason correctly over the patterns already present in `billing.csv`, including at minimum:

```text
normal invoices
late payments
reconciliation exception and rounding adjustment
duplicate payment followed by refund
manual reconciliation
incorrect remittance reference
invoice dispute and correction
credit notes and credit application
delayed credit application
partial payments
planned split payments
duplicate/resubmitted invoice events
missing account_id
missing invoice_id
genuinely unmatched payment
refund of unmatched payment
post-settlement adjustment
unknown/unclassified abnormalities
```

The purpose is not to hard-code the exact dataset answers.

The purpose is to provide enough structure that the Agent can correctly investigate and classify these Cases while deterministic components preserve financial calculation reliability.

---

# 34. Final Design Principle

The upgraded system should preserve this separation:

```text
Agent
├── investigates
├── understands Invoice lifecycles
├── interprets abnormal behavior
├── chooses Case labels
├── chooses which Events play which financial roles
├── handles unknown Cases
└── writes the final business interpretation

Deterministic Tools
├── retrieve structured data
├── preserve complete requested ranges
├── resolve missing account_id through invoice linkage
├── enumerate Invoice Cases
├── read source amounts
├── perform exact arithmetic
├── enforce Case schema
├── aggregate results
└── verify workflow consistency
```

The central architectural goal is:

> Do not use deterministic code to replace Agent semantic judgment.
> Do not use Agent reasoning for work that can be made reliably deterministic.

The final system should therefore remain an Agent-based billing analyst, but with a deterministic data and financial harness around the Agent so that the report is substantially more complete, auditable, and reliable than the current baseline.

```
```
