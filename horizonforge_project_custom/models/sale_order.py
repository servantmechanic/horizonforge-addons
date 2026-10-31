from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    hf_job_code = fields.Char(
        string="Job Code",
        related="project_id.hf_job_code",
    )

    def _prepare_analytic_account_data(self, prefix=None):
        # Core copies the customer's reference into the analytic code; leave it
        # empty so the project gives the job its number.
        return dict(super()._prepare_analytic_account_data(prefix), code=False)
