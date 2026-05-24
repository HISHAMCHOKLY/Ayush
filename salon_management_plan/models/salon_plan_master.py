# -*- coding: utf-8 -*-
from odoo import api, fields, models

class SalonPlanMaster(models.Model):
    _name = 'salon.plan.master'
    _description = 'Treatment Plan Master'

    name = fields.Char(string='Plan Name', required=True)
    product_ids = fields.Many2many('product.product', string='Services', required=True, domain=[('type', '=', 'service')])
    amount = fields.Monetary(string='Plan Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.user.company_id.currency_id.id)
    no_of_persons = fields.Integer(string='Number of Persons', default=1, required=True)
    validity_months = fields.Integer(string='Validity (Months)', default=1, required=True)
    active = fields.Boolean(default=True)
