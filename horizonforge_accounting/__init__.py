from . import models
from . import wizard


def _hf_accounting_post_init(env):
    companies = env["res.company"].search([("chart_template", "!=", False), ("parent_id", "=", False)])
    companies._hf_setup_accounting()
