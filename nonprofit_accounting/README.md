# Nonprofit Accounting

A simplified, standalone fund-accounting app for Odoo 19 Community. It does not
depend on Odoo's `account` module.

It tracks money by **fund** and **net asset class** (with or without donor
restrictions). Expenses are tagged by **function** (program, management &
general, fundraising). That supports the standard nonprofit financial
statements.

## Status

Early development. See [PLAN.md](PLAN.md) for scope and milestones.

## Install

```bash
cd ~/odoo-dev
venv/bin/python odoo/odoo-bin -c odoo.conf -d dev19 -i nonprofit_accounting --stop-after-init
```
