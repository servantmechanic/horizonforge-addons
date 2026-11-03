from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # The owner reconcile models came after the first install.
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env["res.company"].search([("chart_template", "!=", False), ("parent_id", "=", False)])
    for company in companies:
        company.with_company(company)._hf_setup_reconcile_models()
