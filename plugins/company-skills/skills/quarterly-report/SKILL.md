---
name: quarterly-report
description: |
  Use this when the user uploads a general-ledger export (CSV with columns
  like account_code, period, debit, credit) and asks for a quarterly
  financial summary, narrative, or board-ready document. Triggers on phrases
  like "Q3 report", "quarterly summary", "close out the quarter",
  "board package", or when a GL/ledger file is attached with an end-of-quarter
  date range. Does NOT trigger for monthly close, ad-hoc variance analysis,
  or non-financial reports.
version: 0.2.0
license: proprietary
---

# Quarterly Report Skill

Generates the finance team's standard quarterly narrative and accompanying
board package from a raw general-ledger export.

## When to use this

Trigger this skill when **both** of these are true:

1. A general-ledger CSV is attached (see `references/gl-schema.md` for the
   accepted schema), AND
2. The user's request is for a quarter-end deliverable: narrative,
   summary, board package, exec memo, or close-out doc.

If the user wants ad-hoc analysis on the GL data without quarterly framing,
do not use this skill — answer directly using standard data-analysis tools.

## Workflow

1. Confirm the quarter and fiscal year with the user before generating
   anything. Do not assume; finance teams have non-calendar fiscal years.
2. Load `references/gl-schema.md` to map the CSV columns to the report's
   line items. If columns don't match the schema, ask the user to confirm
   the mapping rather than guessing.
3. Run `scripts/aggregate.py <csv-path> --quarter <Q> --fy <YYYY>` to
   produce the aggregated figures. This script handles the standard
   accounting rules (debit/credit signing, account grouping, period
   filtering) deterministically.
4. Load `references/narrative-template.md` for the expected document
   structure and tone. Follow it closely — finance leadership expects
   consistency quarter to quarter.
5. Generate the narrative inline. The user can ask for a PDF afterward
   using the `pdf` skill if needed; don't create a PDF unless asked.

## Boundaries

- Don't include forecasts or guidance — this skill is for historical
  reporting only. If the user asks for forward-looking content, decline
  and suggest they use a separate forecasting workflow.
- Don't aggregate across fiscal years unless explicitly requested. The
  default scope is a single quarter.
- Don't include account-level detail in the narrative; use grouped
  categories from `references/gl-schema.md`. Account-level detail goes
  in the appendix only.

## Failure modes

- If the GL covers a date range narrower than the requested quarter,
  surface that gap to the user before proceeding — don't silently
  generate a partial report.
- If revenue or net income comes out negative when prior quarters were
  positive, flag this prominently in the executive summary. Don't bury it.
