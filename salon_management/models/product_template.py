# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    time_taken = fields.Float(
        string="Time",
        help="Approximate time required for this service in Hours"
    )
    equipment_ids = fields.One2many(
        'service.equipment.line',
        'service_id',
        string="Equipments",
        help="Equipments required for this service"
    )
