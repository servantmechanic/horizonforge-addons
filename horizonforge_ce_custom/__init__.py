from . import controllers
from . import models


def _hf_signup_by_invitation(env):
    """Accounts on invitation only: no "Don't have an account?" on the login
    page. auth_signup turns free sign-up on when it installs."""
    env["ir.config_parameter"].sudo().set_param("auth_signup.invitation_scope", "b2b")


def _hf_post_init(env):
    """Turn off the periodic KPI digest emails if the digest app is
    installed, and public sign-up."""
    _hf_signup_by_invitation(env)
    if "digest.digest" in env:
        env["digest.digest"].search([("state", "=", "activated")]).action_deactivate()
        env["ir.config_parameter"].sudo().set_param("digest.default_digest_emails", False)
