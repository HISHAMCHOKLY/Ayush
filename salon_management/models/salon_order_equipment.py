# -*- coding: utf-8 -*-
from odoo import fields, models

class SalonOrderEquipment(models.Model):
    _name = 'salon.order.equipment'
    _description = 'Treatment Order Equipment'

    salon_order_id = fields.Many2one(
        'salon.order', 
        string="Treatment Order", 
        required=True, 
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product', 
        string="Equipment", 
        required=True
    )
    quantity = fields.Float(
        string="Quantity", 
        default=1.0
    )
