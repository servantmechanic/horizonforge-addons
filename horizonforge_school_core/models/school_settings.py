from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class SchoolSettings(models.TransientModel):
    """The school's settings, for the principal: the school part of Odoo's
    Settings, without the rest of it (users, apps, email), which stays with
    the system administrator. Saved on the company by ``create``."""

    _name = "school.settings"
    _description = "School Settings"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    school_current_year_id = fields.Many2one(
        "school.year",
        string="Current School Year",
        default=lambda self: self.env["school.year"]._get_current(),
        help="The year new classes are created in and the one teachers see first.",
    )
    school_principal_name = fields.Char(
        related="company_id.school_principal_name",
        readonly=False,
    )
    school_name_order = fields.Selection(
        related="company_id.school_name_order",
        readonly=False,
    )

    @api.model
    def _check_principal(self):
        if not self.env.user.has_group("horizonforge_school_core.group_school_admin"):
            raise AccessError(_("Only the principal changes the school settings."))

    @api.model_create_multi
    def create(self, vals_list):
        """Save the settings: on the company, with the rights for it. Only
        this model's own fields, all of them school settings, are written."""
        self._check_principal()
        settings = super(SchoolSettings, self.sudo()).create(vals_list).sudo(False)
        for record in settings:
            if record.school_current_year_id:
                record.school_current_year_id.is_current = True
        return settings

    def write(self, vals):
        self._check_principal()
        return super(SchoolSettings, self.sudo()).write(vals)

    def action_save(self):
        """The form's Save: the values were saved with the record."""
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "type": "success",
            "message": _("School settings saved."),
            "next": {"type": "ir.actions.client", "tag": "soft_reload"},
        }}
