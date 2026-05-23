# -*- coding: utf-8 -*-
from odoo import api, fields, models

class SalonOrder(models.Model):
    _inherit = 'salon.order'

    plan_order_id = fields.Many2one('salon.plan.order', string="Plan Order", help="Plan order from which this order was created")
