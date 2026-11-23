from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolScoreCategory(models.Model):
    _name = "school.score.category"
    _description = "Score Category"
    _order = "sequence, id"

    name = fields.Char(
        required=True,
        help="For example Lesson or Test.",
    )
    code = fields.Char(
        required=True,
        help="Short code shown in the gradebook column header, for example L.",
    )
    color = fields.Char(
        default="#4c6ef5",
        help="Color of the code in the gradebook.",
    )
    shortcut = fields.Char(
        size=1,
        help="A key that makes the gradebook column you're on this category, "
        "for example / for lessons and - for tests (as in Candle). Not a "
        "letter or a number: those type scores.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Score category codes must be unique.",
    )
    _shortcut_unique = models.Constraint(
        "UNIQUE(shortcut)",
        "Two score categories can't have the same shortcut key.",
    )

    @api.constrains("shortcut")
    def _check_shortcut(self):
        for category in self:
            key = category.shortcut
            if key and (key.isalnum() or key in ".,? "):
                raise ValidationError(_(
                    "%(key)s can't be a shortcut: letters, numbers, the decimal "
                    "point and ? already do something in the gradebook. Try / - * or +.",
                    key=key,
                ))

    @api.model
    def _rename_default_lesson(self):
        """The shipped Lesson/Homework (HW) is Lesson (L) since 0.8, once:
        a category the school renamed keeps its name."""
        lesson = self.env.ref("horizonforge_school_gradebook.score_category_homework", raise_if_not_found=False)
        if not lesson or (lesson.name, lesson.code) != ("Lesson/Homework", "HW"):
            return
        if self.with_context(active_test=False).search_count([("code", "=", "L")], limit=1):
            return
        lesson.write({"name": "Lesson", "code": "L"})

    @api.model
    def _set_default_shortcuts(self):
        """/ for lessons and - for tests, the first time only: once any
        category has a shortcut, the school's choice stands."""
        if self.with_context(active_test=False).search_count([("shortcut", "!=", False)], limit=1):
            return
        for xmlid, key in (("score_category_homework", "/"), ("score_category_test", "-")):
            category = self.env.ref(f"horizonforge_school_gradebook.{xmlid}", raise_if_not_found=False)
            if category:
                category.shortcut = key
