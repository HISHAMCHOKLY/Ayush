from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    is_therapist = fields.Boolean(string="Is Therapist", default=False, index=True)
