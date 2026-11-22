from odoo import fields, models


class ProjectTaskType(models.Model):
    _inherit = "project.task.type"

    hf_closes_task = fields.Boolean(
        string="Closes Tasks",
        help="Tasks moved to this stage are marked Done, so the timer no longer offers them.",
    )
