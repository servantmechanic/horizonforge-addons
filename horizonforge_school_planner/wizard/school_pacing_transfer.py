import base64
import csv
import io
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.horizonforge_school_gradebook.models.school_assignment import ENTRY_MODES

HEADER = ["Order", "Unit", "Name", "Topic", "Category", "Days", "Max Points", "Entry Mode", "Notes", "Files"]


class SchoolPacingTransfer(models.TransientModel):
    """A course's pacing guide to a file and back: a CSV, or a zip with the
    CSV and the items' files, to share a guide between courses, years or
    schools."""

    _name = "school.pacing.transfer"
    _description = "Export or Import a Pacing Guide"

    course_id = fields.Many2one(
        "school.course",
        string="Course",
        required=True,
        default=lambda self: self.env.context.get("default_course_id"),
    )
    mode = fields.Selection(
        [("export", "Export"), ("import", "Import")],
        default="export",
        required=True,
    )
    data_file = fields.Binary(
        string="File",
        help="A .zip exported from a pacing guide (with its files), or a .csv "
        "with the columns: " + ", ".join(HEADER) + ".",
    )
    file_name = fields.Char()
    replace = fields.Boolean(
        string="Replace the Current Guide",
        help="Remove the course's items first. Otherwise the file's items "
        "come after them.",
    )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def _file_name(self, item, attachment, index):
        return f"{item.sequence:04d}-{index}-{attachment.name}".replace("/", "-")

    def _export_rows(self):
        self.ensure_one()
        mode_labels = dict(ENTRY_MODES)
        rows = []
        for item in self.course_id.pacing_item_ids.sorted(lambda i: (i.sequence, i.id)):
            rows.append([
                item.sequence, item.unit or "", item.name, item.topic or "",
                item.category_id.code or "", item.days, f"{item.max_points:g}" if item.max_points else "",
                mode_labels.get(item.entry_mode, ""), item.note or "",
                "; ".join(self._file_name(item, a, i) for i, a in enumerate(item.attachment_ids, start=1)),
            ])
        return rows

    def _csv_bytes(self, rows):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(HEADER)
        writer.writerows(rows)
        # With a byte order mark, so Excel reads accents correctly.
        return buffer.getvalue().encode("utf-8-sig")

    def action_export(self):
        self.ensure_one()
        if not self.course_id.pacing_item_ids:
            raise UserError(_("%(course)s has no pacing guide yet.", course=self.course_id.name))
        rows = self._export_rows()
        items = self.course_id.pacing_item_ids
        stem = f"{self.course_id.name} pacing guide".replace("/", "-")
        if items.attachment_ids:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("guide.csv", self._csv_bytes(rows))
                for item in items:
                    for index, attachment in enumerate(item.attachment_ids, start=1):
                        archive.writestr(f"files/{self._file_name(item, attachment, index)}", attachment.raw or b"")
            content, name, mimetype = buffer.getvalue(), f"{stem}.zip", "application/zip"
        else:
            content, name, mimetype = self._csv_bytes(rows), f"{stem}.csv", "text/csv"
        attachment = self.env["ir.attachment"].create({
            "name": name,
            "datas": base64.b64encode(content),
            "mimetype": mimetype,
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "download",
        }

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _read_file(self):
        """``(csv text, {file name: bytes})`` from the uploaded file."""
        self.ensure_one()
        if not self.data_file:
            raise UserError(_("Choose the file to import."))
        raw = base64.b64decode(self.data_file)
        files = {}
        if zipfile.is_zipfile(io.BytesIO(raw)):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
                if not names:
                    raise UserError(_("The zip has no .csv file of the guide in it."))
                text = archive.read(names[0]).decode("utf-8-sig")
                for name in archive.namelist():
                    if name.startswith("files/") and not name.endswith("/"):
                        files[name[len("files/"):]] = archive.read(name)
            return text, files
        try:
            return raw.decode("utf-8-sig"), files
        except UnicodeDecodeError as error:
            raise UserError(_("Import a .csv or a .zip exported from a pacing guide.")) from error

    def _parse(self, text, files):
        categories = self.env["school.score.category"].with_context(active_test=False).search([])
        by_key = {}
        for category in categories:
            by_key[(category.code or "").lower()] = category
            by_key[(category.name or "").lower()] = category
        modes = {}
        for key, label in ENTRY_MODES:
            modes[key] = key
            modes[label.lower()] = key
        reader = csv.DictReader(io.StringIO(text))
        missing = {"Name"} - set(reader.fieldnames or [])
        if missing:
            raise UserError(_("The file needs at least a Name column. Its columns can be: %(columns)s.",
                              columns=", ".join(HEADER)))
        vals_list = []
        for number, row in enumerate(reader, start=2):
            name = (row.get("Name") or "").strip()
            if not name:
                continue
            category = False
            if (row.get("Category") or "").strip():
                category = by_key.get(row["Category"].strip().lower())
                if not category:
                    raise UserError(_(
                        "Line %(line)s: no score category %(category)s. Use a category's code or name: %(known)s.",
                        line=number, category=row["Category"].strip(),
                        known=", ".join(categories.mapped("code")),
                    ))
            mode = (row.get("Entry Mode") or "").strip().lower()
            if mode and mode not in modes:
                raise UserError(_("Line %(line)s: %(mode)s isn't an entry mode.", line=number, mode=mode))
            try:
                days = int(row.get("Days") if (row.get("Days") or "").strip() else 1)
                points = float(row.get("Max Points") or 0)
                sequence = int(row.get("Order") or 0)
            except ValueError as error:
                raise UserError(_("Line %(line)s: Order, Days and Max Points take numbers.", line=number)) from error
            attachments = []
            for file_name in filter(None, (f.strip() for f in (row.get("Files") or "").split(";"))):
                if file_name in files:
                    attachments.append({"name": file_name.split("-", 2)[-1], "raw": files[file_name]})
            vals_list.append({
                "sequence": sequence,
                "unit": (row.get("Unit") or "").strip() or False,
                "name": name,
                "topic": (row.get("Topic") or "").strip() or False,
                "category_id": category.id if category else False,
                "days": max(days, 0),
                "max_points": points,
                "entry_mode": modes.get(mode, False),
                "note": (row.get("Notes") or "").strip() or False,
                "_files": attachments,
            })
        if not vals_list:
            raise UserError(_("The file has no items."))
        return vals_list

    def action_import(self):
        self.ensure_one()
        vals_list = self._parse(*self._read_file())
        course = self.course_id
        Item = self.env["school.pacing.item"]
        if self.replace:
            course.pacing_item_ids.unlink()
        start = max(course.pacing_item_ids.mapped("sequence"), default=0)
        # Keep the file's order, after what is there.
        vals_list.sort(key=lambda vals: vals["sequence"])
        created = Item
        for offset, vals in enumerate(vals_list, start=1):
            files = vals.pop("_files")
            vals.update(course_id=course.id, sequence=start + offset * 10)
            item = Item.create(vals)
            if files:
                item.attachment_ids = self.env["ir.attachment"].create([
                    dict(file, res_model=Item._name, res_id=item.id) for file in files
                ])
            created |= item
        course.section_ids.filtered(lambda s: s.year_id.is_current)._replan()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("%(count)s items imported into %(course)s.", count=len(created), course=course.name),
                "next": course.action_open_pacing_guide(),
            },
        }
