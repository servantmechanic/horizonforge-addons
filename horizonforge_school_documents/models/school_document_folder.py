from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SchoolDocumentFolder(models.Model):
    _name = "school.document.folder"
    _description = "Document Folder"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "complete_name"
    _rec_name = "complete_name"

    name = fields.Char(required=True)
    complete_name = fields.Char(
        string="Folder",
        compute="_compute_complete_name",
        store=True,
        recursive=True,
    )
    parent_id = fields.Many2one(
        "school.document.folder",
        string="Inside",
        ondelete="restrict",
        index=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        "school.document.folder",
        "parent_id",
        string="Folders",
    )
    # Who sees a folder follows its top folder: everyone for the school's
    # reference and a year's folders, the homeroom's teacher (and the
    # office) for a homeroom's.
    scope = fields.Selection(
        [
            ("school", "Schoolwide"),
            ("year", "School year"),
            ("homeroom", "Homeroom"),
        ],
        string="For",
        compute="_compute_scope",
        store=True,
        readonly=False,
        required=True,
        recursive=True,
        precompute=True,
    )
    year_id = fields.Many2one(
        "school.year",
        string="School Year",
        compute="_compute_scope",
        store=True,
        readonly=False,
        recursive=True,
        precompute=True,
        ondelete="restrict",
        index=True,
    )
    homeroom_id = fields.Many2one(
        "school.homeroom",
        string="Homeroom",
        compute="_compute_scope",
        store=True,
        readonly=False,
        recursive=True,
        precompute=True,
        ondelete="restrict",
        index=True,
    )
    is_auto = fields.Boolean(
        string="Created Automatically",
        readonly=True,
        copy=False,
        help="The folder of a school year or of a homeroom in a year. It "
        "follows their names.",
    )
    document_ids = fields.One2many(
        "school.document",
        "folder_id",
        string="Files",
    )
    document_count = fields.Integer(
        string="Files Count",
        compute="_compute_document_count",
    )
    note = fields.Char(
        string="About",
        help="What belongs in this folder.",
    )

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for folder in self:
            if folder.parent_id:
                folder.complete_name = f"{folder.parent_id.complete_name} / {folder.name}"
            else:
                folder.complete_name = folder.name

    @api.depends("parent_id.scope", "parent_id.year_id", "parent_id.homeroom_id")
    def _compute_scope(self):
        for folder in self:
            parent = folder.parent_id
            if parent and not folder.is_auto:
                folder.scope = parent.scope
                folder.year_id = parent.year_id
                folder.homeroom_id = parent.homeroom_id
            else:
                # A top folder, or a year's or homeroom's own: as set.
                folder.scope = folder.scope or "school"
                folder.year_id = folder.year_id
                folder.homeroom_id = folder.homeroom_id

    def _compute_document_count(self):
        Document = self.env["school.document"]
        for folder in self:
            # Files of the folder and of everything inside it.
            folder.document_count = Document.search_count(
                [("folder_id", "child_of", folder.ids)]
            ) if folder.ids else 0

    @api.constrains("parent_id")
    def _check_no_loop(self):
        if self._has_cycle():
            raise ValidationError(_("A folder can't be inside itself."))

    @api.ondelete(at_uninstall=False)
    def _unlink_only_empty(self):
        Document = self.env["school.document"].with_context(active_test=False).sudo()
        for folder in self:
            if folder.child_ids or Document.search_count([("folder_id", "=", folder.id)], limit=1):
                raise UserError(_(
                    "%(folder)s isn't empty. Move or delete its files and folders first "
                    "(files in the trash count too).",
                    folder=folder.complete_name,
                ))

    # ------------------------------------------------------------------
    # Folders of the school years and homerooms
    # ------------------------------------------------------------------

    @api.model
    def _sync_auto_folders(self):
        """Make sure every school year has its folder, with a folder per
        homeroom inside, and that their names follow the records."""
        Folder = self.sudo()
        homerooms = self.env["school.homeroom"].sudo().search([])
        for year in self.env["school.year"].sudo().search([]):
            year_folder = Folder.search(
                [("is_auto", "=", True), ("scope", "=", "year"), ("year_id", "=", year.id)], limit=1
            )
            if not year_folder:
                year_folder = Folder.create({
                    "name": year.name, "scope": "year", "year_id": year.id, "is_auto": True,
                    "note": _("Shared with every teacher for this school year."),
                })
            elif year_folder.name != year.name:
                year_folder.name = year.name
            existing = {
                folder.homeroom_id: folder
                for folder in Folder.search([
                    ("is_auto", "=", True), ("scope", "=", "homeroom"), ("year_id", "=", year.id),
                ])
            }
            for homeroom in homerooms:
                folder = existing.get(homeroom)
                if not folder:
                    Folder.create({
                        "name": homeroom.name, "parent_id": year_folder.id, "scope": "homeroom",
                        "year_id": year.id, "homeroom_id": homeroom.id, "is_auto": True,
                        "note": _("Only this homeroom's teacher and the office see it."),
                    })
                elif folder.name != homeroom.name:
                    folder.name = homeroom.name

    def action_open_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_school_documents.school_document_action"
        )
        action["domain"] = [("folder_id", "child_of", self.id)]
        action["context"] = {"default_folder_id": self.id}
        action["display_name"] = self.complete_name
        return action

    def action_upload(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_school_documents.school_document_upload_action"
        )
        action["context"] = {"default_folder_id": self.id}
        return action
