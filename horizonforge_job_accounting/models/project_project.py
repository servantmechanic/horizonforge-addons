from odoo import fields, models

PROFIT_GROUPS = "account.group_account_readonly,project.group_project_manager"


class ProjectProject(models.Model):
    _inherit = "project.project"

    hf_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_hf_currency_id",
    )
    hf_contract_amount = fields.Monetary(
        string="Contract",
        currency_field="hf_currency_id",
        compute="_compute_hf_profitability",
        groups=PROFIT_GROUPS,
        help="Untaxed total of the job's sales order.",
    )
    hf_to_invoice = fields.Monetary(
        string="To Invoice",
        currency_field="hf_currency_id",
        compute="_compute_hf_profitability",
        groups=PROFIT_GROUPS,
        help="Delivered on the sales order but not invoiced yet, untaxed.",
    )
    hf_revenue = fields.Monetary(
        string="Invoiced",
        currency_field="hf_currency_id",
        compute="_compute_hf_profitability",
        groups=PROFIT_GROUPS,
    )
    hf_cost = fields.Monetary(
        string="Costs",
        currency_field="hf_currency_id",
        compute="_compute_hf_profitability",
        groups=PROFIT_GROUPS,
        help="Labor (with the labor burden), bills and other costs charged to the job.",
    )
    hf_profit = fields.Monetary(
        string="Profit",
        currency_field="hf_currency_id",
        compute="_compute_hf_profitability",
        groups=PROFIT_GROUPS,
    )
    hf_margin = fields.Float(
        string="Margin",
        compute="_compute_hf_profitability",
        groups=PROFIT_GROUPS,
        help="Profit as a share of invoiced revenue.",
    )
    hf_hours = fields.Float(
        string="Hours",
        compute="_compute_hf_profitability",
        groups=PROFIT_GROUPS,
    )

    def _compute_hf_currency_id(self):
        for project in self:
            project.hf_currency_id = (project.company_id or self.env.company).currency_id

    def _compute_hf_profitability(self):
        totals = self.env["hf.job.profit.line"]._hf_totals_by_project(self)
        for project in self:
            revenue, cost, hours = totals.get(project.id, (0.0, 0.0, 0.0))
            order_lines = project.sudo().sale_order_id.order_line
            project.hf_contract_amount = sum(order_lines.mapped("price_subtotal"))
            project.hf_to_invoice = sum(order_lines.mapped("untaxed_amount_to_invoice"))
            project.hf_revenue = revenue
            project.hf_cost = cost
            project.hf_profit = revenue - cost
            project.hf_margin = (revenue - cost) / revenue if revenue else 0.0
            project.hf_hours = hours

    def action_hf_job_profit_lines(self):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_job_accounting.action_hf_job_profit_line"
        )
        action["domain"] = [("project_id", "in", self.ids)]
        action["context"] = {"pivot_row_groupby": ["category"]}
        if len(self) == 1:
            action["name"] = self.env._("%(job)s: Profitability", job=self.display_name)
        return action
