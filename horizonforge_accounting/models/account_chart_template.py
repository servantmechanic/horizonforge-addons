from odoo import models


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    def _post_load_data(self, template_code, company, template_data):
        res = super()._post_load_data(template_code, company, template_data)
        company = company or self.env.company
        if not company.parent_id:
            company._hf_setup_accounting()
        return res
