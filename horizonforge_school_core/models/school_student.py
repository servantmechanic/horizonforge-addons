from odoo import _, api, fields, models


class SchoolStudent(models.Model):
    _name = "school.student"
    _description = "Student"
    _inherits = {"res.partner": "partner_id"}
    _order = "last_name, first_name, id"
    _rec_names_search = ["last_name", "first_name", "student_code"]

    partner_id = fields.Many2one(
        "res.partner",
        string="Related Contact",
        required=True,
        ondelete="restrict",
        index=True,
        help="The student's contact record. It holds the address, phone and "
        "email, so billing and messages can use it later.",
    )
    first_name = fields.Char(required=True)
    last_name = fields.Char(required=True)
    student_code = fields.Char(
        string="Student ID",
        copy=False,
        help="The school's own number or code for the student.",
    )
    grade_level_id = fields.Many2one(
        "school.grade.level",
        string="Grade Level",
        ondelete="restrict",
        index=True,
    )
    homeroom_id = fields.Many2one(
        "school.homeroom",
        string="Homeroom",
        compute="_compute_homeroom_id",
        store=True,
        readonly=False,
        ondelete="set null",
        index=True,
        help="Follows the grade level when only one homeroom has it. Pick "
        "one by hand when a grade level is split over several homerooms.",
    )
    birthdate = fields.Date()
    patron_ids = fields.Many2many(
        "res.partner",
        "school_student_patron_rel",
        "student_id",
        "partner_id",
        string="Patrons",
        domain=[("is_patron", "=", True)],
        help="Parents, guardians or other family contacts.",
    )
    # Own flag, not the contact's: a withdrawn student is archived here while
    # the contact stays available (family records, later billing).
    active = fields.Boolean(
        default=True,
        help="Clear to archive a withdrawn student. Their grades and "
        "attendance are kept.",
    )
    enrollment_ids = fields.One2many(
        "school.enrollment",
        "student_id",
        string="Enrollments",
    )

    _student_code_unique = models.Constraint(
        "UNIQUE(student_code)",
        "Student IDs must be unique.",
    )

    @api.depends("grade_level_id", "grade_level_id.homeroom_ids")
    def _compute_homeroom_id(self):
        for student in self:
            homerooms = student.grade_level_id.homeroom_ids
            if student.homeroom_id in homerooms:
                continue
            student.homeroom_id = homerooms if len(homerooms) == 1 else False

    @api.depends("first_name", "last_name")
    def _compute_display_name(self):
        for student in self:
            student.display_name = ", ".join(
                part for part in (student.last_name, student.first_name) if part
            )

    @api.model
    def _full_name(self, first_name, last_name):
        return " ".join(part.strip() for part in (first_name, last_name) if part)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # The contact's name is required and always follows the student's.
            if not vals.get("partner_id") or vals.get("first_name") or vals.get("last_name"):
                vals["name"] = self._full_name(vals.get("first_name"), vals.get("last_name"))
            if not vals.get("student_code"):
                vals["student_code"] = False
        students = super().create(vals_list)
        students.patron_ids.filtered(lambda p: not p.is_patron).is_patron = True
        return students

    def write(self, vals):
        if "student_code" in vals and not vals["student_code"]:
            vals["student_code"] = False
        res = super().write(vals)
        if "first_name" in vals or "last_name" in vals:
            for student in self:
                student.partner_id.name = self._full_name(
                    student.first_name, student.last_name
                )
        if "patron_ids" in vals:
            self.patron_ids.filtered(lambda p: not p.is_patron).is_patron = True
        return res

    def _grid_rows(self):
        """These students as the grids list them: named and sorted by the
        user's choice, last name first or first name first."""
        first_last = self.env.user.school_name_order == "first_last"

        def key(student):
            names = ((student.first_name or "").lower(), (student.last_name or "").lower())
            return (names if first_last else names[::-1]) + (student.id,)

        return [
            {
                "id": student.id,
                "name": f"{student.first_name} {student.last_name}" if first_last else student.display_name,
            }
            for student in self.sorted(key)
        ]

    @api.model
    def grid_set_name_order(self, order):
        self.env.user.school_name_order = order
        return True

    def _school_attendance_totals(self, date_from, date_to):
        """Attendance of these students between two dates, for reports:
        ``{student_id: {"school_days", "present", "absent", "excused",
        "unexcused", "tardy"}}``. Empty here: the attendance addon fills it."""
        return {}

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for vals in vals_list:
            # A copy is a new person: it gets its own contact.
            vals.pop("partner_id", None)
        return vals_list

    @api.model
    def get_import_templates(self):
        return [{
            "label": _("Import Template for Students"),
            "template": "/horizonforge_school_core/static/csv/students_import_template.csv",
        }]
