from odoo import api, fields, models, tools

BURDEN_PARAM = "horizonforge_job_accounting.labor_burden_pct"


class HfJobProfitLine(models.Model):
    """One row per analytic line of a job, sorted into revenue and costs.

    Invoices (and refunds) are revenue, timesheets are labor at wage cost plus
    the labor burden, vendor bills are bills, and anything else is revenue
    when positive and a cost when negative.
    """

    _name = "hf.job.profit.line"
    _description = "Job Profitability Line"
    _auto = False
    _order = "date desc, id desc"
    _rec_name = "name"

    date = fields.Date(readonly=True)
    name = fields.Char(string="Description", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    project_id = fields.Many2one("project.project", string="Job", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Analytic Account", readonly=True)
    general_account_id = fields.Many2one("account.account", string="Account", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", readonly=True)
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    analytic_line_id = fields.Many2one("account.analytic.line", readonly=True)
    category = fields.Selection(
        [
            ("revenue", "Revenue"),
            ("labor", "Labor"),
            ("bills", "Bills"),
            ("other", "Other Costs"),
        ],
        readonly=True,
    )
    revenue = fields.Monetary(readonly=True)
    cost = fields.Monetary(
        readonly=True,
        help="Labor includes the labor burden from Settings > Project.",
    )
    burden = fields.Monetary(string="Labor Burden", readonly=True)
    profit = fields.Monetary(readonly=True)
    hours = fields.Float(readonly=True)

    @property
    def _table_query(self):
        return f"""
            WITH params AS (
                SELECT COALESCE(NULLIF((
                    SELECT value FROM ir_config_parameter WHERE key = '{BURDEN_PARAM}'
                ), '')::numeric, 0) / 100 AS burden
            ),
            lines AS (
                SELECT aal.id, aal.date, aal.name, aal.company_id, aal.account_id,
                       aal.general_account_id, aal.employee_id, aal.move_line_id,
                       aal.amount, aal.unit_amount,
                       COALESCE(aal.project_id, (
                           SELECT p.id FROM project_project p
                            WHERE p.account_id = aal.account_id
                            ORDER BY p.id LIMIT 1
                       )) AS project_id,
                       CASE
                           WHEN aal.project_id IS NOT NULL AND aal.employee_id IS NOT NULL THEN 'labor'
                           WHEN aal.category = 'invoice' THEN 'revenue'
                           WHEN aal.category = 'vendor_bill' THEN 'bills'
                           WHEN aal.amount > 0 THEN 'revenue'
                           ELSE 'other'
                       END AS category
                  FROM account_analytic_line aal
            )
            SELECT l.id, l.id AS analytic_line_id, l.date, l.name, l.company_id,
                   c.currency_id, l.project_id, p.partner_id,
                   l.account_id AS analytic_account_id, l.general_account_id,
                   l.employee_id, aml.move_id, l.category,
                   CASE WHEN l.category = 'revenue' THEN l.amount ELSE 0 END AS revenue,
                   CASE
                       WHEN l.category = 'labor' THEN -l.amount * (1 + params.burden)
                       WHEN l.category = 'revenue' THEN 0
                       ELSE -l.amount
                   END AS cost,
                   CASE WHEN l.category = 'labor' THEN -l.amount * params.burden ELSE 0 END AS burden,
                   CASE
                       WHEN l.category = 'revenue' THEN l.amount
                       WHEN l.category = 'labor' THEN l.amount * (1 + params.burden)
                       ELSE l.amount
                   END AS profit,
                   CASE WHEN l.category = 'labor' THEN l.unit_amount ELSE 0 END AS hours
              FROM lines l
              JOIN project_project p ON p.id = l.project_id
              JOIN res_company c ON c.id = l.company_id
              LEFT JOIN account_move_line aml ON aml.id = l.move_line_id
             CROSS JOIN params
             WHERE p.is_template IS NOT TRUE
        """

    def action_open_source(self):
        """Open the invoice or bill behind the line, or the timesheet."""
        self.ensure_one()
        if self.move_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": self.move_id.id,
                "view_mode": "form",
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.analytic.line",
            "res_id": self.analytic_line_id.id,
            "view_mode": "form",
        }

    @api.model
    def _hf_totals_by_project(self, projects):
        groups = self._read_group(
            [("project_id", "in", projects.ids)],
            ["project_id"],
            ["revenue:sum", "cost:sum", "hours:sum"],
        )
        return {project.id: (revenue, cost, hours) for project, revenue, cost, hours in groups}
