from . import controllers
from . import models


def _hf_post_init(env):
    """Turn off the periodic KPI digest emails if the digest app is installed."""
    if "digest.digest" in env:
        env["digest.digest"].search([("state", "=", "activated")]).action_deactivate()
        env["ir.config_parameter"].sudo().set_param("digest.default_digest_emails", False)
