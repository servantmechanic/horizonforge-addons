from odoo import SUPERUSER_ID, api

from odoo.addons.horizonforge_ce_custom import _hf_signup_by_invitation


def migrate(cr, version):
    # Once, for databases installed before 1.2.0: turn off public sign-up.
    _hf_signup_by_invitation(api.Environment(cr, SUPERUSER_ID, {}))
