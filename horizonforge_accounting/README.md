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
- The menus are window actions on MIS's report view with `active_model` / `active_id` in
  their context. On Odoo 19 the MIS widget gets no field value (`props.value` no longer
  exists for field widgets) and falls back to `active_id`, which MIS's own Preview button
  sets by being a button. Without it the page fails with "Invalid ids list". This is an
  upstream MIS Builder bug, worth reporting to OCA/mis-builder.
- **Budget vs. actual:** the P&L lines are budgetable. Create an MIS budget for the Profit
  and Loss template, then add a column with the budget as its source.
- OCA's **Cash Flow** (`mis_builder_cash_flow`) is a forward-looking forecast of bank
  balances from open invoices and bills, not a statement of cash flows.
- PDFs use a compact layout (`report/mis_report_templates.xml`): company top-left, title
  and period top-right, no shading, rules only above totals. MIS styles have no borders,
  so `mis.report.style` gets a **Rule Above** property (`hf_rule`). It's added by overriding
  `merge()` and `to_css_style()`, not MIS's module-level `PROPS` list, which every database
  on the server shares.

## Payment states

Odoo Community normally marks an invoice or bill Paid as soon as a payment is registered,
because it assumes nothing reconciles bank statements. Here OCA's `account_in_payment` is
installed, so they stay **In Payment** until the payment is matched with the bank: paid in
the books, not yet cleared. That's what the reconcile screen and the outstanding balance on
the dashboard's bank cards show.

With that module, core stops forcing payments through an outstanding account, and a payment
method without one would post no journal entry. `account.payment._compute_outstanding_account_id()`
therefore falls back to the chart's Outstanding Payments / Outstanding Receipts for bank and
card journals. Upgrading to 19.0.0.7.0 recomputes stored Paid states once (migration).

## Payment lists

Core's payments list has one signed Amount column, money out negative, so its total is
net cash. Here it is replaced by **Paid Out** and **Received**, both positive with their
own totals, like a check register (`hf_amount_out` / `hf_amount_in`, stored, so they also
total when grouped). The Checks to Print list opened from the dashboard shows one positive
**Check Amount** instead (context `hf_checks_to_print`). Journal entries and accounting
reports keep their usual signs.

The list also has **Check No.** and a **Status** column (`hf_status`, stored) that splits
core's In Process: **To Print** for a check not printed yet, **In Payment** once printed
(or for any other payment waiting to clear), then **Paid** when matched with the bank. It
mirrors the bill's status. It is display only: the payment's real state stays core's,
because reconciliation depends on it, and the form's status bar still shows it.

## Printing checks

The **QuickBooks Voucher Check (Top)** layout prints on pre-printed QuickBooks-compatible
voucher checks: an 8.5 x 11 in sheet with the check at the top and two stubs. The bank
details, check number and MICR line are already on the stock, so only the date, payee,
amount, amount in words, payee address (placed for a double-window envelope) and memo are
printed. Both stubs show the payee, date, check number and the bills paid.

Setup sets it as the company's check layout when none is chosen. To print:

1. On the bank journal (Configuration > Journals, Outgoing Payments tab), make sure
   **Checks** is an outgoing payment method, and set the next check number.
2. Pay a bill (or several). From a bank journal the payment window defaults to the Checks
   method, unless the bill or vendor has a preferred method; credit card journals default
   to Manual Payment. With Checks there are two buttons instead of Create Payment:
   - **Pay and Print** records the payment and prints at once. With pre-numbered checks
     Odoo first asks for the number of the first check in the printer; with Manual
     Numbering on the journal the PDF opens straight away.
   - **Pay, Print Later** records the payment and puts the check in the print queue.
3. The bank journal's card on the Accounting dashboard shows **N checks to print** (opening
   the list) and a **Print Checks** button that prints the whole queue in one PDF, oldest
   first. In the Payments list, select checks and click **Print Checks** for just those
   (filter Checks to Print shows the queue). That button replaces core's Confirm, which
   only posts drafts; Actions > Post Payments still does that. Payment Receipt is under
   Actions too, so Print Checks is the one print button.

**Vendor credits:** select a vendor's bills together with their credit notes and click Pay.
Paying by check turns on **Group Payments**, so each vendor gets one check for the net
amount, with the credits used against the bills. (Core pays each bill separately and books
each credit note as money received, which would mean mailing several checks.) The stub
lists each bill at what it settles, then the credits as negative lines, adding up to the
check. When a vendor's credits exceed the bills, the vendor owes you: Odoo proposes an
incoming payment on Manual Payment, not a check. Bills with installment payment terms pay
the installment that's due, as core does.

**Handwritten checks:** select queued checks in the Payments list (or open one) and use
Actions > **Record Handwritten Check**. It suggests the next check numbers in date order,
each editable, then marks the checks sent and takes them out of the queue. Numbers must be
unique per bank journal. With Manual Numbering on the journal, its next number moves past
the highest one used, so the printer doesn't reuse a number from the same book. Core's
Post Payments is unchanged: it only posts drafts.

Either way the payment is posted to Outstanding Payments and the bill shows **In Payment**;
printing gives the payment its check number and marks it sent. The bill turns **Paid** when
the check clears: the bank feed line is reconciled with the payment. For a bank draft or anything else paid
without a check, use the Manual payment method, which never enters the queue.
4. Lines that don't fit on one stub continue on extra pages marked VOID, when
   **Multi-Pages Check Stub** is on in Settings; otherwise the stub is cut short with "...".

**Lining up the printer:** print a payment on plain paper, hold it over a blank check
against the light, and adjust **Check Top Margin** and **Check Left Margin** in Settings >
Accounting. They move everything on the page; at their default, 0.25 in, the layout prints
where it was designed. Raise a value to move the print down or right. Turn off
**Print Date Label** if the stock already says DATE. Print at 100% ("Actual size"), never
"Fit to page".

Core opens the new payment after paying instead; `account.payment.register.action_create_payments()`
is overridden for the Checks method only, and keeps core's behavior when no check layout is
set, so paying never fails on a missing setting. The queue is
`account.journal._hf_checks_to_print_domain()`: core's Checks to Print filter, plus checks
already Paid, which a payment posted straight to the bank account becomes.

The layout is `report/check_qb_voucher.xml`. Field positions are absolute, in inches from
the sheet's top left corner, on a zero-margin Letter paper format, so they can be tuned for
other stock in one place. Blank check stock with a printed MICR line is not supported.

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
| `tests/test_check_printing.py` | Default layout, check and stub contents, VOID pages, margins, Pay and Print, Pay Print Later, the queue and batch printing, In Payment until cleared, handwritten checks |
| `tests/test_ui.py` | In a browser: each statement renders, and the OCA report wizards and MIS list open |
| `tests/test_qb_import.py` | Parsing QBO exports, mapping, tie-out, open items, bank journals, history, mismatches |

The Plaid connector has its own tests (all Plaid calls mocked):

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_plaid -i account_statement_import_online_plaid \
    --test-tags /account_statement_import_online_plaid --stop-after-init --http-port 8079
dropdb test_plaid
```
