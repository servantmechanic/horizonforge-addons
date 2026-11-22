from odoo import _, fields, models
from odoo.exceptions import UserError


class SchoolDocumentUpload(models.TransientModel):
    _name = "school.document.upload"
    _description = "Upload Files"

    folder_id = fields.Many2one(
        "school.document.folder",
        string="Folder",
        required=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Files",
        help="Choose one or several files.",
    )

    def action_upload(self):
        self.ensure_one()
        attachments = self.attachment_ids.sudo()
        if not attachments:
            raise UserError(_("Choose at least one file."))
        documents = self.env["school.document"].create([
            {
                "folder_id": self.folder_id.id,
                "filename": attachment.name,
                "datas": attachment.datas,
            }
            for attachment in attachments
        ])
        # The files now live on the documents.
        attachments.unlink()
        action = self.folder_id.action_open_documents()
        if len(documents) == 1:
            # One file: straight to it, to name it or add a note.
            action = {
                "type": "ir.actions.act_window",
                "res_model": "school.document",
                "res_id": documents.id,
                "view_mode": "form",
            }
        return action
