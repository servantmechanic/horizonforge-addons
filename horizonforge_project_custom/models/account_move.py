from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    hf_project_id = fields.Many2one(
        "project.project",
        string="Job",
        domain=[("is_template", "=", False), ("account_id", "!=", False)],
        check_company=True,
        index="btree_not_null",
        help="Charges this vendor bill to the job: every line gets the job's "
             "analytic account. For a bill split across jobs, leave this empty "
             "and set the analytic distribution on each line.",
    )

    def write(self, vals):
        res = super().write(vals)
        if "hf_project_id" in vals and not vals["hf_project_id"]:
            self.invoice_line_ids.filtered(lambda l: l.display_type == "product").analytic_distribution = False
        return res


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends("move_id.hf_project_id")
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self:
            project = line.move_id.hf_project_id
            if project and line.display_type == "product":
                line.analytic_distribution = project.sudo()._get_analytic_distribution()
