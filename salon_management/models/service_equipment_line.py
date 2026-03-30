# -*- coding: utf-8 -*-
from odoo import fields, models


class ServiceEquipmentLine(models.Model):
    _name = 'service.equipment.line'
    _description = 'Service Equipment Line'

    service_id = fields.Many2one(
        'product.template',
        string="Service",
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string="Equipment",
        required=True
    )
    quantity = fields.Float(string="Quantity", default=1.0)
    price = fields.Float(string="Price")
