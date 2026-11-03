# HorizonForge Job Accounting

Job profitability for jobs from `horizonforge_project_custom`, on the books set up by
`horizonforge_accounting`. It installs by itself once both are installed (`auto_install`).

## What it shows

| Where | What |
|---|---|
| Project > Reporting > Job Profitability (also Accounting > Reporting > Management) | One row per job: contract, invoiced, to invoice, costs, profit, margin, hours. A row opens its lines |
| Project > Reporting > Job Costs and Revenue | Pivot, graph and list of every line by job, category, month, account, employee or customer. A list row opens the invoice, bill or timesheet |
| Profit button on a job | That job's lines, by category |

Settings > Project > Timesheet Payroll has **Labor Burden (%)**, added to wage cost for
payroll taxes, workers' comp and benefits. It applies at once, to past lines too.

Job Profitability and the lines are visible to accountants (`account.group_account_readonly`)
and project managers, since labor cost shows wages.

## How it works

`hf.job.profit.line` is a SQL view (`_table_query`) over `account.analytic.line`. A line
belongs to a job through its `project_id` (timesheets) or the job's analytic account
(invoices and bills, through `hf_project_id` or the sales order). Templates are left out.

| Category | Lines | Amount |
|---|---|---|
| Revenue | Customer invoices and refunds (`category = 'invoice'`), and other positive lines | Revenue |
| Labor | Timesheets (a project and an employee) | Cost: wage cost × (1 + burden) |
| Bills | Vendor bills and refunds (`category = 'vendor_bill'`) | Cost |
| Other Costs | Other negative lines | Cost |

The burden is read from `ir.config_parameter` `horizonforge_job_accounting.labor_burden_pct`
inside the view, so changing it needs no recompute. Wage cost is the timesheet amount from
`horizonforge_project_custom`, the employee's Wage without the overtime premium.

Contract and To Invoice come from the job's sales order lines (`price_subtotal` and
`untaxed_amount_to_invoice`). Margin is profit over invoiced revenue.

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_hf_job -i horizonforge_job_accounting \
    --test-tags /horizonforge_job_accounting --stop-after-init --http-port 8079
dropdb test_hf_job
```

`tests/test_ui.py` opens both screens in a browser. `tests/test_job_profit.py` runs a T&M job end to end: 10 hours at a $20 wage billed at $40,
a $120 lumber bill, and the invoice. It checks categories, job totals, uninvoiced time,
burden, refunds, opening the source and access.

## Known limits

- Revenue counts only invoices whose lines carry the job's analytic account. T&M and job
  products from `horizonforge_project_custom` do.
- Labor uses base wage; the overtime premium is only in the Payroll report.
- Jobs without a sales order show no contract or to-invoice amount.
