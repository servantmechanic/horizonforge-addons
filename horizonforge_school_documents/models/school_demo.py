import base64

from odoo import api, models


def _pdf(title, lines):
    """A small one-page PDF, without any library."""
    text = [f"BT /F1 18 Tf 72 720 Td ({title}) Tj ET"]
    for index, line in enumerate(lines):
        text.append(f"BT /F1 11 Tf 72 {690 - index * 18} Td ({line}) Tj ET")
    stream = "\n".join(text).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


class SchoolYear(models.Model):
    _inherit = "school.year"

    @api.model
    def _load_school_documents_demo(self):
        """A few sample files in the reference, year and homeroom folders.
        Does nothing when files already exist.

        By hand: ``env["school.year"]._load_school_documents_demo()``.
        """
        Document = self.env["school.document"]
        if Document.with_context(active_test=False).search_count([], limit=1):
            return
        Folder = self.env["school.document.folder"]
        Folder._sync_auto_folders()
        ref = self.env.ref
        samples = [
            (ref("horizonforge_school_documents.folder_handbooks"), "Parent Handbook.pdf",
             _pdf("Parent Handbook", ["School hours, dress and attendance.", "A sample file for the demo."])),
            (ref("horizonforge_school_documents.folder_handbooks"), "Staff Policies.pdf",
             _pdf("Staff Policies", ["Grading, supervision and reporting.", "A sample file for the demo."])),
            (ref("horizonforge_school_documents.folder_forms"), "Enrollment Form.pdf",
             _pdf("Enrollment Form", ["Student: ____________________", "Patron: _____________________"])),
            (ref("horizonforge_school_documents.folder_forms"), "Field Trip Permission.pdf",
             _pdf("Field Trip Permission", ["I give permission for my child to attend.", "Signed: _______________"])),
            (ref("horizonforge_school_documents.folder_curriculum"), "Book List.csv",
             b"Grade,Subject,Book\n1,Math,Arithmetic 1\n1,English,Reading 1\n2,Math,Arithmetic 2\n"),
        ]
        year = self.search([("name", "=", "2026-27")])
        year_folder = Folder.search([("is_auto", "=", True), ("scope", "=", "year"), ("year_id", "=", year.id)], limit=1)
        if year_folder:
            samples.append((year_folder, "School Calendar 2026-27.pdf",
                            _pdf("School Calendar 2026-27", ["First day: August 24", "Last day: May 21"])))
            samples.append((year_folder, "Staff Meeting Notes.txt",
                            b"August staff meeting\n\n- Schedules handed out\n- Report cards go home after each period\n"))
            for folder in year_folder.child_ids[:5]:
                samples.append((folder, "Class Schedule.pdf",
                                _pdf(f"Class Schedule: {folder.name}", ["8:30 Math", "9:30 English", "10:45 Science"])))
                samples.append((folder, "Seating Chart.txt", b"Row 1: ...\nRow 2: ...\n"))
        Document.create([
            {"folder_id": folder.id, "filename": filename, "datas": base64.b64encode(content)}
            for folder, filename, content in samples
        ])
