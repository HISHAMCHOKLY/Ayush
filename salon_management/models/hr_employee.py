# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    """Inherit hr.employee to add is_doctor field"""
    _inherit = 'hr.employee'

    is_doctor = fields.Boolean(
        string="Is Doctor",
        help="Check this if the employee is a doctor")
