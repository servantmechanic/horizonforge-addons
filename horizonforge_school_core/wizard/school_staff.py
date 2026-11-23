from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.res_users import LEVEL_GROUPS, SCHOOL_LEVELS


class SchoolStaff(models.TransientModel):
    """Add or change a staff member's login, for the principal: a school
    access level and nothing else. Users who manage Odoo itself (access
    rights) are changed in Odoo's Settings, Users, by the system
    administrator."""

    _name = "school.staff"
    _description = "Staff Member"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        readonly=True,
    )
    name = fields.Char(required=True)
    login = fields.Char(
        required=True,
        help="What they sign in with, usually their email address.",
    )
    email = fields.Char()
    level = fields.Selection(
        SCHOOL_LEVELS,
        string="School Access",
        default="teacher",
        required=True,
        help="Teacher: their classes and homeroom. Office: every class, and "
        "students, patrons and enrollments. Principal: everything school, "
        "the school settings and staff.",
    )
    password = fields.Char(
        help="Needed for a new login. Leave empty to keep the current password.",
    )
    active = fields.Boolean(
        string="Can Sign In",
        default=True,
        help="Clear it for someone who left: their login is archived, their "
        "classes, grades and notes stay.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        user = self.env["res.users"].with_context(active_test=False).browse(
            self.env.context.get("school_staff_user_id")
        ).exists()
        if user:
            values.update({
                "user_id": user.id,
                "name": user.name,
                "login": user.login,
                "email": user.email,
                "level": user.school_level or "teacher",
                "active": user.active,
            })
        return values

    @api.model
    def _check_principal(self):
        if not self.env.user.has_group("horizonforge_school_core.group_school_admin"):
            raise AccessError(_("Only the principal adds and changes staff."))

    def _check_target(self):
        """What a principal may not do: change a system administrator, or
        lock themselves out."""
        self.ensure_one()
        user = self.user_id.with_context(active_test=False)
        if not user:
            return
        is_system = self.env.user.has_group("base.group_system")
        if user.school_it_admin and not is_system:
            raise UserError(_(
                "%(name)s manages Odoo itself: change their account in Odoo's "
                "Settings, Users (ask the system administrator).",
                name=user.name,
            ))
        if user == self.env.user and (self.level != "principal" or not self.active):
            raise UserError(_(
                "You can't take away your own principal access: ask another "
                "principal or the system administrator."
            ))

    def _level_commands(self):
        """Group changes for the level: the school groups (and the export
        that comes with Principal) off, the chosen level on."""
        commands = [Command.unlink(self.env.ref(xmlid).id) for xmlid in LEVEL_GROUPS.values()]
        if self.level != "principal":
            commands.append(Command.unlink(self.env.ref("base.group_allow_export").id))
        commands.append(Command.link(self.env.ref(LEVEL_GROUPS[self.level]).id))
        return commands

    def action_apply(self):
        self.ensure_one()
        self._check_principal()
        self._check_target()
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        vals = {
            "name": self.name.strip(),
            "login": self.login.strip(),
            "email": (self.email or "").strip() or False,
        }
        if self.user_id:
            # sudo: a principal may change school staff; _check_target made
            # sure this one is no system administrator.
            user = self.user_id.sudo().with_context(active_test=False)
            user.write(dict(vals, group_ids=self._level_commands()))
            if self.password:
                user.password = self.password
            if user.active != self.active:
                user.active = self.active
            message = _("%(name)s saved.", name=user.name)
        else:
            if not self.password:
                raise UserError(_("Give the new login a password: they can change it after signing in."))
            # sudo: only internal access and a school level are given.
            user = Users.create(dict(
                vals,
                password=self.password,
                company_id=self.env.company.id,
                company_ids=[Command.set(self.env.company.ids)],
                group_ids=[Command.set([self.env.ref("base.group_user").id])] + self._level_commands(),
            ))
            message = _("%(name)s can now sign in as %(login)s.", name=user.name, login=user.login)
        # Don't keep the password in the form's record (as Odoo's own
        # change-password form does).
        self.write({"password": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": message,
                "next": self.env["res.users"].action_school_staff(),
            },
        }
