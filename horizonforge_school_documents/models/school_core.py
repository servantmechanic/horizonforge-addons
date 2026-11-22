from odoo import api, fields, models


class SchoolYear(models.Model):
    _inherit = "school.year"

    @api.model_create_multi
    def create(self, vals_list):
        years = super().create(vals_list)
        self.env["school.document.folder"]._sync_auto_folders()
        return years

    def write(self, vals):
        res = super().write(vals)
        if "name" in vals:
            self.env["school.document.folder"]._sync_auto_folders()
        return res


class SchoolHomeroom(models.Model):
    _inherit = "school.homeroom"

    @api.model_create_multi
    def create(self, vals_list):
        homerooms = super().create(vals_list)
        self.env["school.document.folder"]._sync_auto_folders()
        return homerooms

    def write(self, vals):
        res = super().write(vals)
        if "name" in vals or vals.get("active"):
            self.env["school.document.folder"]._sync_auto_folders()
        return res


class SchoolStudent(models.Model):
    _inherit = "school.student"

    document_ids = fields.Many2many(
        "ir.attachment",
        "school_student_document_rel",
        "student_id",
        "attachment_id",
        string="Files",
        help="Enrollment forms, records and other files of this student. "
        "Seen by the office and every teacher.",
    )
    document_count = fields.Integer(compute="_compute_document_count")

    @api.depends("document_ids")
    def _compute_document_count(self):
        for student in self:
            student.document_count = len(student.document_ids)

    def _link_documents(self):
        """Tie the uploaded files to the student, so that who may open them
        follows who may see the student."""
        for student in self:
            loose = student.document_ids.sudo().filtered(
                lambda a: a.res_model != self._name or a.res_id != student.id
            )
            loose.write({"res_model": self._name, "res_id": student.id})

    @api.model_create_multi
    def create(self, vals_list):
        students = super().create(vals_list)
        students._link_documents()
        return students

    def write(self, vals):
        res = super().write(vals)
        if "document_ids" in vals:
            self._link_documents()
        return res
