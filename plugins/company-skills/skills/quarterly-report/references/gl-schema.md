# GL Schema

Standard column mapping for the Acme finance general-ledger export.

| Column          | Type     | Description                              |
| --------------- | -------- | ---------------------------------------- |
| account_code    | string   | Account number, e.g. "4000"              |
| account_name    | string   | Human-readable account name              |
| period          | date     | YYYY-MM-DD, last day of accounting month |
| debit           | decimal  | Positive numbers only                    |
| credit          | decimal  | Positive numbers only                    |
| memo            | string   | Optional transaction memo                |

## Grouping for the narrative

| Account range | Category in report   |
| ------------- | -------------------- |
| 4000–4999     | Revenue              |
| 5000–5999     | Cost of revenue      |
| 6000–7999     | Operating expenses   |
| 8000–8999     | Other income/expense |
| 9000–9999     | Tax                  |

(Truncated example. In the real repo, this file would carry the full
chart-of-accounts mapping.)
