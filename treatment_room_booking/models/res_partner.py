from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_patient = fields.Boolean(string="Is Patient", default=False, index=True)
