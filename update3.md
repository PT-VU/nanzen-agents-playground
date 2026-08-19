
# Expected Billing PDF Content

## 1. Core Objective

The final PDF should be a concise, customer-ready billing summary focused on the financial state of the billing relationship.

The `billing_summary` task requires the report to:

1. Summarize total invoiced versus total paid.
2. Identify late payments and outstanding invoices.
3. Include:
   - a summary paragraph of the billing relationship;
   - a table of all invoices with their status and amounts;
   - notable findings such as disputes, credits, and late payments.

The report should therefore focus on **invoice-level financial state**, not on the Agent's internal reasoning, event-processing workflow, or analysis metadata.

---

## 2. Required PDF Content

### A. Billing Relationship Summary

The report should begin with a short summary containing only information that is directly useful for understanding the billing relationship.

Include:

- Account: Meridian Health / MERID-001
- Billing data period / data cutoff
- Number of invoices
- Total invoiced
- Total valid paid
- Total outstanding
- Number of invoices that were eventually paid late
- Number of invoices that are currently outstanding
- A simple distinction between outstanding invoices that are:
  - overdue;
  - not yet due.

For the current analyzed dataset, the summary should reflect:

- 28 invoices
- Total invoiced: **€509,852.11**
- Total valid paid: **€472,684.95**
- Total outstanding: **€37,167.16**
- **10 invoices were paid late**
- **2 invoices are currently outstanding**
  - `INV-2025-MH-023`: overdue and unpaid
  - `INV-2026-MH-028`: unpaid but not yet due at the data cutoff

The purpose of this section is to allow an account manager to understand the current billing position within a few seconds.

---

### B. Invoice Table

The main invoice table should contain only the invoice-level financial information required by the task.

Use five columns:

| Column | Purpose |
|---|---|
| Invoice ID | Unique invoice identifier |
| Amount (EUR) | Final effective invoice amount |
| Valid Paid (EUR) | Payments that validly settle the invoice |
| Outstanding (EUR) | Amount that remains unsettled |
| Status | Current payment state |

The `Status` field should use the payment-state vocabulary already used by the implementation, such as:

- `fully_paid`
- `partially_paid`
- `outstanding`

For an invoice that has passed its due date but remains unpaid, the payment state should still be **outstanding/unpaid**, rather than replacing the payment state with a label such as `payment overdue`.

Whether the invoice is overdue should instead be represented through the underlying timing information and, where relevant, explained in the summary or notable findings.

The main table should represent the final financial state of each invoice.

It should **not** reproduce detailed anomaly analysis or internal billing-event history.

---

### C. Notable Findings

Billing anomalies, exceptions, and relevant historical context should be presented after the invoice table as concise explanatory findings.

Only include events that materially affect interpretation of the billing relationship.

Relevant findings may include:

- the observed late-payment pattern;
- currently overdue outstanding invoices;
- duplicate payments and corresponding refunds where the original invoice was nevertheless correctly settled;
- invoice disputes and corrections;
- duplicate or resubmitted invoice events that required selecting the correct effective invoice amount;
- reconciliation adjustments;
- SLA credits and their application;
- misdirected payments and subsequent returns;
- goodwill or other adjustments that remain pending future reconciliation;
- material data-quality observations where there is sufficient evidence that they affect completeness or interpretation.

These findings should be written as short customer-facing explanations.

Do not expose internal Case labels or raw Agent reasoning.

A missing monthly invoice record, such as the absence of a January 2024 invoice, should only be presented as a data-completeness concern if the available evidence supports the conclusion that an invoice should have existed. Absence alone should not automatically be described as a confirmed data error.

---

## 3. Information That Should Not Appear in the Final PDF

### A. Do Not Include Internal Analysis Metadata in the Invoice Table

The following information is useful internally but is not required in the customer-facing invoice table:

- Timing classifications such as:
  - `on_time_or_early`
  - `late`
  - `unpaid`
  - `unknown`

- Internal Case labels such as:
  - `late_payment`
  - `payment_reminder`
  - `multiple_payments`
  - `manual_reconciliation`
  - `duplicate_or_resubmitted_invoice`
  - `adjustment`
  - `credit_applied`
  - other internal anomaly classifications

