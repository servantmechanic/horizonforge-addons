# HorizonForge Accounting: Project Plan

## Goal

Full small-business books on Odoo 19 Community: invoices and bills, bank and
credit card feeds, reconciliation, standard financial statements and job
profitability for contractors using `horizonforge_project_custom`. Built from
CE Accounting plus OCA modules, with small custom modules for the gaps.

`nonprofit_accounting` is reference only and is not part of this build: no
dependency on it, no code shared with it, and it isn't installed or tested
alongside it. This module borrows its UX ideas (dashboard cards, click-through,
compact spreadsheet-style reports), reimplemented on `account.move`.

## Decisions

| Topic | Decision |
|---|---|
| Ledger | Odoo's `account.move`, so invoices, bills, timesheets, MIS Builder and OCA reconciliation share one set of books |
| Accounting basis | Accrual only (standard Odoo). No cash-basis layer |
| Bank and card feeds | Plaid, by porting OCA `account_statement_import_online_plaid` to 19.0. CSV/XLSX file import as the fallback |
| Credit cards | A bank-type journal on a credit card liability account (not core's `credit` type, which OCA import and feeds reject). Card payments are internal transfers |
| Reports | MIS Builder (P&L, balance sheet, budget, cash flow) and `account_financial_report` (GL, trial balance, aging) |
| Job profitability | A separate bridge module, `horizonforge_job_accounting`, so the jobs module needs no MIS dependency |
| Migration | QuickBooks Online exports: chart, contacts, opening trial balance, open A/R and A/P, optional monthly history |
| Enterprise | Never. Everything runs on Community |

## OCA modules used (19.0)

| Need | Module | Repo |
|---|---|---|
| Full accounting menus and groups | `account_usability` | account-financial-tools |
| Fiscal year, lock dates | `account_fiscal_year`, `account_lock_date_update` | account-financial-tools |
| Depreciation | `account_asset_management` | account-financial-tools |
| Recurring entries | `account_move_template` | account-financial-tools |
| P&L, balance sheet, KPIs | `mis_builder` | mis-builder |
| Budget vs. actual | `mis_builder_budget` | mis-builder |
| Cash flow | `mis_builder_cash_flow` | account-financial-reporting |
| GL, trial balance, aging | `account_financial_report` | account-financial-reporting |
| Customer statements | `partner_statement` | account-financial-reporting |
| Reconciliation | `account_reconcile_oca` | account-reconcile |
| In Payment until cleared | `account_in_payment` | account-reconcile |
| Feed framework | `account_statement_import_online` | bank-statement-import |
| CSV/XLSX statements | `account_statement_import_sheet_file_xlsx`, `account_statement_import_file_reconcile_oca` | bank-statement-import |

These also pull in `date_range` (server-ux), `report_xlsx` and `report_xlsx_helper`
(reporting-engine), `account_statement_base`, `account_statement_import_base` and
`account_statement_import_file`. Python: `openupgradelib`, `xlrd`, `xlsxwriter`.
Plaid adds `plaid-python`.

## Milestones

### M0: Setup ✅
- OCA repos cloned at 19.0 under `~/odoo-dev/oca/` and added to `addons_path`
- Full set installed in a throwaway database with `horizonforge_project_custom`: no
  errors, and its existing tests pass

### M1: Accounting baseline ✅
- Module depending on the OCA set
- Contractor starter accounts (`noupdate`): Equipment and Vehicles with accumulated
  depreciation; Credit Card (`liability_credit_card`); Owner Contributions and Draws; job
  costs (Materials, Subcontractors, Labor, Equipment Rental, Permits & Fees); common
  operating expenses; Depreciation. Codes are padded to the chart's length, and taken
  codes are skipped
- Journals: Savings, Credit Card (a bank journal on the card liability, because OCA import
  and feeds reject core's `credit` type), Petty Cash. The chart's bank journal is checking
- Current fiscal year (`account_fiscal_year`). Lock dates: core plus `account_lock_date_update`
- Runs on install and whenever a company loads a chart. Re-running adds only what's missing
- Installed on `dev19`

### M2: Bank and card feeds (sandbox check pending)
- `account_statement_import_online_plaid` ported to 19.0 on branch
  `19.0-mig-account_statement_import_online_plaid` of `~/odoo-dev/oca/bank-statement-import`,
  to offer upstream. Fixes over 18.0: imports only the chosen account (a login can hold
  several), skips pending transactions, keeps bank dates, one Plaid call per pull, shared
  logins, reconnect (update mode) and unlink, admin-only access token, Link from Plaid's CDN.
  27 mocked tests
- To do: a Plaid sandbox pull into a test journal from the browser
- CSV maps: Chase card and checking, Amex, Discover, Capital One, Citi, Wells Fargo, generic
- Reconcile models: Owner Draw and Owner Contribution (charts already have Internal
  Transfers and Bank Fees). The OCA reconcile screen's Analytic column charges feed
  expenses to a job

### M3: Dashboard ✅
- Core's Accounting dashboard already has journal balances, items to reconcile, bills to
  pay and invoices owed, so it is extended rather than replaced
- Bank cards with a feed: last sync time or "Last sync failed", and a Sync button
- Plaid: scheduled pulls look back 14 days (configurable), because banks post many
  transactions days after their date

### M4: Financial reports ✅
- MIS templates from account types: Profit and Loss (month, YTD, last YTD), Profit and Loss
  by Month (12 months), Balance Sheet (today, last month end, last year end) with an Out of
  Balance check. Menus under Reporting > Statement Reports
- P&L lines are budgetable, for MIS budgets (budget vs. actual)
- Compact PDF layout, with a Rule Above style property for totals
- OCA's Cash Flow is a forecast, not a cash flow statement. A statement of cash flows is
  left for later

### M5: Job profitability (`horizonforge_job_accounting`) ✅
- `hf.job.profit.line`, a SQL view over the job's analytic lines: revenue (invoices and
  refunds), labor (timesheets at wage cost plus burden), bills, other costs, with profit and
  hours. Pivot, graph and list; each line opens its invoice, bill or timesheet
- Job Profitability list: contract, invoiced, to invoice, costs, profit, margin, hours.
  Profit smart button on the job
- Labor burden % in Settings > Project, next to the payroll settings
- No MIS Job P&L: timesheets don't post to the ledger, so MIS can't see labor. The pivot
  by job, month and category covers it

### M6: QuickBooks migration ✅
- Wizard: upload QBO exports, review the proposed account mapping, import
- Opening entry, open invoices and bills against Opening Balance Clearing (zero when the
  aging reports agree with the trial balance), optional monthly P&L history, contacts and
  bank journals

### M7: Check printing ✅
- QuickBooks Voucher Check (Top) layout for pre-printed voucher stock: check fields placed
  for QuickBooks checks and a double-window envelope, two stubs with the bills paid, VOID
  continuation pages. Built on core `account_check_printing` (numbering, Print Checks,
  Void); its margin settings fine-tune alignment
- Set as the company's check layout on install when none is chosen
- Paying by check: **Pay and Print**, or **Pay, Print Later** to queue the check. The bank
  card on the dashboard shows the queue count and prints the whole queue in one batch.
  Bank drafts use the Manual method, outside the queue
- Bills paid by check (or any payment) show In Payment until the bank clears them, then
  Paid: OCA `account_in_payment`, with bank and card payments kept on the outstanding
  accounts
- Vendor credits: paying by check groups by vendor (one net check per vendor), and the
  stub lists bills at what they settle plus the credits used
- Actions > Record Handwritten Check: enter the numbers of checks written by hand, which
  leaves them out of the print queue
- To do: a test print on real stock to confirm the positions

### Later
- OFX/QFX importer (missing in OCA 19.0)
- Statement of cash flows (indirect method) as an MIS template
- Report the MIS widget bug upstream (OCA/mis-builder 19.0: the widget reads `props.value`, gone since Odoo 17)
- 1099-NEC vendor flag and report
- WIP report for progress-billing jobs (over/under billing)
- Sales tax review per client
- Other check layouts (voucher middle or bottom, three per page); blank stock with MICR
