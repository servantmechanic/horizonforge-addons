from odoo import _, api, fields, models


class SchoolSection(models.Model):
    _name = "school.section"
    _description = "Class"
    _order = "year_id desc, course_id, name, id"
    _rec_names_search = ["course_id.name", "course_id.code", "name"]

    course_id = fields.Many2one(
        "school.course",
        string="Course",
        required=True,
        ondelete="restrict",
        index=True,
    )
    year_id = fields.Many2one(
        "school.year",
        string="School Year",
        required=True,
        ondelete="restrict",
        index=True,
        default=lambda self: self.env["school.year"]._get_current(),
    )
    name = fields.Char(
        string="Label",
        help="Only needed to tell apart two classes of the same course in "
        "one year, for example A and B.",
    )
    teacher_id = fields.Many2one(
        "res.users",
        string="Teacher",
        index=True,
        domain=lambda self: self._teacher_domain(),
        help="The teacher who grades this class.",
    )
    co_teacher_ids = fields.Many2many(
        "res.users",
        "school_section_co_teacher_rel",
        "section_id",
        "user_id",
        string="Co-teachers",
        domain=lambda self: self._teacher_domain(),
        help="Other teachers who can also grade this class.",
    )
    homeroom_id = fields.Many2one(
        "school.homeroom",
        string="Homeroom",
        ondelete="restrict",
        index=True,
        help="When set, only this homeroom's students are enrolled by "
        "Enroll Students.",
    )
    enrollment_ids = fields.One2many(
        "school.enrollment",
        "section_id",
        string="Enrollments",
    )
    student_count = fields.Integer(
        string="Students",
        compute="_compute_student_count",
    )
    active = fields.Boolean(default=True)

    @api.model
    def _teacher_domain(self):
        group = self.env.ref(
            "horizonforge_school_core.group_school_teacher", raise_if_not_found=False
        )
        return [("all_group_ids", "in", group.ids)] if group else []

    @api.depends("course_id.name", "name", "year_id.name")
    def _compute_display_name(self):
        for section in self:
            parts = [section.course_id.name or "", section.name or ""]
            label = " ".join(part for part in parts if part)
            if section.year_id:
                label = f"{label} ({section.year_id.name})"
            section.display_name = label

    @api.depends("enrollment_ids")
    def _compute_student_count(self):
        counts = dict(self.env["school.enrollment"]._read_group(
            [("section_id", "in", self.ids)],
            ["section_id"],
            ["student_id:count_distinct"],
        ))
        for section in self:
            section.student_count = counts.get(section, 0)

    def action_enroll_grade_levels(self):
        """Enroll every active student of the course's grade levels (in the
        class's homeroom, when it has one) who isn't in the class yet."""
        to_create = []
        for section in self:
            domain = [
                ("grade_level_id", "in", section.course_id.grade_level_ids.ids),
                ("id", "not in", section.enrollment_ids.student_id.ids),
            ]
            if section.homeroom_id:
                domain.append(("homeroom_id", "=", section.homeroom_id.id))
            students = self.env["school.student"].search(domain)
            to_create += [
                {"section_id": section.id, "student_id": student.id}
                for student in students
            ]
        enrollments = self.env["school.enrollment"].create(to_create)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if enrollments else "info",
                "message": _("%(count)s students enrolled.", count=len(enrollments)),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    # A teacher's classes: those they teach, and those their homeroom's
    # students take (the homeroom teacher keeps their grades too).

    @api.model
    def _my_classes_domain(self, user=None, path=""):
        """Domain on classes (or, with ``path`` such as "section_id.", on
        records of a class) for the classes of ``user``."""
        uid = (user or self.env.user).id
        return [
            "|", "|",
            (path + "teacher_id", "=", uid),
            (path + "co_teacher_ids", "in", uid),
            (path + "enrollment_ids.student_id.homeroom_id.teacher_id", "=", uid),
        ]

    def _is_my_class(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if user in (self.teacher_id | self.co_teacher_ids):
            return True
        # sudo: the homeroom of every student in the class, not only those
        # the user can see.
        return user in self.sudo().enrollment_ids.student_id.homeroom_id.teacher_id

