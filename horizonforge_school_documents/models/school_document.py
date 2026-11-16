import mimetypes

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Font Awesome icon per kind of file.
ICONS = {
    "pdf": "fa-file-pdf-o",
    "image": "fa-file-image-o",
    "word": "fa-file-word-o",
    "sheet": "fa-file-excel-o",
    "slides": "fa-file-powerpoint-o",
    "text": "fa-file-text-o",
    "archive": "fa-file-archive-o",
    "audio": "fa-file-audio-o",
    "video": "fa-file-video-o",
    "other": "fa-file-o",
}
EXTENSIONS = {
    "word": {"doc", "docx", "odt", "rtf"},
    "sheet": {"xls", "xlsx", "ods", "csv"},
    "slides": {"ppt", "pptx", "odp"},
    "archive": {"zip", "7z", "gz", "tar", "rar"},
    "text": {"txt", "md"},
}


class SchoolDocument(models.Model):
    _name = "school.document"
    _description = "Document"
    _order = "name, id"

    name = fields.Char(
        compute="_compute_name",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        help="Shown in the folder. Defaults to the file's name.",
    )
    folder_id = fields.Many2one(
        "school.document.folder",
        string="Folder",
        required=True,
        ondelete="restrict",
        index=True,
    )
    datas = fields.Binary(
        string="File",
        attachment=True,
        required=True,
    )
    filename = fields.Char(string="File Name")
    file_type = fields.Selection(
        [(key, key.capitalize()) for key in ICONS],
        compute="_compute_file_type",
        store=True,
    )
    icon = fields.Char(compute="_compute_file_type", store=True)
    file_size = fields.Integer(
        string="Size (Bytes)",
        compute="_compute_file_size",
        store=True,
    )
    size_label = fields.Char(string="Size", compute="_compute_size_label")
    note = fields.Text(string="Notes")
    active = fields.Boolean(
        default=True,
        help="Cleared when the file is in the trash.",
    )
    scope = fields.Selection(related="folder_id.scope", store=True)
    year_id = fields.Many2one(related="folder_id.year_id", store=True)
    homeroom_id = fields.Many2one(related="folder_id.homeroom_id", store=True)

    @api.depends("filename")
    def _compute_name(self):
        for document in self:
            if not document.name and document.filename:
                document.name = document.filename.rsplit(".", 1)[0]

    @api.depends("filename")
    def _compute_file_type(self):
        for document in self:
            filename = (document.filename or "").lower()
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            mimetype = mimetypes.guess_type(filename)[0] or ""
            kind = "other"
            if extension == "pdf":
                kind = "pdf"
            elif mimetype.startswith(("image/", "audio/", "video/")):
                kind = mimetype.split("/")[0]
            else:
                kind = next((k for k, extensions in EXTENSIONS.items() if extension in extensions), "other")
            document.file_type = kind
            document.icon = ICONS[kind]

    @api.depends("datas")
    def _compute_file_size(self):
        for document in self.with_context(bin_size=False):
            # Base64: four characters for every three bytes.
            document.file_size = len(document.datas or b"") * 3 // 4

    @api.depends("file_size")
    def _compute_size_label(self):
        for document in self:
            size = float(document.file_size)
            for unit in ("B", "KB", "MB", "GB"):
                if size < 1024 or unit == "GB":
                    document.size_label = f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
                    break
                size /= 1024

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        """The folder tree on the left shows each folder's own name, not
        its whole path."""
        result = super().search_panel_select_range(field_name, **kwargs)
        if field_name == "folder_id" and result.get("values"):
            names = dict(
                self.env["school.document.folder"]
                .browse([value["id"] for value in result["values"]])
                .mapped(lambda folder: (folder.id, folder.name))
            )
            for value in result["values"]:
                value["display_name"] = names.get(value["id"], value["display_name"])
        return result

    def action_download(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/school.document/{self.id}/datas?download=true"
                   f"&filename_field=filename",
            "target": "download",
        }

    # Deleting is two steps on purpose: the trash first (anyone who may
    # change the file, and it can be restored), then for good (office only).

    def action_trash(self):
        self.action_archive()

    def action_restore(self):
        self.action_unarchive()

    def action_delete_forever(self):
        if any(document.active for document in self):
            raise UserError(_("Move the file to the trash first."))
        self.unlink()
        return self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_school_documents.school_document_trash_action"
        )
