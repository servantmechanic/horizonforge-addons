# Nonprofit Accounting: Project Plan

## Goal

A simple, standalone double-entry ledger for small nonprofits on Odoo 19
Community. It should produce GAAP-style nonprofit statements without
Odoo's full `account` module.

## Assumptions (confirm or change)

- US nonprofit, following FASB ASC 958 (two net asset classes:
  *without* and *with* donor restrictions)
- Single company, single currency (USD)
- Accrual basis with simple cash-basis reporting optional (TBD)
- Users: a bookkeeper/treasurer (full access) and board members (read-only reports)

## Core concepts → models

| Concept | Model | Key fields |
|---|---|---|
| Chart of accounts | `np.account` | code, name, type (asset / liability / net assets / revenue / expense) |
| Fund | `np.fund` | name, restriction (none / purpose / time / perpetual) |
| Program | `np.program` | name (used for program-expense breakdown) |
| Journal entry | `np.move` | date, reference, state (draft / posted), lines |
| Entry line | `np.move.line` | account, fund, debit, credit, functional class, program, partner |
| Donor | `res.partner` (extended) | is_donor, giving history |
| Contribution | `np.contribution` | donor, date, amount, fund, pledge vs. received; generates a move |
| Fiscal period lock | field on company/settings | lock date: no posting before it |

## Milestones

### M0: Project setup ✅
Module skeleton, CLAUDE.md, README, PLAN, git branch.

### M1: Ledger core
- `np.account`, `np.fund`, `np.move`, `np.move.line`
- Constraint: posted entries must balance (total debits = total credits)
- Posted entries are read-only; corrections are made with reversing entries
- Menus, list/form views, access rights, two user groups
- Tests: balancing, posting, lock date

### M2: Donors & contributions
- Donor flag and giving history on contacts
- Contributions and pledges create journal entries automatically
- Donor acknowledgment letter (PDF) for gifts ≥ $250 (IRS requirement)

### M3: Restrictions
- Release-from-restriction entries (with → without donor restrictions)
- Fund balance report

### M4: Financial statements (PDF + on-screen)
- Statement of Financial Position
- Statement of Activities (columns by net asset class)
- Statement of Functional Expenses (program / M&G / fundraising)
- Trial balance and general ledger

### M5: Nice-to-haves
- Budgets vs. actual by fund/program
- Bank CSV import
- Form 990 line mapping
- Year-end close

## Open questions

- Cash or accrual basis, or both?
- Need multi-company (e.g. several nonprofits in one database)?
- Default chart of accounts: ship a starter template (UCOA-based)?
- Migrating existing data (e.g. QuickBooks export)?
