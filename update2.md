你这个批评是对的。上一版的问题主要有两个：**把“升级说明”写成了“完整设计文档”**，这会诱导 Codex顺手重构更多东西；另外我用了太多具体 case example，确实可能变成对 Agent 的答案提示，而不是只描述我们希望系统具备的能力。

所以第二轮升级文档应该遵守两个原则：**只描述相对 V1 的增量修改，不重复整个架构；只写通用 billing semantics 和系统行为，不写具体 invoice 的标准答案或具体 event 对应关系。**

下面是更合适的版本：

````markdown
# Billing Agent Upgrade V2

## 1. Scope

This is an incremental upgrade on top of the existing V1 billing-agent implementation.

Do not redesign the current architecture.

Keep the existing:
- structured billing retrieval;
- Invoice Case analysis;
- fixed Case Document schema with optional fields;
- deterministic calculation;
- aggregation;
- verifier;
- PDF generation workflow.

This upgrade only fixes several billing-semantic and consistency issues found after the first full run.

---

## 2. Billing-Specific Prompt

First inspect the current prompt structure.

If a billing-specific instruction block already exists, extend it.

If billing-specific rules are still stored in the shared ActorAgent prompt, separate them so that:

```text
shared prompt
→ only generic Agent behavior

billing-specific prompt
→ billing lifecycle and billing analysis rules
````

Do not expose billing-specific rules to unrelated workflows such as usage or support analysis.

---

## 3. Refund Lifecycle

Add the following billing rule:

A refund can contain multiple lifecycle events, such as:

```text
refund initiated
→ refund completed
```

Multiple lifecycle rows describing the same refund must not be interpreted as multiple independent refunds simply because each row contains an amount.

For realized refund statistics, only the event representing the completed refund should contribute to the final refund amount.

Earlier refund lifecycle events remain relevant Case evidence but must not cause duplicate financial counting.

The Agent should identify the semantic role of refund events.

The deterministic aggregation layer should calculate refund totals from the Event IDs selected as realized refunds.

---

## 4. Duplicate Payment and Settlement

Add the following billing rule:

A duplicate payment is not a second valid settlement of the invoice.

The Agent must distinguish:

```text
valid settlement payment
duplicate / overpayment
```

Only valid settlement payment Event IDs should be stored in:

```text
payment_amount_event_ids
```

Duplicate payments should remain classified separately.

A later duplicate payment must not change the invoice's settlement date.

---

## 5. `paid_date`

Standardize `paid_date` as:

> The date on which valid cumulative payments first fully settle the invoice.

Therefore:

* for a normal single payment, use the valid payment date;
* for partial or split payments, use the date when cumulative valid payments first fully settle the invoice;
* duplicate payments occurring after settlement do not change `paid_date`.

The Agent determines which payment events are valid settlement events.

The deterministic layer derives the final `paid_date` from those selected Event IDs.

---

## 6. Open / Unsettled Invoice Cases

Invoices without a completed payment must still participate in billing analysis.

They must not be excluded simply because their lifecycle is still open.

Every real Invoice Case should contribute to the appropriate statistics, including where applicable:

```text
invoice count
total invoiced
valid paid amount
outstanding amount
payment timing
```

An unpaid invoice still has a meaningful payment state and timing state.

---

## 7. Payment and Timing State

Keep the status vocabulary already used by the current implementation.

Current payment states:

- `fully_paid`
- `partially_paid`
- `outstanding`

Current timing states:

- `on_time_or_early`
- `late`
- `unpaid`
- `unknown`

Do not migrate or rename these states as part of this V2 upgrade.
This upgrade changes their calculation semantics where necessary, not their schema vocabulary.

---

## 8. Deterministic `days_past_due`

Derive `days_past_due` deterministically.

For a fully settled invoice:

```text
days_past_due
=
paid_date - due_date
```

For an invoice that is still not fully settled:

```text
days_past_due
=
billing_analysis_end_date - due_date
```

Use the analyzed billing dataset end date, not the current wall-clock date, so repeated runs over the same static dataset remain stable.

The deterministic layer should derive the timing result from the Agent-selected valid settlement events and the invoice due date.

---

## 9. Outstanding Amount

The deterministic calculation layer should derive:

```text
outstanding_amount
=
canonical invoice amount
-
valid settled payment amount
```

using the existing Case Document references and current financial logic.

Duplicate payments must not reduce outstanding a second time.

Refund lifecycle events must not be counted twice.

Open invoices must retain their outstanding balance.

---

## 10. Aggregation Changes

Review the current aggregation logic and ensure that:

* only valid settlement payments contribute to normal paid totals;
* duplicate payments are excluded from normal settlement totals;
* one refund lifecycle produces one realized refund amount;
* open invoices remain included in invoice and outstanding statistics;
* payment timing statistics are produced for all Invoice Cases where applicable.

Keep the existing V1 aggregation architecture.

Do not introduce a new finance rules engine.

---

## 11. Verifier Change

Add a deterministic consistency check between payment state and outstanding amount.

At minimum:

payment_status == "fully_paid"
→ outstanding_amount == 0

A fully-paid invoice with non-zero outstanding must fail verification.

The Verifier should only check deterministic consistency.

Do not make the Verifier independently re-evaluate the Agent's semantic decisions.

---

## 12. Responsibility Boundary

Keep the existing division of responsibility:

```text
Agent
→ determines semantic meaning of billing events
→ identifies valid vs duplicate payments
→ identifies refund lifecycle roles
→ determines Case classification