- Payment reminder history
- Internal reconciliation classifications
- Billing Event IDs such as `BIL-5105`
- Dispute IDs
- Internal workflow states
- Agent reasoning metadata

These fields may remain available internally in the structured Invoice Case Documents.

They should only be translated into natural-language findings when they materially affect the billing conclusion.

In particular, do not expose a long `Case Labels` column in the invoice table. It adds internal implementation detail and can make the report difficult to read.

---

### B. Do Not Include Unnecessary Customer Profile Information

The billing report does not need general account-profile information that is unrelated to the billing task.

Do not include fields such as:

- Industry
- Customer segment
- City / country
- Employee count
- Company annual revenue
- Website
- Primary contact
- Other CRM profile fields

These fields may exist in other data sources, but they are not required to answer the billing task.

Company annual revenue is particularly inappropriate because it could easily be confused with revenue generated from the billing relationship being analyzed.

---

### C. Optional Chart

The billing task does not require a chart, but a chart is allowed when the Agent determines that it materially improves readability.

The PDF renderer supports charts as an available rendering capability, but chart support does not imply that every report should contain one by default.

For this task, the invoice table and notable findings remain the required core content.

The Agent may include a concise chart if it helps an account manager understand the billing state faster, such as a compact invoice amount versus outstanding balance chart.

If a chart is included, it must not replace the invoice table or notable findings, and it must not introduce internal fields such as case labels, timing metadata, event IDs, or workflow states.

---

## 4. PDF Tool Requirements

The PDF generation tool supports the following section types:

- heading
- paragraph
- table
- chart

These are rendering capabilities only.

The tool itself does **not** require:

- a minimum number of sections;
- at least one table;
- at least one chart;
- an image;
- a fixed report structure.

The content requirements come from the `billing_summary` task, not from the PDF renderer.

For the billing task, the required content is therefore:

1. a billing relationship summary paragraph;
2. a table covering all invoices with their status and amounts;
3. notable findings covering relevant disputes, credits, late payments, and other material billing exceptions.

A chart is optional and should be included only when it materially improves readability.

---

## 5. Table Width and Layout

The current PDF renderer uses:

- portrait A4;
- 2.5 cm left margin;
- 2.5 cm right margin;
- a ReportLab `Table` with repeated header rows.

The renderer does not explicitly define column widths or automatically enforce a maximum table width.

Therefore, long textual columns can cause the invoice table to become too wide for the available page area.

The preferred solution for the billing report is **not** to expand or redesign the PDF renderer.

Instead, keep the customer-facing table intentionally narrow and restrict it to the information actually required by the task.

The recommended five-column schema is:

```text
Invoice ID
Amount (EUR)
Valid Paid (EUR)
Outstanding (EUR)
Status
````

Detailed anomalies should remain outside the table in the Notable Findings section.

---

## 6. Recommended Final PDF Structure

```text
Billing Summary - Meridian Health (MERID-001)

1. Billing Relationship Summary
   - Data period / cutoff
   - Invoice count
   - Total invoiced
   - Total valid paid
   - Total outstanding
   - Number of invoices paid late
   - Number and current state of outstanding invoices

2. All Invoices

   Invoice ID
   Amount (EUR)
   Valid Paid (EUR)
   Outstanding (EUR)
   Status

3. Notable Findings
   - Late-payment pattern
   - Outstanding / overdue invoices
   - Duplicate payments and refunds
   - Invoice corrections and disputes
   - Credits
   - Adjustments
   - Other material billing anomalies
   - Relevant data-quality observations where justified
```

---

## 7. Core Principle

**Internal analysis may be complex; the final PDF should remain simple.**

The internal Agent workflow may maintain information such as:

```text
Timing
Case Labels
Event IDs
Reconciliation State
Anomaly Types
Lifecycle Events
```

These fields exist to support correct reasoning, deterministic aggregation, and verification.

They should not automatically appear in the customer-facing report.

Only information that materially changes the interpretation of the billing relationship should be converted into concise natural-language Notable Findings.

The final report should primarily answer three questions:

1. **How much have we invoiced?**
2. **How much has the customer validly paid, and how much remains outstanding?**
3. **What billing anomalies, unresolved issues, or material risks should the account manager know about?**

```

