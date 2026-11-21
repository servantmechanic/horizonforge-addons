# Nonprofit Accounting

A simplified, standalone, cash-basis ledger for small nonprofits (first user:
a small school) on Odoo 19 Community. It does not depend on Odoo's `account`
module.

Records deposits, payments and transfers, tracks income by source, reconciles
bank statements, and produces a period report (beginning balance, income,
expenses, ending balance).

## Status

Testing. Milestones M0–M4 and report click-through are built. See
[PLAN.md](PLAN.md) for scope and milestones.

## Entering bills

A new bill starts on **Paid To**; Tab goes through Bill Date, Bill / Invoice #,
Memo, Pay From and Check #, then straight to a new line (Account first). On any
date field, **+** and **-** move the date a day later or earlier.

## Install

```bash
cd ~/odoo-dev
venv/bin/python odoo/odoo-bin -c odoo.conf -d dev19 -i nonprofit_accounting --stop-after-init
```
