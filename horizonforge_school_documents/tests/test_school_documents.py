import base64

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.horizonforge_school_core.tests.common import SchoolCoreCase

PDF = base64.b64encode(b"%PDF-1.4 sample")


@tagged("post_install", "-at_install")
class TestSchoolDocuments(SchoolCoreCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Folder = cls.env["school.document.folder"]
        cls.Document = cls.env["school.document"]
        cls.homeroom = cls.env["school.homeroom"].create({
            "name": "Test Lower Room",
            "teacher_id": cls.teacher.id,
            "grade_level_ids": [Command.set(cls.level_5.ids)],
        })
        cls.other_homeroom = cls.env["school.homeroom"].create({
            "name": "Test Upper Room",
            "teacher_id": cls.other_teacher.id,
            "grade_level_ids": [Command.set(cls.level_6.ids)],
        })
        cls.reference = cls.env.ref("horizonforge_school_documents.folder_reference")
        cls.forms = cls.env.ref("horizonforge_school_documents.folder_forms")
        cls.year_folder = cls.Folder.search([
            ("is_auto", "=", True), ("scope", "=", "year"), ("year_id", "=", cls.year.id),
        ])
        cls.room_folder = cls.year_folder.child_ids.filtered(lambda f: f.homeroom_id == cls.homeroom)
        cls.other_room_folder = cls.year_folder.child_ids.filtered(
            lambda f: f.homeroom_id == cls.other_homeroom
        )

    def _document(self, folder, user=None, filename="Handbook.pdf", **vals):
        return self.Document.with_user(user or self.teacher).create({
            "folder_id": folder.id, "filename": filename, "datas": PDF, **vals,
        })

    # Folders

    def test_auto_folders(self):
        self.assertEqual(len(self.year_folder), 1)
        self.assertEqual(self.year_folder.name, "Test 2030-31")
        self.assertEqual(len(self.room_folder), 1)
        self.assertEqual(
            (self.room_folder.scope, self.room_folder.year_id, self.room_folder.complete_name),
            ("homeroom", self.year, "Test 2030-31 / Test Lower Room"),
        )
        # They follow the names, and a new year gets its own set.
        self.homeroom.name = "Test Primary Room"
        self.year.name = "Test Year"
        self.assertEqual(self.room_folder.complete_name, "Test Year / Test Primary Room")
        new_year = self.env["school.year"].create({
            "name": "Test 2031-32", "date_start": "2031-08-25", "date_end": "2032-05-21",
        })
        new_folder = self.Folder.search([("scope", "=", "year"), ("year_id", "=", new_year.id)])
        self.assertEqual(len(new_folder), 1)
        self.assertIn(self.homeroom, new_folder.child_ids.homeroom_id)
        # Running the sync again creates nothing.
        count = self.Folder.search_count([])
        self.Folder._sync_auto_folders()
        self.assertEqual(self.Folder.search_count([]), count)

    def test_subfolders_inherit_who_sees_them(self):
        trips = self.Folder.with_user(self.teacher).create({"name": "Field Trips", "parent_id": self.room_folder.id})
        self.assertEqual((trips.scope, trips.year_id, trips.homeroom_id), ("homeroom", self.year, self.homeroom))
        shared = self.Folder.with_user(self.teacher).create({"name": "Songs", "parent_id": self.reference.id})
        self.assertEqual((shared.scope, shared.homeroom_id), ("school", self.env["school.homeroom"]))
        with self.assertRaises(AccessError):
            self.Folder.with_user(self.teacher).create({"name": "Sneaky", "parent_id": self.other_room_folder.id})

    def test_folder_delete_only_empty(self):
        folder = self.Folder.create({"name": "Old", "parent_id": self.reference.id})
        document = self._document(folder)
        with self.assertRaises(AccessError):
            folder.with_user(self.teacher).unlink()
        with self.assertRaises(UserError):
            folder.with_user(self.office).unlink()
        document.action_trash()
        with self.assertRaises(UserError):  # the trash counts
            folder.with_user(self.office).unlink()
        document.with_user(self.office).action_delete_forever()
        folder.with_user(self.office).unlink()

    # Files

    def test_document_fields(self):
        document = self._document(self.forms, filename="Enrollment Form.pdf")
        self.assertEqual(document.name, "Enrollment Form")
        self.assertEqual((document.file_type, document.icon), ("pdf", "fa-file-pdf-o"))
        self.assertEqual(document.file_size, len(b"%PDF-1.4 sample"))
        self.assertEqual(document.size_label, "15 B")
        self.assertEqual(document.scope, "school")
        for filename, kind in [("a.docx", "word"), ("b.XLSX", "sheet"), ("c.png", "image"),
                               ("d.txt", "text"), ("e.zip", "archive"), ("f", "other")]:
            self.assertEqual(self._document(self.forms, filename=filename).file_type, kind, filename)
        self.assertIn(f"/web/content/school.document/{document.id}/datas", document.action_download()["url"])
        self.assertEqual(self.forms.document_count, 7)
        self.assertEqual(self.reference.document_count, 7)  # counts what is inside too

    def test_everyone_shares_schoolwide_and_year_folders(self):
        handbook = self._document(self.forms)
        calendar = self._document(self.year_folder, filename="Calendar.pdf")
        Other = self.Document.with_user(self.other_teacher)
        self.assertEqual(Other.search([("id", "in", (handbook | calendar).ids)]), handbook | calendar)
        # Another teacher may change and add, as well.
        handbook.with_user(self.other_teacher).note = "Updated for this year"
        self._document(self.forms, user=self.other_teacher, filename="Second.pdf")

    def test_homeroom_folder_is_private(self):
        mine = self._document(self.room_folder, filename="Seating.pdf")
        self.assertEqual(mine.homeroom_id, self.homeroom)
        Other = self.Document.with_user(self.other_teacher)
        self.assertFalse(Other.search([("id", "=", mine.id)]))
        with self.assertRaises(AccessError):
            mine.with_user(self.other_teacher).read(["name"])
        with self.assertRaises(AccessError):
            self._document(self.room_folder, user=self.other_teacher)
        self.assertNotIn(self.room_folder, self.Folder.with_user(self.other_teacher).search([]))
        # The office sees every homeroom's folder.
        self.assertEqual(self.Document.with_user(self.office).search([("id", "=", mine.id)]), mine)
        # Moving a file into a shared folder shares it.
        mine.folder_id = self.forms
        self.assertEqual(Other.search([("id", "=", mine.id)]), mine)

    def test_delete_is_two_steps(self):
        document = self._document(self.forms)
        # A teacher can't erase a file, only move it to the trash.
        with self.assertRaises(AccessError):
            document.with_user(self.teacher).unlink()
        document.with_user(self.other_teacher).action_trash()
        self.assertFalse(document.active)
        self.assertNotIn(document, self.Document.search([("folder_id", "=", self.forms.id)]))
        with self.assertRaises(AccessError):
            document.with_user(self.teacher).action_delete_forever()
        document.with_user(self.teacher).action_restore()
        self.assertTrue(document.active)
        # For good: the office only, and only from the trash.
        with self.assertRaises(UserError):
            document.with_user(self.office).action_delete_forever()
        document.action_trash()
        attachment = self.env["ir.attachment"].search([
            ("res_model", "=", "school.document"), ("res_id", "=", document.id),
            ("res_field", "=", "datas"),
        ])
        self.assertTrue(attachment)
        document.with_user(self.office).action_delete_forever()
        self.assertFalse(document.exists())
        self.assertFalse(attachment.exists())

    def test_upload_several_files(self):
        Attachment = self.env["ir.attachment"].with_user(self.teacher)
        files = Attachment.create([
            {"name": "One.pdf", "datas": PDF, "res_model": "school.document.upload"},
            {"name": "Two.txt", "datas": base64.b64encode(b"hello"), "res_model": "school.document.upload"},
        ])
        wizard = self.env["school.document.upload"].with_user(self.teacher).create({
            "folder_id": self.room_folder.id,
            "attachment_ids": [Command.set(files.ids)],
        })
        action = wizard.action_upload()
        documents = self.Document.search([("folder_id", "=", self.room_folder.id)])
        self.assertEqual(sorted(documents.mapped("name")), ["One", "Two"])
        self.assertEqual(sorted(documents.mapped("filename")), ["One.pdf", "Two.txt"])
        self.assertFalse(files.exists())
        self.assertEqual(action["context"], {"default_folder_id": self.room_folder.id})
        empty = self.env["school.document.upload"].create({"folder_id": self.forms.id})
        with self.assertRaises(UserError):
            empty.action_upload()

    def test_folder_tree_shows_short_names(self):
        self._document(self.room_folder)
        result = self.Document.with_user(self.teacher).search_panel_select_range("folder_id", enable_counters=True)
        names = {value["id"]: value["display_name"] for value in result["values"]}
        self.assertEqual(names[self.room_folder.id], self.homeroom.name)
        self.assertNotIn(self.other_room_folder.id, names)

    def test_views_load(self):
        for model, view_types in [
            ("school.document", ("kanban", "list", "form", "search")),
            ("school.document.folder", ("list", "form", "search")),
            ("school.document.upload", ("form",)),
            ("school.student", ("form",)),
        ]:
            for view_type in view_types:
                self.env[model].with_user(self.teacher).get_view(view_type=view_type)
        self.assertIn("document_ids", self.env["school.student"].get_view(view_type="form")["arch"])

    # Files on the student record

    def test_student_files_follow_the_student(self):
        self.section_5.action_enroll_grade_levels()  # the teacher teaches Anna
        self.section_6.action_enroll_grade_levels()
        upload = self.env["ir.attachment"].with_user(self.office).create({
            "name": "Enrollment.pdf", "datas": PDF,
        })
        self.anna.with_user(self.office).document_ids = [Command.link(upload.id)]
        self.assertEqual((upload.res_model, upload.res_id), ("school.student", self.anna.id))
        self.assertEqual(self.anna.document_count, 1)
        # Every teacher sees every student, so every teacher opens it.
        self.assertEqual(upload.with_user(self.teacher).name, "Enrollment.pdf")
        self.assertEqual(upload.with_user(self.other_teacher).name, "Enrollment.pdf")

    def test_demo_loader(self):
        self.Document.with_context(active_test=False).search([]).unlink()
        self.env["school.year"]._load_school_documents_demo()
        documents = self.Document.search([])
        self.assertGreaterEqual(len(documents), 5)
        self.assertIn("pdf", documents.mapped("file_type"))
        self.env["school.year"]._load_school_documents_demo()
        self.assertEqual(self.Document.search_count([]), len(documents))
