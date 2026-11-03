from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # The QuickBooks check layout came after the first install.
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env["res.company"].search([("chart_template", "!=", False), ("parent_id", "=", False)])
    for company in companies:
        company._hf_setup_check_layout()
