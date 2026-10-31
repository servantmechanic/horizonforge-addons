# HorizonForge Project Customizations

Job tracking for small contractors on Odoo 19 Community. `horizonforge_project_custom`
adds what core lacks for running jobs: customer portal privacy, automatic task following,
weekly payroll from timesheets, job costing, and ready-made job types. It inherits core
models and views only and does not need Enterprise or any OCA module.

| Feature | What it does |
|---|---|
| Portal privacy | Hides hours and, optionally, sales orders from portal customers, at the data layer as well as on the page |
| Auto-follow | A customer who follows a project follows all its tasks, old and new, except tasks marked Hide from Customers |
| Payroll report | Weekly hours, regular and overtime pay, from project timesheets, as PDF, XLSX or an on-screen job cost list |
| Job costing | Job codes, labor cost from the employee's wage, and a Job field on vendor bills |
| Job setup | Three service products, each linked to a project template with standard stages |

Office staff should use the user guide, which covers daily use. This README is for whoever
installs and maintains the module.

## Requirements

- Odoo 19 Community, run from source
- Python package `xlsxwriter`, already in Odoo's `requirements.txt`
- Odoo modules: `project`, `hr_timesheet`, `sale_project`, `sale_timesheet`, `portal`, `account`.
  Installing this module installs them, which adds Sales, Project, Timesheets and Invoicing to the database.

Developed and tested on Python 3.11. The Debian 13 target runs Python 3.13, so run the tests there first.

## Install and upgrade

Run from `~/odoo-dev`, with the server stopped:

```bash
# First install
venv/bin/python odoo/odoo-bin -c odoo.conf -d <database> -i horizonforge_project_custom --stop-after-init

# Upgrade after changes to fields, views or data
venv/bin/python odoo/odoo-bin -c odoo.conf -d <database> -u horizonforge_project_custom --stop-after-init
```

`-i` does nothing on a database that already has the module. A plain restart is enough for
Python-only changes. If the new code runs before the upgrade, Odoo fails with
`column project_project.hf_job_code does not exist` or similar; stop the server and run the upgrade.

### After installing

1. Enter each employee's hourly pay in Wage, on the employee's Payroll tab.
2. Set the Sales Price of the Time and Materials Job product to the hourly labor rate.
3. Review Settings > Project, under Customer Portal and Timesheet Payroll.

The module turns on analytic accounting for internal users on every install and update. Leave
the Analytic Accounting setting alone on Community: ticking it also flags the Enterprise
`account_accountant` app.

## Configuration

All settings are in Settings > Project. They are stored as `ir.config_parameter` keys prefixed
`horizonforge_project_custom.`.

| Key | Default | Effect |
|---|---|---|
| `portal_hide_timesheets` | True | Hides hours and timesheets from the portal |
| `portal_hide_sales_orders` | False | Hides sales orders and quotations from the portal |
| `auto_follow_tasks` | True | Customers follow a project's tasks |
| `ot_threshold` | 40.0 | Weekly hours before overtime |
| `ot_multiplier` | 1.5 | Overtime pay multiplier |
| `week_start` | 6 | Workweek start: 6 is Sunday, 0 is Monday |

`portal_hide_sales_orders` is off by default because the client brief makes it optional.

Job numbers come from the `horizonforge_project_custom.job_code` sequence, formatted `J-00001`.
Change the prefix or padding under Settings > Technical > Sequences in developer mode.

## How it works

### Portal privacy

Template changes alone would leave the data reachable over RPC, so each toggle works at several levels.

| Level | Timesheets | Sales orders |
|---|---|---|
| Pages | `_show_portal_timesheets()` returns False | Home counters return 0 |
| Routes | `/my/timesheets` and the task PDF redirect to `/my` | `/my/orders` and `/my/quotes` redirect to `/my` |
| Fields | `project.task._has_field_access()` blocks them | Same override |
| Records | Portal users have no access to the lines | Global `ir.rule` on orders and lines |
| Project sharing views | Stripped in `_get_view()` | Stripped in `_get_view()` |

- Core builds views as superuser, so blocked fields stay in the arch and crash the web client.
  `_get_view()` removes them, and `_get_view_cache_key()` includes both toggles.
- Links with an access token read the order as superuser, so emailed quotes keep working
  while the record rule blocks everything else.
