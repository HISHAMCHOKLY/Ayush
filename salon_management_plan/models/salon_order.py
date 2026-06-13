# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SalonOrder(models.Model):
    _inherit = 'salon.order'

    plan_order_id = fields.Many2one('salon.plan.order', string="Plan Order", help="Plan order from which this order was created")
    plan_member_ids = fields.Many2many('res.partner', related='plan_order_id.member_ids', string="Plan Members")
    is_care_of = fields.Boolean(string="Care Of", help="Check if this order is care of another member of the plan")
    care_of_partner_id = fields.Many2one('res.partner', string="Care Of Customer", help="Select a member from the plan order selected members")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            if self.plan_order_id and self.partner_id not in self.plan_order_id.member_ids:
                self.plan_order_id = False
                self.is_care_of = False
                self.care_of_partner_id = False
        else:
            self.plan_order_id = False
            self.is_care_of = False
            self.care_of_partner_id = False

    @api.onchange('is_care_of', 'plan_order_id')
    def _onchange_is_care_of(self):
        if not self.is_care_of or not self.plan_order_id:
            self.care_of_partner_id = False

    @api.constrains('partner_id', 'plan_order_id')
    def _check_partner_in_plan_members(self):
        for order in self:
            if order.plan_order_id and order.partner_id:
                if order.partner_id not in order.plan_order_id.member_ids:
                    raise ValidationError(_(
                        "The selected customer '%s' is not a member of the selected Plan Order '%s'."
                    ) % (order.partner_id.name, order.plan_order_id.name))

    @api.constrains('is_care_of', 'care_of_partner_id', 'plan_order_id')
    def _check_care_of_partner_in_plan_members(self):
        for order in self:
            if order.is_care_of and order.plan_order_id and order.care_of_partner_id:
                if order.care_of_partner_id not in order.plan_order_id.member_ids:
                    raise ValidationError(_(
                        "The selected Care Of Customer '%s' is not a member of the selected Plan Order '%s'."
                    ) % (order.care_of_partner_id.name, order.plan_order_id.name))

    @api.constrains('date', 'plan_order_id')
    def _check_plan_order_dates(self):
        for order in self:
            if order.plan_order_id and order.date:
                order_date = order.date.date()
                if order_date < order.plan_order_id.start_date or order_date > order.plan_order_id.end_date:
                    raise ValidationError(_(
                        "The treatment order date (%s) must be between the plan start date (%s) and end date (%s)."
                    ) % (order_date, order.plan_order_id.start_date, order.plan_order_id.end_date))

    @api.onchange('chair_id')
    def _onchange_chair_id(self):
        if self.env.context.get('active_model') != 'salon.chair':
            return
        return super()._onchange_chair_id()

    @api.onchange('plan_order_id')
    def _onchange_plan_order_id(self):
        if self.plan_order_id:
            plan_products = self.plan_order_id.service_line_ids.mapped('product_id')
            for line in self.order_line_ids:
                if line.product_id in plan_products:
                    line.price = 0.0
                    line.price_subtotal = 0.0
            if self.care_of_partner_id and self.care_of_partner_id not in self.plan_order_id.member_ids:
                self.care_of_partner_id = False
        else:
            for line in self.order_line_ids:
                if line.product_id:
                    line.price = line.product_id.lst_price
                    line.price_subtotal = line.product_id.lst_price
            self.is_care_of = False
            self.care_of_partner_id = False

    def action_confirm(self):
        for order in self:
            if order.name in ["Draft Salon Order", "Draft Treatment Order"]:
                order_date = str(order.date)
                order_date = order_date[0:10]
                if order.plan_order_id:
                    sequence_code = 'salon.order.plan.sequence'
                else:
                    sequence_code = 'salon.order.sequence'
                order.name = self.env['ir.sequence'].with_context(
                    ir_sequence_date=order_date
                ).next_by_code(sequence_code) or "Draft Treatment Order"
        return super().action_confirm()

    def action_validate(self):
        res = super().action_validate()
        for order in self:
            if order.equipment_line_ids and order.delivery_count == 0:
                order.action_create_delivery()
            pickings = self.env['stock.picking'].search([('origin', '=', order.name), ('state', 'not in', ['done', 'cancel'])])
            if pickings:
                pickings.action_assign()
                for move in pickings.move_ids:
                    move.picked = True
                pickings.button_validate()
        return res

class SalonOrderLine(models.Model):
    _inherit = 'salon.order.line'

    plan_order_id = fields.Many2one('salon.plan.order', related='salon_order_id.plan_order_id', string="Plan Order", store=True)
    date = fields.Datetime(related='salon_order_id.date', string='Date', store=True, readonly=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        res = super()._onchange_product_id()
        if self.salon_order_id.plan_order_id and self.product_id:
            plan_service = self.salon_order_id.plan_order_id.service_line_ids.filtered(
                lambda s: s.product_id == self.product_id
            )
            if plan_service:
                self.price = 0.0
                self.price_subtotal = 0.0
                
                # Check availability warning
                # Allowed count
                allowed = sum(plan_service.mapped('allowed_count'))
                # Taken in other orders
                other_orders = self.salon_order_id.plan_order_id.salon_order_ids.filtered(
                    lambda o: o.state != 'canceled' and o.id != (self.salon_order_id.id or self.salon_order_id._origin.id)
                )
                db_taken_other = len(other_orders.mapped('order_line_ids').filtered(lambda l: l.product_id == self.product_id))
                # Current order lines
                current_count = len(self.salon_order_id.order_line_ids.filtered(lambda l: l.product_id == self.product_id))
                
                available_now = allowed - db_taken_other - current_count
                if available_now < 0:
                    warning_msg = _(
                        "The product '%s' is not available or its limit has been exceeded in the selected Plan Order."
                    ) % self.product_id.name
                    return {
                        'warning': {
                            'title': _("Limit Exceeded"),
                            'message': warning_msg,
                        }
                    }
        return res
