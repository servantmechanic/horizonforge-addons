# HorizonForge Addons

Addons for **Odoo 19 Community** (no Enterprise modules needed) for small
businesses, contractors, small schools and small nonprofits. Each folder is one
module: put this repository on Odoo's `addons_path` and install the modules you
want.

Try the school addons on the public demo: <https://school.horizonforge.tech>
(the logins are shown on the login page; the demo is rebuilt every night).

## Modules

| Module | What it does | Status | License |
|---|---|---|---|
| [`horizonforge_ce_custom`](horizonforge_ce_custom) | Small usability tweaks for any Community database: no quick-create of contacts and products, duplicate contact warning, +/- keys on dates, simple interface for non-admins, no odoo.com links or phone-home, no public sign-up | Stable | AGPL-3 |
| [`horizonforge_school_core`](horizonforge_school_core) | School records: years, grading periods, calendar, homerooms, students, patrons, courses, classes, setup guide | In development | LGPL-3 |
| [`horizonforge_school_gradebook`](horizonforge_school_gradebook) | Gradebook: categories, weights, grading scales, assignment schedules, keyboard grid, report cards | In development | LGPL-3 |
| [`horizonforge_school_attendance`](horizonforge_school_attendance) | Daily attendance by homeroom: present unless recorded, part days, summary report | In development | LGPL-3 |
| [`horizonforge_school_documents`](horizonforge_school_documents) | Shared school files: schoolwide, per year and per homeroom folders, files on the student | In development | LGPL-3 |
| [`nonprofit_accounting`](nonprofit_accounting) | Standalone cash-basis ledger for a small nonprofit: deposits, bills, transfers, bank reconciliation, period report. Does not use Odoo's Accounting app | In production | AGPL-3 |
| [`horizonforge_accounting`](horizonforge_accounting) | Small-business books on Community Accounting and OCA: bank feeds, reconciliation, financial statements, check printing, QuickBooks migration | In development | AGPL-3 |
| [`horizonforge_project_custom`](horizonforge_project_custom) | Job tracking for small contractors: portal privacy, timesheet payroll, job costing, job templates | In development | LGPL-3 |
| [`horizonforge_job_accounting`](horizonforge_job_accounting) | Job profitability, linking the two modules above (installs itself when both are present) | In development | AGPL-3 |
| [`ozark_timecard`](ozark_timecard) | Printable timecards from Attendances: weekly overtime, pay and paid time off | In production | AGPL-3 |

The school modules work on their own (with or without `nonprofit_accounting`)
and share one version number; see the
[changelog](horizonforge_school_core/CHANGELOG.md).

## Requirements

- Odoo 19 Community, run from source, Python 3.11 or later.
- `horizonforge_accounting` also needs these
  [OCA](https://odoo-community.org) repositories (branch 19.0) on the addons
  path: `server-ux`, `reporting-engine`, `account-financial-tools`,
  `account-financial-reporting`, `mis-builder`, `account-reconcile` and
  `bank-statement-import`. See [its README](horizonforge_accounting/README.md).
- The other modules use core Odoo only.

## Install

```bash
# on the addons path, next to Odoo's own addons
git clone https://github.com/servantmechanic/horizonforge-addons.git
odoo-bin -c odoo.conf -d <database> -i horizonforge_school_core --stop-after-init
```

Each module's README covers its setup and how to run its tests.

## Branches

`main` holds the released modules. New work happens on `feature/...` branches
and is merged into `main` once it has been tried.

## License

The repository is licensed under the [AGPL-3](LICENSE). The school and project
modules are under the LGPL-3 instead, each with its own `LICENSE` file; the
license of every module is also in its `__manifest__.py`.