Deterministic layer
→ reads actual amounts
→ calculates paid amount
→ calculates paid_date
→ calculates outstanding
→ calculates days_past_due
→ aggregates final statistics

Verifier
→ checks final internal consistency
```

Do not move complex Case interpretation into deterministic rules.

---

## 13. Batch Case Document Tool

Add one deterministic tool for bulk Case Document construction.

Preferred tool name:

```text
build_invoice_case_documents
```

The purpose of this tool is to prevent the Agent from manually reading, printing, and saving all Invoice Case Documents one by one.

The tool should:

* read the complete structured billing data for the target account;
* enumerate all real `INV-*` Invoice Cases using the existing deterministic case listing logic;
* build one draft Case Document per Invoice Case;
* populate deterministic fields directly from source events;
* write the Case Documents to the existing Case Document directory;
* return only a compact summary to the Agent.

The tool must not return full raw billing rows or full Case Documents in normal operation.

Required input:

```json
{
  "account_id": "MERID-001",
  "start_date": null,
  "end_date": null
}
```

Required compact output:

```json
{
  "status": "PASS",
  "account_id": "MERID-001",
  "case_document_count": 28,
  "case_document_dir": "output/billing_case_documents/MERID-001",
  "requires_agent_review": [
    "INV-..."
  ],
  "errors": []
}
```

The generated draft Case Documents should include, when deterministically available:

* `invoice_id`;
* `analysis_status`;
* `case_labels`;
* `case_summary`;
* `canonical_invoice_event_id`;
* `lifecycle_event_ids`;
* `payment_amount_event_ids`;
* `refund_amount_event_ids`;
* `duplicate_payment_event_ids`;
* `adjustment_amount_event_ids`;
* `payment_status`;
* `timing_status`.

Each generated Case Document must use the existing Case Document schema.
The tool must save documents through the existing validation path, equivalent to calling `save_invoice_case`.
It must not bypass schema validation by writing arbitrary JSON directly.

The tool may assign conservative draft `case_labels` and `case_summary` values.
Agent review remains responsible for correcting semantic labels and summaries where the case is ambiguous.

The tool should mark a Case for Agent review when it detects any of the following:

* multiple payment events;
* refund lifecycle events;
* duplicate or resubmitted invoice events;
* dispute or correction events;
* credit note references or credit application events;
* missing `account_id` or missing `invoice_id` evidence;
* manual reconciliation;
* adjustment events;
* unpaid or partially paid invoices.

Agent workflow after this tool should be:

```text
build_invoice_case_documents
→ review only cases listed in requires_agent_review
→ save corrected Case Documents only where needed
→ scan_missing_invoice_ids
→ aggregate_billing_summary(use_case_documents=True)
→ verify_billing_summary
→ create_report
```

Do not require the Agent to print or inspect every generated Case Document.
If the Agent needs detail, it should request one specific Invoice Case at a time.

This tool is an extension of the existing V1 Case Document workflow.
Do not create a parallel document schema or a new aggregation path.

---

## 14. Audited Settlement Delta Path

The deterministic billing path must remain the default source of invoice-level financial truth.
However, the system must support a controlled abnormal path for edge cases where the strict formula below is insufficient:

```text
base_outstanding = invoice_amount - valid_cash_paid
```

This path exists for cases such as small write-offs, rounding residuals, approved settlement adjustments, or other abnormal events that change whether an invoice is considered settled without changing the actual cash paid.

### Required Data Model

Structured Invoice Case Documents may include these optional fields:

```json
{
  "abnormal_tags": ["rounding_writeoff"],
  "settlement_adjustment_cents": -1,
  "settlement_adjustment_event_ids": ["BIL-7028"],
  "settlement_adjustment_reason": "€0.01 rounding residual was written off and approved per policy."
}
```

Meaning:

* `settlement_adjustment_cents` is an audited delta applied after deterministic base calculation.
* `settlement_adjustment_event_ids` must point to source billing events supporting the delta.
* `settlement_adjustment_reason` must explain why the deterministic base formula requires an adjustment.
* `abnormal_tags` must classify the abnormal condition.

The aggregation formula becomes:

```text
base_outstanding = invoice_amount - valid_cash_paid
effective_outstanding = base_outstanding + settlement_adjustment_cents
```

`valid_cash_paid` must not be changed by this mechanism.
It remains the amount of actual valid customer payment.
The delta only affects effective settlement state and effective outstanding balance.

### Hard Limits

For the first implementation, non-zero settlement deltas are limited to:

```text
abs(settlement_adjustment_cents) <= 1000
```

This is a €10.00 absolute cap.

Any larger commercial waiver, bad debt write-off, large credit, or negotiated discount must not silently pass through this small-delta path.
Those cases should remain explicit abnormal cases requiring further review or a separate controlled mechanism.

### Verifier Requirements

The verifier must force a full recalculation for every invoice case where:

```text
settlement_adjustment_cents != 0
```

For each such invoice, the verifier must check:

* `abnormal_tags` is present and non-empty.
* `settlement_adjustment_event_ids` is present and non-empty.
* `settlement_adjustment_reason` is present and non-empty.
* Every referenced event ID exists.
* Referenced adjustment events are attached to the same invoice lifecycle or clearly belong to the same invoice.
* The delta does not exceed €10.00 in absolute value.
* The referenced event amount supports the requested delta.
* The verifier recalculates:
  * canonical invoice amount;
  * valid cash paid;
  * base outstanding;
  * settlement adjustment;
  * effective outstanding.
* `effective_outstanding` must not become negative unless a future explicitly approved overpayment path is added.

### Status Semantics

The implementation should keep cash payment and settlement concepts separate.

Minimum required fields in aggregate rows:

```json
{
  "valid_paid_amount_cents": 9999,
  "base_outstanding_amount_cents": 1,
  "settlement_adjustment_cents": -1,
  "effective_outstanding_amount_cents": 0,
  "settlement_status": "settled"
}
```

The invoice table may display `effective_outstanding` as the final outstanding balance.
It must still preserve `valid_paid_amount` as actual cash paid.

Example:

```text
invoice_amount = €100.00
valid_cash_paid = €99.99
base_outstanding = €0.01
settlement_adjustment = -€0.01
effective_outstanding = €0.00
settlement_status = settled
```

This means the customer did not pay the final cent in cash, but the invoice is effectively settled because the residual was written off.

### Design Principle

This path must not let the Agent freely rewrite totals.
The Agent may propose a delta only through structured fields on the Case Document.
The deterministic tools then apply the delta, log it through the saved Case Document, and the verifier must re-check the affected invoice case from source events.

The abnormal path is therefore:

```text
deterministic base calculation
→ structured abnormal delta on the Case Document
→ deterministic aggregation applies the delta
→ verifier recalculates and audits the delta
→ final report explains the abnormal settlement if material
```

---

## 15. Implementation Requirement

Make these changes by modifying the existing V1 implementation rather than creating parallel replacement components.

Before adding any new file, Tool, schema, or abstraction, check whether the current V1 component can be extended directly.

The goal of V2 is to correct billing semantics and consistency, not to expand system complexity.


