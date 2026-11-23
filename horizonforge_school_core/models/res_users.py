from odoo import _, api, fields, models
from odoo.exceptions import AccessError

NAME_ORDERS = [
    ("last_first", "Last name, First name"),
    ("first_last", "First name Last name"),
]

SCHOOL_LEVELS = [
    ("teacher", "Teacher"),
    ("office", "Office"),
    ("principal", "Principal"),
]
LEVEL_GROUPS = {
    "teacher": "horizonforge_school_core.group_school_teacher",
    "office": "horizonforge_school_core.group_school_office",
    "principal": "horizonforge_school_core.group_school_admin",
}


class ResUsers(models.Model):
    _inherit = "res.users"

    school_name_order = fields.Selection(
        NAME_ORDERS,
        string="Student Names",
        default="last_first",
        required=True,
        help="How students are shown and sorted in the gradebook and attendance grids.",
    )
    school_level = fields.Selection(
        SCHOOL_LEVELS,
        string="School Access",
        compute="_compute_school_level",
        compute_sudo=True,
    )
    school_it_admin = fields.Boolean(
        string="System Administrator",
        compute="_compute_school_level",
        compute_sudo=True,
        help="Manages Odoo itself (users and access rights): their account is "
        "changed in Odoo's Settings, Users, not under Staff.",
    )

    @api.depends("all_group_ids")
    def _compute_school_level(self):
        it_group = self.env.ref("base.group_erp_manager")
        groups = [(key, self.env.ref(xmlid)) for key, xmlid in LEVEL_GROUPS.items()]
        for user in self:
            level = False
            for key, group in groups:  # the highest wins
                if group in user.all_group_ids:
                    level = key
            user.school_level = level
            user.school_it_admin = it_group in user.all_group_ids

    @api.model_create_multi
    def create(self, vals_list):
        """New users start with the school's default."""
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
            vals.setdefault("school_name_order", company.school_name_order)
        return super().create(vals_list)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["school_name_order"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["school_name_order"]

    # ------------------------------------------------------------------
    # Staff (Configuration, Staff): the principal's list of school logins
    # ------------------------------------------------------------------

    @api.model
    def _check_school_principal(self):
        if not self.env.user.has_group("horizonforge_school_core.group_school_admin"):
            raise AccessError(_("Only the principal manages staff."))

    @api.model
    def action_school_staff(self):
        """Everyone with school access, archived ones under a filter."""
        self._check_school_principal()
        teacher = self.env.ref("horizonforge_school_core.group_school_teacher")
        users = self.sudo().with_context(active_test=False).search([
            ("all_group_ids", "in", teacher.id), ("share", "=", False),
            ("id", "!=", self.env.ref("base.user_root").id),
        ])
        return {
            "type": "ir.actions.act_window",
            "name": _("Staff"),
            "res_model": "res.users",
            "view_mode": "list",
            "views": [(self.env.ref("horizonforge_school_core.school_staff_view_list").id, "list")],
            "search_view_id": [self.env.ref("horizonforge_school_core.school_staff_view_search").id],
            "domain": [("id", "in", users.ids)],
            "target": "current",
        }

    def action_school_staff_add(self):
        """Add Staff, above the list (whatever rows are selected)."""
        self._check_school_principal()
        return self._school_staff_form(_("Add Staff"))

    def action_school_staff_edit(self):
        self.ensure_one()
        self._check_school_principal()
        return self._school_staff_form(self.name, school_staff_user_id=self.id)

    @api.model
    def _school_staff_form(self, title, **context):
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "school.staff",
            "view_mode": "form",
            "target": "new",
            "context": context,
        }
