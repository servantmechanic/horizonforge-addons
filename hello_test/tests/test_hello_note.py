from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHelloNote(TransactionCase):

    def test_create_note(self):
        note = self.env['hello.note'].create({'name': 'Test', 'description': 'Body'})
        self.assertEqual(note.name, 'Test')
        self.assertEqual(note.description, 'Body')
