# HorizonForge Accounting

Small-business books on Odoo 19 Community. `horizonforge_accounting` installs the OCA
accounting set (reports, reconciliation, bank feeds) and adds contractor starter accounts,
journals, reconcile models, statement import maps and a fiscal year, plus feed status on the
dashboard, financial statements and a QuickBooks migration wizard. See `PLAN.md` for the
roadmap. Job profitability is in the bridge module `horizonforge_job_accounting`.

## Requirements

- Odoo 19 Community, run from source
- OCA repos at branch 19.0 on the addons path: `server-ux`, `reporting-engine`,
  `account-financial-tools`, `account-financial-reporting`, `mis-builder`,
  `account-reconcile`, `bank-statement-import`
- The Plaid connector `account_statement_import_online_plaid`, ported to 19.0 on branch
  `19.0-mig-account_statement_import_online_plaid` of `~/odoo-dev/oca/bank-statement-import`
  until it is merged upstream. Deploy that branch, not OCA's 19.0, on servers
- Python packages `openupgradelib` (for `account_usability`), `plaid-python`, `xlrd` and
  `xlsxwriter`

## Install and upgrade

Run from `~/odoo-dev`, with the server stopped:

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d <database> -i horizonforge_accounting --stop-after-init
venv/bin/python odoo/odoo-bin -c odoo.conf -d <database> -u horizonforge_accounting --stop-after-init
```

## What it sets up

Setup runs on install for every company with a chart of accounts, and again whenever a
company loads a chart. It only adds what's missing, so it never overwrites edits.

| Item | Details |
|---|---|
| Starter accounts | Equipment, Vehicles and their accumulated depreciation; Credit Card; Owner Contributions and Draws; job costs (Materials, Subcontractors, Labor, Equipment Rental, Permits & Fees); common operating expenses; Depreciation |
| Journals | Savings (`SAV`), Credit Card (`CARD`), Petty Cash (`CSH1`). Checking (`CHK`) only if the company has no bank journal yet; otherwise the chart's own bank journal is the checking account |
| Reconcile models | Owner Draw and Owner Contribution. Charts already have Internal Transfers and Bank Fees |
| Fiscal year | The current one, from the company's fiscal year end |

Starter account codes are four digits padded to the chart's code length, so `5100` becomes
`510000` on the generic chart. A code that's already in use is skipped. The generic chart
already has Credit Card at `201100`, so that one isn't created there.

Rename the chart's `Bank` journal to the checking account's name, and enter bank account
numbers, in Accounting > Configuration > Journals.

## How it works

- `res.company._hf_setup_accounting()` does the setup. The `post_init_hook` calls it for
  root companies, and `account.chart.template._post_load_data()` calls it after a chart loads.
- Each record it creates gets an XML id, `horizonforge_accounting.<company id>_<key>`, with
  `noupdate`. A record with that XML id, or with the same code, is never created again,
  so renamed accounts stay renamed. A deleted starter account comes back if setup runs again
  (a chart reload), so archive accounts instead of deleting them.
- **Credit cards are bank journals, not core's Credit Card type.** OCA's statement file
  import and online feeds only accept `bank` journals. The Card journal's default account is
  the credit card liability, so its balance shows what is owed. Add a journal and liability
  account for each further card.
- Lock dates use core's fields plus OCA's `account_lock_date_update` wizard.
- Upgrades don't rerun setup. A version that adds setup items runs just those in a migration
  script, as `migrations/19.0.0.2.0` does for the reconcile models.

## Bank and card feeds

### Plaid

1. Open the journal (Accounting > Configuration > Journals), set **Bank Feeds** to Online
   and the provider to Plaid.com, and save. The provider list is under Accounting >
   Configuration > Accounting > Online Bank Statement Providers.
2. On the provider, enter the Plaid **Client ID** and **Secret** and pick Sandbox or
   Production. Sandbox logins are `user_good` / `pass_good`.
3. Click **Link with Plaid**, log in to the bank, and choose the account for this journal.
4. Use **Pull Online Bank Statement** for history. After that, the scheduled pull runs
   hourly by default.

For a second account at the same bank (a card next to checking), set **Use Plaid Login Of**
on its provider instead of entering keys, then **Choose Account**. Plaid bills per login.
**Reconnect Bank** repairs an expired login, and **Unlink from Plaid** removes the login at
Plaid. The access token is readable by administrators only.

What the port changes from OCA's 18.0 version is listed in its `readme/HISTORY.md`. The main
fixes: only the chosen account is imported, pending transactions are skipped, dates stay
as the bank's, and a pull makes one Plaid call instead of one per day.

### CSV downloads

Accounting > Accounting > Import Statement accepts CSV and XLSX files with a statement map. The module
ships maps (`data/statement_import_maps.xml`, `noupdate`) for Chase card and checking,
American Express, Discover, Capital One, Citi, Wells Fargo, and a generic Date / Description
/ Amount file. Card maps turn purchases negative and payments positive, whatever sign the
issuer uses. Banks change formats now and then: if a map doesn't fit a download, copy it
under Accounting > Configuration > Accounting > Statement Sheet Mappings and adjust the copy.

CSV files have no transaction IDs, so importing overlapping date ranges imports lines twice.
Download from the day after the last import.

### Reconciling

Accounting > Accounting > Reconcile (`account_reconcile_oca`) matches statement lines to
invoices, bills and payments, or books them to an account with a reconcile model. The
**Analytic** column on a counterpart line charges an expense from the feed to a job.

## Dashboard

Accounting's own dashboard (Accounting > Dashboard) already shows each bank and card
journal's balance, items to reconcile, bills to pay and invoices owed. This module adds,
on journals with a bank feed:

- **Synced** with the time of the last successful pull, or **Last sync failed** in red,
  linking to the provider. The provider form shows the error.
- A **Sync** button that pulls from the last successful pull up to now, showing any error.

A failed scheduled pull stores its error in `online.bank.statement.provider.hf_last_error`,
and the next pull that works clears it.

## Financial statements

Accounting > Reporting > Statement Reports:

| Report | Columns |
|---|---|
| Profit and Loss | This month, year to date, last year to date |
| Profit and Loss by Month | The last 12 months |
| Balance Sheet | Today, end of last month, end of last year |

They are MIS Builder templates (`data/mis_reports.xml`) built from account types, not codes,
so they work on any chart and pick up new accounts. Each line expands into its accounts,
and every amount drills down to its journal items. The Balance Sheet includes an
**Out of Balance** line, hidden while it is zero.

- The report instances have no company, so they report on the company the user is working
  in. Change dates and columns on a copy (Accounting > Reporting > MIS Reporting > MIS
  Reports).
- **Budget vs. actual:** the P&L lines are budgetable. Create an MIS budget for the Profit
  and Loss template, then add a column with the budget as its source.
- OCA's **Cash Flow** (`mis_builder_cash_flow`) is a forward-looking forecast of bank
  balances from open invoices and bills, not a statement of cash flows.
- PDFs use a compact layout (`report/mis_report_templates.xml`): company top-left, title
  and period top-right, no shading, rules only above totals. MIS styles have no borders,
  so `mis.report.style` gets a **Rule Above** property (`hf_rule`). It's added by overriding
  `merge()` and `to_css_style()`, not MIS's module-level `PROPS` list, which every database
  on the server shares.

## QuickBooks migration

Accounting > Configuration > Import from QuickBooks (accounting managers). From QuickBooks
Online, export these as of one date (the last day of a month or year), on the accrual basis
with all accounts showing:

| Report | Needed |
|---|---|
| Account List | Yes |
| Trial Balance | Yes |
| A/R Aging Detail, A/P Aging Detail | For open invoices and bills |
| Customer Contact List, Vendor Contact List | Optional, for emails and phones |
| Profit and Loss, columns by month | Optional history, at least the fiscal year to that date |

The wizard reads CSV or XLSX, finds the column headings below QuickBooks' title lines, and
proposes a mapping: A/R, A/P and Retained Earnings go to Odoo's own accounts, accounts with
the same name map to existing ones, and the rest are created with a code from their type's
range (or the QuickBooks number). Every proposal can be changed before **Import**.

How it balances:

- One **opening entry** on the opening balance date posts the trial balance. A/R and A/P go
  to **Opening Balance Clearing** instead.
- Each open item from the aging reports becomes an invoice, credit note, bill or vendor
  credit against clearing, with its QuickBooks number as reference, its original date and
  due date, and the opening balance date as accounting date. Payments can then be matched
  to them as usual.
- With history, each month gets an entry dated its last day, offset to clearing, and the
  opening entry posts earnings from before the history to Retained Earnings instead of
  income and expense accounts.
- When the aging reports agree with the trial balance, clearing ends at zero, and the result
  page says so. Otherwise it shows what's left to fix.

New Bank and Credit Card accounts get a bank journal. A company can be imported once; the
opening entry is kept as `horizonforge_accounting.<company id>_qb_opening_move`.

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_horizonforge_accounting -i horizonforge_accounting \
    --test-tags /horizonforge_accounting --stop-after-init --http-port 8079
dropdb test_horizonforge_accounting
```

| File | Covers |
|---|---|
| `tests/test_setup.py` | Starter accounts, journals, fiscal year, re-running, edits surviving a re-run |
| `tests/test_statement_import.py` | Every statement map against a sample file, and the owner reconcile models |
| `tests/test_feed_dashboard.py` | Feed status on the dashboard, Sync, failed and recovered scheduled pulls |
| `tests/test_financial_reports.py` | P&L and Balance Sheet amounts, balance check, rules at totals, compact PDF |
| `tests/test_qb_import.py` | Parsing QBO exports, mapping, tie-out, open items, bank journals, history, mismatches |

The Plaid connector has its own tests (all Plaid calls mocked):

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_plaid -i account_statement_import_online_plaid \
    --test-tags /account_statement_import_online_plaid --stop-after-init --http-port 8079
dropdb test_plaid
```
