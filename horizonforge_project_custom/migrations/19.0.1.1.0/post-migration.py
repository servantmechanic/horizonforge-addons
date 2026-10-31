from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["project.project"].with_context(active_test=False).search([])._hf_assign_job_codes()
