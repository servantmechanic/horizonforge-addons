from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hf_portal_hide_timesheets = fields.Boolean(
        string="Hide timesheets from the portal",
        config_parameter="horizonforge_project_custom.portal_hide_timesheets",
        help="Portal customers see no Time Spent, hours or timesheet lists "
             "on project and task pages.",
    )
    hf_portal_hide_sales_orders = fields.Boolean(
        string="Hide sales orders from the portal",
        config_parameter="horizonforge_project_custom.portal_hide_sales_orders",
        help="Portal customers see no Sales Orders or Quotations. Links sent "
             "by email keep working, and invoices stay visible.",
    )
    hf_auto_follow_tasks = fields.Boolean(
        string="Auto-follow tasks",
        config_parameter="horizonforge_project_custom.auto_follow_tasks",
        help="A customer who follows a project also follows all its tasks, "
             "old and new. Internal users are skipped.",
    )
    hf_ot_threshold = fields.Float(
        string="Overtime threshold (hrs/week)",
        config_parameter="horizonforge_project_custom.ot_threshold",
        help="Weekly hours above this are paid as overtime.",
    )
    hf_ot_multiplier = fields.Float(
        string="Overtime multiplier",
        config_parameter="horizonforge_project_custom.ot_multiplier",
        help="Overtime hours are paid at the hourly wage times this.",
    )
    hf_week_start = fields.Selection(
        [
            ("6", "Sunday"),
            ("0", "Monday"),
        ],
        string="Week starts on",
        config_parameter="horizonforge_project_custom.week_start",
        help="Weekly overtime is calculated per workweek starting on this day.",
    )

    @api.constrains("hf_ot_threshold", "hf_ot_multiplier")
    def _check_hf_overtime(self):
        for settings in self:
            if settings.hf_ot_threshold <= 0 or settings.hf_ot_multiplier <= 0:
                raise ValidationError(self.env._("The overtime threshold and multiplier must be above zero."))

    def set_values(self):
        hidden_before = self.env.user._hf_portal_toggle("portal_hide_sales_orders")
        super().set_values()
        if hidden_before != self.env.user._hf_portal_toggle("portal_hide_sales_orders"):
            # Record rule domains are cached and depend on this toggle.
            self.env.registry.clear_cache()
