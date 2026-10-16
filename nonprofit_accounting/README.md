# Nonprofit Accounting

A simplified, standalone, cash-basis ledger for small nonprofits (first user:
a small school) on Odoo 19 Community. It does not depend on Odoo's `account`
module.

Records deposits, payments and transfers, tracks income by source, reconciles
bank statements, and produces a period report (beginning balance, income,
expenses, ending balance).

## Status

Early development. See [PLAN.md](PLAN.md) for scope and milestones.

## Install

```bash
cd ~/odoo-dev
venv/bin/python odoo/odoo-bin -c odoo.conf -d dev19 -i nonprofit_accounting --stop-after-init
```
