from . import controllers
from . import models
from . import wizard

# Set once at install, not as XML data: Settings deletes a parameter when it is
# unticked, and a deleted data record would come back on the next module update.
DEFAULT_PARAMS = {
    "horizonforge_project_custom.portal_hide_timesheets": "True",
    "horizonforge_project_custom.auto_follow_tasks": "True",
    "horizonforge_project_custom.ot_threshold": "40.0",
    "horizonforge_project_custom.ot_multiplier": "1.5",
    "horizonforge_project_custom.week_start": "6",
}


def _hf_project_post_init(env):
    params = env["ir.config_parameter"].sudo()
    for key, value in DEFAULT_PARAMS.items():
        params.set_param(key, value)
    env["project.project"].with_context(active_test=False).search([])._hf_assign_job_codes()
