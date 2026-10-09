from odoo import fields, models


class HelloNote(models.Model):
    _name = 'hello.note'
    _description = 'Hello Note'

    name = fields.Char(required=True)
    description = fields.Text()
