# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
import pytz
from dateutil.relativedelta import relativedelta

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
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('complete', 'Complete'),
        ('canceled', 'Canceled')
    ], string='Status', default='draft', copy=False)
    salon_order_ids = fields.One2many('salon.order', 'plan_order_id', string='Treatment Orders')
    salon_order_count = fields.Integer(string='Treatment Orders Count', compute='_compute_salon_order_count')
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    invoice_count = fields.Integer(string='Invoices Count', compute='_compute_invoice_count')

    member_ids = fields.Many2many('res.partner', string='Members')
    no_of_persons = fields.Integer(related='plan_id.no_of_persons', string='Allowed Persons', readonly=True)
    type = fields.Selection([
        ('2_hand', '2 Hand'),
        ('4_hand', '4 Hand')
    ], string='Type', default='2_hand', required=True)
    last_partner_id = fields.Many2one('res.partner', string='Last Customer', store=False)
    service_line_ids = fields.One2many('salon.plan.order.service', 'plan_order_id', string='Services')
    treatment_line_ids = fields.One2many('salon.order.line', 'plan_order_id', string='Treatment Lines', readonly=True)

    @api.constrains('member_ids', 'plan_id')
    def _check_member_ids_limit(self):
        for record in self:
            if record.plan_id:
                max_persons = record.plan_id.no_of_persons
                if len(record.member_ids) > max_persons:
                    raise ValidationError(_(
                        "The number of selected members (%s) cannot exceed the maximum limit of %s allowed by the selected plan '%s'."
                    ) % (len(record.member_ids), max_persons, record.plan_id.name))

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            old_partner = self.last_partner_id or self._origin.partner_id
            if old_partner and old_partner != self.partner_id:
                if old_partner in self.member_ids:
                    self.member_ids = [(3, old_partner.id)]
            
            if self.partner_id.id not in self.member_ids.ids:
                self.member_ids = [(4, self.partner_id.id)]
            
            self.last_partner_id = self.partner_id

    @api.onchange('start_date', 'plan_id')
    def _onchange_dates(self):
        if self.start_date and self.plan_id:
            self.end_date = self.start_date + relativedelta(months=self.plan_id.validity_months)

    @api.onchange('plan_id')
    def _onchange_plan_id_services(self):
        if self.plan_id and self.plan_id.product_ids:
            self.service_line_ids = [(5, 0, 0)] + [
                (0, 0, {
                    'product_id': product.id,
                    'allowed_count': 1,
                }) for product in self.plan_id.product_ids
            ]
        else:
            self.service_line_ids = [(5, 0, 0)]

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
        records = super().create(vals_list)
        for record in records:
            if record.partner_id and record.partner_id not in record.member_ids:
                super(SalonPlanOrder, record).write({'member_ids': [(4, record.partner_id.id)]})
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals or 'member_ids' in vals:
            for record in self:
                if record.partner_id and record.partner_id not in record.member_ids:
                    super(SalonPlanOrder, record).write({'member_ids': [(4, record.partner_id.id)]})
        return res

    def action_confirm(self):
        for record in self:
            if record.start_date > record.end_date:
                raise ValidationError(_("Start Date cannot be after End Date."))
            record.state = 'confirm'

    def action_complete(self):
        for record in self:
            record.state = 'complete'

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
        
        products = self.plan_id.product_ids
        if not products:
            raise ValidationError(_("Please set at least one service product on the Plan Master to create an invoice."))
        product = products[0]
            
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

    def action_create_treatment_order(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if today > self.end_date:
            raise ValidationError(_("You cannot create a treatment order because the plan order has expired (End Date: %s).") % self.end_date)
        
        default_date = today
        if default_date < self.start_date:
            default_date = self.start_date
            
        default_datetime = datetime.combine(default_date, datetime.min.time())

        return {
            'name': _('Create Treatment Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'salon.order',
            'view_mode': 'form',
            'context': {
                'default_plan_order_id': self.id,
                'default_date': default_datetime,
                'default_partner_id': self.partner_id.id,
                'active_id': False,
                'active_ids': [],
                'active_model': 'salon.order',
            },
            'target': 'current',
        }

class SalonPlanOrderService(models.Model):
    _name = 'salon.plan.order.service'
    _description = 'Treatment Plan Order Service'

    plan_order_id = fields.Many2one('salon.plan.order', string='Plan Order', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Service', required=True, domain=[('type', '=', 'service')])
    allowed_count = fields.Integer(string='Allowed Count', default=1, required=True)
    total_taken = fields.Integer(string='Total Taken', compute='_compute_service_counts')
    available_count = fields.Integer(string='Available Count', compute='_compute_service_counts')

    @api.depends('plan_order_id.salon_order_ids.state', 'plan_order_id.salon_order_ids.order_line_ids.product_id', 'allowed_count')
    def _compute_service_counts(self):
        for record in self:
            taken = 0
            if record.plan_order_id:
                orders = record.plan_order_id.salon_order_ids.filtered(lambda o: o.state != 'canceled')
                lines = orders.mapped('order_line_ids').filtered(lambda l: l.product_id == record.product_id)
                taken = len(lines)
            record.total_taken = taken
            record.available_count = record.allowed_count - taken
