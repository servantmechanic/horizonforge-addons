from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SchoolSetupGuide(models.TransientModel):
    """The school's setup as a checklist: each step opens the real screen,
    so everything stays editable through the year. Other school addons add
    their own steps."""

    _name = "school.setup.guide"
    _description = "School Setup Guide"

    year_id = fields.Many2one(
        "school.year",
        string="Current School Year",
        compute="_compute_counts",
    )
    period_count = fields.Integer(compute="_compute_counts")
    day_off_count = fields.Integer(compute="_compute_counts")
    grade_level_count = fields.Integer(compute="_compute_counts")
    homeroom_count = fields.Integer(compute="_compute_counts")
    course_count = fields.Integer(compute="_compute_counts")
    student_count = fields.Integer(compute="_compute_counts")
    section_count = fields.Integer(compute="_compute_counts")

    @api.depends_context("uid")
    def _compute_counts(self):
        year = self.env["school.year"]._get_current()
        for guide in self:
            guide.year_id = year
            guide.period_count = len(year.period_ids)
            guide.day_off_count = len(year.day_off_ids.filtered(lambda d: d.day_type == "off"))
            guide.grade_level_count = self.env["school.grade.level"].search_count([])
            guide.homeroom_count = self.env["school.homeroom"].search_count([])
            guide.course_count = self.env["school.course"].search_count([])
            guide.student_count = self.env["school.student"].search_count([])
            guide.section_count = len(year.section_ids)

    def _compute_display_name(self):
        self.display_name = _("Setup Guide")

    def _open(self, xml_id):
        return self.env["ir.actions.act_window"]._for_xml_id(xml_id)

    def _current_year(self):
        year = self.env["school.year"]._get_current()
        if not year:
            raise UserError(_("Create the school year first (step 1)."))
        return year

    def action_year(self):
        year = self.env["school.year"]._get_current()
        if not year:
            return self._open("horizonforge_school_core.school_year_setup_action")
        return {
            "type": "ir.actions.act_window",
            "res_model": "school.year",
            "res_id": year.id,
            "view_mode": "form",
        }

    def action_calendar(self):
        return self._current_year().action_open_calendar()

    def action_grade_levels(self):
        return self._open("horizonforge_school_core.school_grade_level_action")

    def action_homerooms(self):
        return self._open("horizonforge_school_core.school_homeroom_action")

    def action_courses(self):
        return self._open("horizonforge_school_core.school_course_action")

    def action_students(self):
        return self._open("horizonforge_school_core.school_student_action")

    def action_generate_sections(self):
        return self._current_year().action_generate_sections()

    def action_sections(self):
        return self._open("horizonforge_school_core.school_section_action")
