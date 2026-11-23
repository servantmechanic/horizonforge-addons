from odoo import api, models


class SchoolYear(models.Model):
    _inherit = "school.year"

    @api.model
    def _load_school_planner_demo(self):
        """Pacing guides for the reference school's Math courses (150
        lessons, a test every 10) and Science (Tuesday and Thursday, 60
        lessons, a quiz every 6),
        built from their settings. The gradebook demo's columns of the same
        names count as taught. Does nothing without the reference school or
        when a guide exists.

        By hand: ``env["school.year"]._load_school_planner_demo()``.
        """
        year = self.search([("name", "=", "2026-27")])
        Guide = self.env["school.pacing.guide"]
        if not year or Guide.with_context(active_test=False).search_count([], limit=1):
            return
        guides = Guide
        for course in year.section_ids.course_id.sorted("sequence"):
            subject = course.name.split()[0]
            if subject == "Math":
                vals = {"sequence": 10, "lesson_count": 150, "chapter_size": 10}
            elif subject == "Science":
                vals = {
                    "sequence": 30, "lesson_count": 60, "chapter_size": 6, "test_name": "Quiz",
                    "meets_monday": False, "meets_wednesday": False, "meets_friday": False,
                }
            else:
                continue
            guides |= Guide.create(dict(vals, course_id=course.id, test_after_chapter=True))
        for guide in guides:
            guide.action_build()