- Record rule domains are cached, so `set_values()` clears the cache when the sales order toggle changes.
- Internal users are not restricted by the field or record checks.

### Auto-follow

- `project.project._message_subscribe()` and `project.task.create()` subscribe customers.
  Customers are partners with `partner_share` set; internal users are skipped.
- Subscribing runs in a `hf_auto_follow` context, which sets `mail.followers.hf_auto_followed`.
  That flag is how unfollowing removes only module-added follows and keeps hand-added ones.
- Core's `message_unsubscribe()` removes partners from every open task, so the override
  excludes customers from that step and deletes flagged rows itself.
- Project subtypes differ from task subtypes, so they are mapped through `parent_id`, as core does.
- `_add_followers()` runs with `hf_skip_hidden_tasks`, because core also subscribes a task's
  customer when sharing, which would bypass Hide from Customers.

### Payroll and job cost

The wizard `hf.timesheet.payroll.wizard` reads `account.analytic.line` records that have a
project and an employee. Periods expand to complete workweeks so overtime is never undercounted.
Overtime rules follow `ozark_timecard`.

Job cost shares each week's overtime premium across that week's hours, at a blended rate, so
job costs add up to payroll. `hf.job.cost.line` is a transient model that holds the on-screen list.

The wizard and job cost lines require `hr_timesheet.group_timesheet_manager`. Wages are read
with `sudo()` because `wage` is limited to `hr.group_hr_manager`.

### Job costing

- `sale.order._prepare_analytic_account_data()` no longer copies the customer reference into
  the analytic code. `project.project._hf_assign_job_codes()` numbers any non-template,
  non-internal project whose analytic account has no code. Existing codes are kept.
- `project.project.hf_job_code` is a stored, writable related field on `account_id.code`.
- `account.analytic.line._hourly_cost()` returns the wage, falling back to `hourly_cost`.
  Billing never reads this: T&M invoices use the sales order line price.
- `account.move.hf_project_id` drives `account.move.line._compute_analytic_distribution()`.

### Job setup

`data/project_defaults.xml` ships five stages, three project templates, three service products
and the job sequence, all `noupdate`. Edits made in the UI survive upgrades. The Done stage sets
`hf_closes_task`, because core stages have no closed state: moving a task there sets it to `1_done`.

| Product | Service policy | Template |
|---|---|---|
| Bid Job | `ordered_prepaid` | Bid Job |
| Progress Billing Job | `delivered_manual` | Progress Billing Job |
| Time and Materials Job | `delivered_timesheet` | Time and Materials Job |

### Two details that bite

- **True-default toggles are set in `post_init_hook`, not XML.** Settings deletes a parameter
  when it is unticked, and a deleted `noupdate` record is recreated on the next update, which would turn the toggle back on.
- **Analytic accounting is enabled by a `<function>`, not a record.** `base.group_user` is
  `noupdate`, so an XML record applies on install but not on update.

## Tests

Never run tests against a real database. With a server on 8069, use another port:

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_hf_project -i horizonforge_project_custom \
    --test-tags /horizonforge_project_custom --stop-after-init --http-port 8079
dropdb test_hf_project
```

| File | Covers |
|---|---|
| `tests/test_portal_privacy.py` | Pages, routes, fields, RPC, tokens, and project sharing in a real browser |
| `tests/test_auto_follow.py` | Follow, unfollow, hidden tasks, moved tasks, back-fill |
| `tests/test_payroll.py` | Overtime, weeks, grouping, job cost, exports, access |
| `tests/test_job_costing.py` | Job codes, search, vendor bills, analytic accounting |
| `tests/test_job_setup.py` | The three job types, invoicing, wage cost versus billing |

Browser tests need Chrome and `websocket-client` in the venv; without them they are skipped.

## Known limits

- Hide from Customers cannot hide a task from a customer with full Edit access; core lets them read every task.
- The back-fill re-adds a customer who unfollowed a single task by hand.
- Payroll uses the current wage, so reprinting an old week after a raise shows the new rate.
- Timesheet analytic cost uses base wage. Only the Payroll report includes the overtime premium.
- Selling materials posts no cost. Material cost reaches a job through vendor bills.
- The tokenized order page keeps its Sales Orders breadcrumb, which redirects to `/my` when hidden.
- Not tested with the OCA timer module `hr_timesheet_time_control`, or on Python 3.13.
- Service products link their template per company, so a second company must set it again.
