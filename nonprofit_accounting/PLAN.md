# Nonprofit Accounting: Project Plan

## Goal

A simple, standalone, cash-basis ledger for a small nonprofit school on Odoo 19
Community. It records deposits and payments, tracks income by source,
reconciles bank statements, and prints a period report:
beginning balance + income − expenses = ending balance.

## Decisions

| Topic | Decision |
|---|---|
| Accounting basis | Cash basis only (no receivables, payables or pledges) |
| Restrictions | None. All money is unrestricted operating funds |
| Company / currency | Single company, USD |
| Income sources | Two supporting districts (operating funds). No individual donors, donor reports or tax receipts |
| Chart of accounts | Ship a default starter chart (editable) |
| Existing data | None to migrate. CSV import may come later |
| Users | Bookkeeper (full access) and Viewer (read-only, reports) |

## How it works

Everything is double-entry underneath, so the books always balance. But the
user mostly fills in simple forms:

- **Deposit**: bank account, date, received from (e.g. a district), lines of *income account + amount*
- **Payment**: bank account, date, paid to, check # / reference, lines of *expense account + amount*
- **Transfer**: between two bank/cash accounts (e.g. checking → petty cash)
- **Journal entry**: manual debits/credits for adjustments and opening balances

The bank side of each deposit, payment and transfer is generated automatically.

## Models

| Model | Purpose | Key fields |
|---|---|---|
| `np.account` | Chart of accounts | code, name, type (bank/cash, liability, equity, income, expense), active |
| `np.move` | Transaction header | type (deposit / payment / transfer / journal), date, bank account, partner, reference, memo, state (draft / posted), lines |
| `np.move.line` | Debit/credit line | account, partner, label, debit, credit, cleared flag, reconciliation |
| `np.reconciliation` | Bank statement reconciliation | bank account, statement date, beginning balance, ending balance, cleared lines, difference, state, statement PDF |
| Lock date | Setting on the company | No posting, editing or reset to draft on or before this date |
| `res.partner` | Payers/payees | Districts, vendors (standard contacts, no extension needed) |

## Milestones

### M0: Project setup ✅
Module skeleton, CLAUDE.md, README, PLAN, git branch.

### M1: Ledger core ✅
- Chart of accounts plus the default starter chart (data file)
- Deposit, payment, transfer and journal entry forms (`np.move`)
- Payments: enter the bill first (bill date, bill/invoice #), then **Pay**
  (paid date defaults to the bill date and can be changed, plus bank account
  and check #). Unpaid bills stay off the books (cash basis). **Bills** menu
  (Unpaid filter by default); **Payments** is the paid check register;
  **Mark Unpaid** voids a payment
- Pay From default: the account this vendor was last paid from, else the
  default payment account in Settings, else the only bank account
- Posted entries must balance (debits = credits)
- **Posted entries can be reset to draft until their date is locked**
  (see the reset-to-draft note below)
- Lock date setting
- Menus, list/form/search views, two user groups, access rights
- Opening balance entry for each bank account
- Tests: balancing, posting, reset to draft, lock date

### M1.5: Dashboard ✅
- App opens on a dashboard: one card per bank/cash account with current
  balance and quick buttons (New Deposit / New Bill / Transfer), plus an
  unpaid-bills summary
- Show **Home Action** on the user form so each user can land on the dashboard
- Later: last reconciled date and uncleared totals per card (after M4)

### M2: Income tracking
- Income accounts for each district: 4010 North, 4020 South (in the starter chart)
- Optional starter contacts for the two districts, used as "received from"
- "Received from" partner on deposits; filter and group income by source
- Income summary by account and source for any date range (list/pivot view)

### M3: Period report (PDF + on-screen)
For a chosen date range, optionally limited to one bank account:

```
Beginning balance (bank/cash accounts as of start date)
+ Income       (by account)
− Expenses     (by account)
= Ending balance (bank/cash accounts as of end date)
```

- Include transfers between bank/cash accounts in the balances but leave
  them out of income/expense
- Check: beginning + income − expenses must equal the ending balance; flag it
  on the report if not
- Wizard: date from / date to / bank account → PDF (QWeb) or on-screen

### M4: Bank reconciliation
Statement-match method:
1. Pick bank account, statement date and statement ending balance
2. Beginning balance comes from the last completed reconciliation
3. List of uncleared posted bank lines up to the statement date, each with
   a checkbox
4. Running totals: cleared deposits, cleared payments, **difference**
5. Can only finish when the difference is $0.00. Finishing marks the lines
   as reconciled
6. Reconciled lines can't be edited or reset to draft unless the
   reconciliation is reopened
7. Attach the statement PDF (binary field plus chatter attachments)

### M5: Later / nice-to-have
- CSV import of bank transactions (create draft deposits/payments)
- CSV import of the chart of accounts
- Budget vs. actual on the period report

## Reset to draft (M1 question)

**Recommendation: yes, with guardrails.** A posted entry can be reset to draft
while its date is after the lock date. Small-office bookkeepers correct
mistakes this way, and Odoo's own accounting works the same. Guardrails:
- Not allowed once the entry's date is on or before the lock date
- Not allowed once any of its lines are reconciled (M4)
- Bookkeeper group only
- State changes are tracked in the chatter (who and when), as an audit trail

After the period is locked, corrections are made with a new entry dated in
the open period.

## Starter chart of accounts

Loaded on install as editable data (`noupdate`). Accounts can be renamed,
added or archived. 4-digit codes.

| Code | Name | Type |
|---|---|---|
| 1000 | Checking | Bank/Cash |
| 1010 | Savings | Bank/Cash |
| 1050 | Petty Cash | Bank/Cash |
| 2100 | Payroll Withholdings | Liability |
| 3000 | Net Assets (Opening Balances) | Equity |
| 4010 | North District Support | Income |
| 4020 | South District Support | Income |
| 4300 | Contributions & Fundraising | Income |
| 4800 | Interest Income | Income |
| 4900 | Other Income | Income |
| 5000 | Salaries & Wages | Expense |
| 5100 | Payroll Taxes | Expense |
| 5200 | Employee Benefits | Expense |
| 5300 | Instructional Supplies | Expense |
| 5400 | Office Supplies & Postage | Expense |
| 5500 | Rent & Facilities | Expense |
| 5600 | Utilities | Expense |
| 5700 | Insurance | Expense |
| 5800 | Professional Fees | Expense |
| 5900 | Repairs & Maintenance | Expense |
| 6000 | Transportation | Expense |
| 6100 | Food Service | Expense |
| 6900 | Bank Fees | Expense |
| 6950 | Miscellaneous | Expense |

Petty cash is its own cash account. Moving money into it is a **Transfer**
(checking → petty cash), and spending from it is a **Payment** from petty cash.

## Open questions

None for now. Ready for M1.
