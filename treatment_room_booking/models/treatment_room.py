from odoo import fields, models


class TreatmentRoom(models.Model):
    _name = "treatment.room"
    _description = "Treatment Room"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
