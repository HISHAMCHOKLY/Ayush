# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
import pytz

class SalonPlanOrder(models.Model):
    _name = 'salon.plan.order'
    _description = 'Treatment Plan Order'

    name = fields.Char(string='Order Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    plan_id = fields.Many2one('salon.plan.master', string='Plan', required=True)
    amount = fields.Monetary(string='Amount', related='plan_id.amount', readonly=True)
    currency_id = fields.Many2one(related='plan_id.currency_id')
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)
    start_time = fields.Float(string='Time', required=True, help="Time of day for the Treatment order (0.0 to 23.99)")
    chair_id = fields.Many2one('salon.chair', string='Room', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('validate', 'Validated'),
        ('invoiced', 'Invoiced'),
        ('canceled', 'Canceled')
    ], string='Status', default='draft', copy=False)
    salon_order_ids = fields.One2many('salon.order', 'plan_order_id', string='Treatment Orders')
    salon_order_count = fields.Integer(string='Treatment Orders Count', compute='_compute_salon_order_count')
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    invoice_count = fields.Integer(string='Invoices Count', compute='_compute_invoice_count')

    def _compute_salon_order_count(self):
        for record in self:
            record.salon_order_count = len(record.salon_order_ids)

    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = 1 if record.invoice_id else 0
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('salon.plan.order.sequence') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for record in self:
            if record.start_date > record.end_date:
                raise ValidationError(_("Start Date cannot be after End Date."))
            
            delta = record.end_date - record.start_date
            order_vals_list = []
            user_tz = pytz.timezone(self.env.user.tz or 'UTC')

            for i in range(delta.days + 1):
                current_date = record.start_date + timedelta(days=i)
                hours = int(record.start_time)
                minutes = int((record.start_time - hours) * 60)
                
                # Combine in user's timezone, then convert to UTC
                local_dt = user_tz.localize(datetime.combine(current_date, datetime.min.time()) + timedelta(hours=hours, minutes=minutes))
                utc_dt = local_dt.astimezone(pytz.UTC).replace(tzinfo=None)

                order_vals = {
                    'partner_id': record.partner_id.id,
                    'chair_id': record.chair_id.id,
                    'start_time': utc_dt,
                    'date': utc_dt,
                    'plan_order_id': record.id,
                    'order_line_ids': [(0, 0, {
                        'product_id': record.plan_id.product_id.id,
                        'price': record.plan_id.product_id.lst_price,
                        'time_taken': record.plan_id.product_id.time_taken,
                    })]
                }
                order_vals_list.append(order_vals)
            
            if order_vals_list:
                orders = self.env['salon.order'].create(order_vals_list)
            record.state = 'confirm'

    def action_confirm_orders(self):
        for record in self:
            for order in record.salon_order_ids:
                if order.state == 'draft':
                    order.action_confirm()
                # if order.state == 'confirm':
                #     order.action_validate()
            record.state = 'validate'

    def action_cancel(self):
        for record in self:
            for order in record.salon_order_ids:
                if order.state in ['draft', 'confirm', 'validate']:
                    order.action_cancel()
            record.state = 'canceled'

    def action_view_salon_orders(self):
        self.ensure_one()
        return {
            'name': _('Treatment Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'salon.order',
            'view_mode': 'list,form',
            'domain': [('plan_order_id', '=', self.id)],
            'context': {'default_plan_order_id': self.id},
        }

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            raise ValidationError(_("An invoice is already created for this plan order."))
        
        product = self.plan_id.product_id
        if not product:
            raise ValidationError(_("Please set a service product on the Plan Master to create an invoice."))
            
        accounts = product.product_tmpl_id.get_product_accounts()
        income_account = accounts.get('income')
        if not income_account:
            raise ValidationError(_("Please define an income account for this product: '%s'.") % product.name)
            
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_user_id': self.env.user.id,
            'invoice_origin': self.name,
            'invoice_line_ids': [(0, 0, {
                'name': self.plan_id.name,
                'product_id': product.id,
                'account_id': income_account.id,
                'price_unit': self.amount,
                'quantity': 1,
            })],
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        self.invoice_id = invoice.id
        self.state = 'invoiced'
        
        return self.action_view_invoice()

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return
        return {
            'name': _('Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
        }
