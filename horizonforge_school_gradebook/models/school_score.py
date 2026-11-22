from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SchoolScore(models.Model):
    _name = "school.score"
    _description = "Score"
    _order = "assignment_id, student_id"

    assignment_id = fields.Many2one(
        "school.assignment",
        string="Assignment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    student_id = fields.Many2one(
        "school.student",
        string="Student",
        required=True,
        ondelete="restrict",
        index=True,
    )
    section_id = fields.Many2one(
        related="assignment_id.section_id",
        store=True,
        index=True,
    )
    period_id = fields.Many2one(
        related="assignment_id.period_id",
        store=True,
        index=True,
    )
    value_entered = fields.Float(
        string="Entered",
        help="What the teacher typed: a percent, points or number wrong, "
        "by the assignment's entry mode.",
    )
    percent = fields.Float(
        compute="_compute_percent",
        store=True,
        help="The score as a percent. Recalculated when the assignment's "
        "max points or entry mode change.",
    )
    status = fields.Selection(
        [
            ("scored", "Scored"),
            ("excused", "Excused"),
            ("missing", "Missing"),
        ],
        default="scored",
        required=True,
    )
    comment = fields.Char()

    _assignment_student_unique = models.Constraint(
        "UNIQUE(assignment_id, student_id)",
        "A student has one score per assignment.",
    )

    @api.depends("value_entered", "status", "assignment_id.max_points", "assignment_id.entry_mode")
    def _compute_percent(self):
        for score in self:
            score.percent = score._to_percent(
                score.value_entered, score.assignment_id.entry_mode, score.assignment_id.max_points
            ) if score.status == "scored" else 0.0

    @api.model
    def _to_percent(self, value, entry_mode, max_points):
        if entry_mode == "percent":
            return value
        if not max_points:
            return 0.0
        if entry_mode == "wrong":
            return (max_points - value) / max_points * 100
        return value / max_points * 100

    @api.constrains("value_entered", "status")
    def _check_value(self):
        for score in self:
            if score.status != "scored":
                continue
            assignment = score.assignment_id
            top = 100.0 if assignment.entry_mode == "percent" else assignment.max_points
            if not 0 <= score.value_entered <= top:
                raise ValidationError(_(
                    "%(value)s is out of range for %(assignment)s: enter 0 to %(top)s.",
                    value=f"{score.value_entered:g}",
                    assignment=assignment.name,
                    top=f"{top:g}",
                ))

    @api.constrains("assignment_id", "student_id")
    def _check_enrolled(self):
        for score in self:
            if score.student_id not in score.section_id.enrollment_ids.student_id:
                raise ValidationError(_(
                    "%(student)s isn't enrolled in %(section)s.",
                    student=score.student_id.display_name,
                    section=score.section_id.display_name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        scores = super().create(vals_list)
        scores.assignment_id._check_unlocked()
        return scores

    def write(self, vals):
        self.assignment_id._check_unlocked()
        return super().write(vals)

    def unlink(self):
        self.assignment_id._check_unlocked()
        return super().unlink()

    def _cell(self):
        self.ensure_one()
        return {
            "assignment_id": self.assignment_id.id,
            "student_id": self.student_id.id,
            "value": self.value_entered if self.status == "scored" else False,
            "status": self.status,
            "comment": self.comment or "",
            "percent": self.percent,
        }

    @api.model
    def save_batch(self, changes):
        """Save gradebook cells. Each change is a dict with ``assignment_id``,
        ``student_id``, ``status`` (scored, excused, missing, or False to
        clear the cell), ``value`` and ``comment``.

        A bad cell doesn't block the others: the result lists the saved
        cells and, separately, the refused ones with the reason.
        """
        assignments = self.env["school.assignment"].browse(
            {change["assignment_id"] for change in changes}
        ).exists()
        existing = {
            (score.assignment_id.id, score.student_id.id): score
            for score in self.search([
                ("assignment_id", "in", assignments.ids),
                ("student_id", "in", list({change["student_id"] for change in changes})),
            ])
        }
        saved, errors = [], []
        for change in changes:
            key = (change["assignment_id"], change["student_id"])
            score = existing.get(key)
            try:
                with self.env.cr.savepoint():
                    if change["assignment_id"] not in assignments.ids:
                        raise UserError(_("This assignment was deleted."))
                    status = change.get("status")
                    if not status:
                        if score:
                            score.unlink()
                            existing.pop(key)
                        saved.append({
                            "assignment_id": key[0], "student_id": key[1], "status": False,
                        })
                        continue
                    vals = {
                        "status": status,
                        "value_entered": change.get("value") or 0.0 if status == "scored" else 0.0,
                        "comment": change.get("comment") or False,
                    }
                    if score:
                        score.write(vals)
                    else:
                        score = existing[key] = self.create({
                            "assignment_id": key[0], "student_id": key[1], **vals,
                        })
                    saved.append(score._cell())
            except (UserError, ValidationError, AccessError) as error:
                errors.append({
                    "assignment_id": key[0],
                    "student_id": key[1],
                    "message": str(error.args[0]) if error.args else str(error),
                })
        # The grid's grade column follows every save.
        grades = [
            {"section_id": section.id, "period_id": period.id, **section._gradebook_grades(period)}
            for section, period in {(a.section_id, a.period_id) for a in assignments.exists()}
        ] if saved else []
        return {"saved": saved, "errors": errors, "grades": grades}
