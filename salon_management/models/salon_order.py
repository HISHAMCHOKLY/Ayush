# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Abbas P (odoo@cybrosys.com)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
################################################################################
from datetime import date, datetime, timedelta
from odoo import api, fields, models
from odoo.tools.translate import _
from odoo.exceptions import UserError, ValidationError


class SalonOrder(models.Model):
    """Model to create salon orders"""
    _name = 'salon.order'
    _description = 'Treatment Order'

    name = fields.Char(string='Treatment', required=True, copy=False, readonly=True,
                       default='Draft Treatment Order', help="Name of Treatment order")
    start_time = fields.Datetime(
        string="Start time", default=fields.Datetime.now, required=True,
        help="Start time of the order")
    end_time = fields.Datetime(string="End time", help="End time of the order")
    date = fields.Datetime(string="Date", required=True,
                           default=fields.Datetime.now, help="Registering date")
    partner_id = fields.Many2one(
        'res.partner', string="Patient", required=False,
        help="If the patient is a regular patient, then you can add the"
             " patient in your database")
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.user.company_id.currency_id.id,
        help="Currency used in the order")
    chair_id = fields.Many2one('salon.chair', string="Room",
                               required=True, help="Room for the current "
                                                   "order")
    price_subtotal = fields.Monetary(string='Total', readonly=True, store=True,
                                     compute='_compute_price_subtotal',
                                     help="Total price of order")
    time_taken_total = fields.Float(string='Total time',
                                    help='Total time taken')
    note = fields.Text(string='Terms and conditions',
                       help="Note for current order")
    order_line_ids = fields.One2many(comodel_name='salon.order.line',
                                     inverse_name='salon_order_id',
                                     string="Order Lines", copy=True,
                                     help='Treatment order line for add '
                                          'list of services', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('validate', 'Validated'),
        ('invoiced', 'Invoiced'),
        ('canceled', 'Canceled')
    ], string='Status', default='draft', copy=False, help="State of the Treatment order")
    inv_stage_identifier = fields.Boolean(string="Stage Identifier",
                                          help="Field to detect stage")
    booking_identifier = fields.Boolean(string="Booking Identifier",
                                        help="Field to identify booking")
    user_id = fields.Many2one('res.users', string="Room User")
    salon_order_created_user = fields.Integer(string="Treatment Order Created User",
                                              default=lambda self: self._uid,
                                              help="The user whom the Treatment"
                                                   " order created.")
    count = fields.Integer(string='Invoices', compute='_compute_count',
                           help="The count of the invoice")
    invoice_id = fields.Many2one('account.move', string="Invoice")
    invoice_state = fields.Selection(related='invoice_id.state', string="Invoice State", store=True)
    invoice_payment_state = fields.Selection(related='invoice_id.payment_state', string="Invoice Payment State", store=True)
    patient_type = fields.Selection([
        ('self', 'Self'),
        ('care_of', 'Care Of')
    ], string="Patient Type", default='self', required=True, help="Select if the order is for self or care of someone else.")
    care_of_partner_id = fields.Many2one(
        'res.partner', string="Care Of Patient",
        domain="[('parent_id', '=', partner_id)]",
        help="Select a partner whose parent matches the partner in the salon order."
    )
    equipment_line_ids = fields.One2many('salon.order.equipment', 'salon_order_id', string="Equipments", compute='_compute_equipment_ids', store=True, readonly=False)
    delivery_count = fields.Integer(string='Delivery Orders', compute='_compute_delivery_count', help="The count of the delivery")
    employee_ids = fields.Many2many(
        'hr.employee', string="Therapists",
        help="Therapists assigned to this Treatment order")
    doctor_id = fields.Many2one(
        'hr.employee', string="Doctor",
        domain="[('is_doctor', '=', True)]",
        help="Doctor assigned to this Treatment order")

    def _compute_delivery_count(self):
        """Compute the count of devalidation_controllerlivery orders"""
        for order in self:
            order.delivery_count = self.env['stock.picking'].search_count([('origin', '=', order.name)])

    def _check_employee_availability(self):
        """Check if the assigned therapists are already booked on
        another confirmed or validated order during the same time period."""
        for order in self:
            if not order.employee_ids:
                continue
            domain = [
                ('id', '!=', order.id),
                ('state', 'in', ['confirm', 'validate']),
                ('employee_ids', 'in', order.employee_ids.ids),
            ]
            # Check time overlap if both start_time and end_time are set
            if order.start_time and order.end_time:
                domain += [
                    ('start_time', '<', order.end_time),
                    ('end_time', '>', order.start_time),
                ]
            conflicting_orders = self.env['salon.order'].search(domain)
            if conflicting_orders:
                # Find which therapists are conflicting
                conflicting_employees = order.employee_ids.filtered(
                    lambda emp: emp.id in conflicting_orders.mapped('employee_ids').ids
                )
                employee_names = ', '.join(conflicting_employees.mapped('name'))
                order_names = ', '.join(conflicting_orders.mapped('name'))
                raise ValidationError(
                    _("The following therapist(s) are already assigned to "
                      "confirmed/validated order(s) during this time period:\n\n"
                      "Therapist(s): %s\n"
                      "Conflicting Order(s): %s\n\n"
                      "Please choose different therapists or adjust the time.",
                      employee_names, order_names)
                )

    @api.depends('order_line_ids.product_id', 'order_line_ids.product_id.product_tmpl_id.equipment_ids')
    def _compute_equipment_ids(self):
        for order in self:
            equipment_dict = {}
            for line in order.order_line_ids:
                if line.product_id and line.product_id.product_tmpl_id.equipment_ids:
                    for eq in line.product_id.product_tmpl_id.equipment_ids:
                        if eq.product_id.id in equipment_dict:
                            equipment_dict[eq.product_id.id] += eq.quantity
                        else:
                            equipment_dict[eq.product_id.id] = eq.quantity
            
            commands = [(5, 0, 0)]
            for prod_id, qty in equipment_dict.items():
                commands.append((0, 0, {
                    'product_id': prod_id,
                    'quantity': qty
                }))
            order.equipment_line_ids = commands

    def action_view_delivery(self):
        """Function to open delivery order for the salon order"""
        self.ensure_one()
        return {'name': 'Delivery Orders',
                'domain': [('origin', '=', self.name)],
                'res_model': 'stock.picking',
                'view_mode': 'list,form',
                'type': 'ir.actions.act_window'}

    @api.depends('order_line_ids.price_subtotal')
    def _compute_price_subtotal(self):
        """Compute the subtotal price of order line"""
        amount_untaxed = 0.0
        self.price_subtotal = amount_untaxed

    @api.onchange('order_line_ids')
    def onchange_time_taken(self):
        total_time_taken = 0.0
        for order in self:
            for line in order.order_line_ids:
                total_time_taken += line.time_taken
        time_takes = total_time_taken
        hours = int(time_takes)
        minutes = (time_takes - hours) * 60
        start_time_store = datetime.strptime(
            str(self.start_time).split(".")[0], "%Y-%m-%d %H:%M:%S")
        self.write({'end_time': start_time_store + timedelta(
            hours=hours, minutes=minutes),
                    'time_taken_total': total_time_taken})

    def _compute_count(self):
        """Compute invoice count of salon orders"""
        for orders in self:
            orders.count = self.env['account.move'].search_count(
                [('invoice_origin', '=', self.name)])

    def action_view_invoice_salon(self):
        """Function to open invoice for the salon order"""
        return {'name': 'Invoices',
                'domain': [('invoice_origin', '=', self.name)],
                'res_model': 'account.move',
                'view_id': False,
                'view_mode': 'list,form',
                'type': 'ir.actions.act_window'}

    def write(self, values):
        """ Manage drag and drop in salon order kanban view """
        if 'state' in values:
            if self.state == 'invoiced':
                raise ValidationError(_("You can't perform that move!"))
            if self.state == 'canceled':
                raise ValidationError(
                    _("You can't move a salon order from Canceled state!"))
            if self.state == 'draft':
                if values['state'] not in ['confirm', 'canceled']:
                    raise ValidationError(_("You can't perform that move!"))
            if self.state == 'confirm':
                if values['state'] == 'canceled':
                    time_taken_chair = self.chair_id.total_time_taken_chair
                    self.chair_id.total_time_taken_chair = (
                            time_taken_chair - self.time_taken_total)
                elif values['state'] not in ['validate', 'canceled']:
                    raise ValidationError(_("You can't perform that move!"))
            if self.state == 'validate':
                if values['state'] == 'canceled':
                    time_taken_chair = self.chair_id.total_time_taken_chair
                    self.chair_id.total_time_taken_chair = (
                            time_taken_chair - self.time_taken_total)
                elif values['state'] not in ['invoiced', 'canceled']:
                    raise ValidationError(_("You can't perform that move!"))
                elif values['state'] == 'invoiced' and not self.inv_stage_identifier:
                    self.action_create_invoice()
                    
        if 'state' in values and self.name == "Draft Salon Order":
            if values['state'] == 'confirm':
                self.action_confirm()

        # self.update_number_of_orders()
        return super(SalonOrder, self).write(values)

    def action_confirm(self):
        """Confirm function of salon order"""
        self._check_employee_availability()
        sequence_code = 'salon.order.sequence'
        order_date = str(self.date)
        order_date = order_date[0:10]
        if self.name == "Draft Salon Order":
            self.name = self.env['ir.sequence'].with_context(
                ir_sequence_date=order_date).next_by_code(sequence_code)
        if self.partner_id:
            self.partner_id.partner_salon = True
        self.state = 'confirm'
        # self.update_number_of_orders()
        self.chair_id.total_time_taken_chair += self.time_taken_total
        self.user_id = self.chair_id.user_id

    def action_validate(self):
        """ Validate function of salon order"""
        self._check_employee_availability()
        self.state = 'validate'
        
    def action_create_delivery(self):
        """Function to create delivery order manually"""
        for order in self:
            if order.delivery_count > 0:
                raise UserError(_("A delivery order has already been created for this salon order!"))
            picking_type = self.env['stock.picking.type'].search([('code', '=', 'outgoing'), ('company_id', '=', self.env.user.company_id.id)], limit=1)
            if not picking_type:
                picking_type = self.env['stock.picking.type'].search([('code', '=', 'outgoing')], limit=1)
            if order.equipment_line_ids and picking_type:
                location_id = picking_type.default_location_src_id.id
                location_dest_id = picking_type.default_location_dest_id.id
                if not location_dest_id:
                    location_dest_id = self.env.ref('stock.stock_location_customers', raise_if_not_found=False).id
                picking_vals = {
                    'partner_id': order.partner_id.id,
                    'picking_type_id': picking_type.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'origin': order.name,
                }
                picking = self.env['stock.picking'].create(picking_vals)
                for eq in order.equipment_line_ids:
                    if eq.product_id and eq.quantity > 0:
                        self.env['stock.move'].create({
                            'name': eq.product_id.name,
                            'product_id': eq.product_id.id,
                            'product_uom_qty': eq.quantity,
                            'product_uom': eq.product_id.uom_id.id,
                            'picking_id': picking.id,
                            'location_id': location_id,
                            'location_dest_id': location_dest_id,
                        })
                picking.action_confirm()

        # self.update_number_of_orders()

    def action_cancel(self):
        """Function to cancel the salon order"""
        if self.state in ['confirm', 'validate']:
            time_taken_chair = self.chair_id.total_time_taken_chair
            self.chair_id.total_time_taken_chair = (time_taken_chair - self.time_taken_total)
        self.state = 'canceled'
        # self.update_number_of_orders()

    def action_update_total(self):
        """Update total amount in salon order"""
        for order in self:
            amount_untaxed = 0.0
            for line in order.order_line_ids:
                amount_untaxed += line.price_subtotal
            order.price_subtotal = amount_untaxed

    @api.onchange('chair_id')
    def _onchange_chair_id(self):
        """Onchange function of chair_id field"""
        if 'active_id' in self._context.keys():
            self.chair_id = self._context['active_id']

    @api.onchange('patient_type', 'partner_id')
    def _onchange_patient_type_partner_id(self):
        if self.patient_type != 'care_of' or not self.partner_id:
            self.care_of_partner_id = False
        elif self.care_of_partner_id and self.care_of_partner_id.parent_id != self.partner_id:
            self.care_of_partner_id = False

    def action_create_invoice(self):
        """Function to create invoice from salon order lines"""
        self.ensure_one()
        if not self.order_line_ids:
            raise UserError(_("Please add at least one service line to "
                              "create an invoice."))
        if self.partner_id:
            customer = self.partner_id
        else:
            customer = self.env['res.partner'].search(
                [("name", "=", "Salon Default Customer")], limit=1)
            if not customer:
                raise UserError(_("Please define a customer or ensure"))
        lines = []
        for records in self.order_line_ids:
            product = records.product_id
            if not product:
                continue
            accounts = product.product_tmpl_id.get_product_accounts()
            income_account = accounts.get('income')
            if not income_account:
                raise UserError(
                    _("Please define income account for this product: "
                      "'%s' (id:%d).") % (product.name, product.id))
            value = (0, 0, {
                # 'name': records.service_id.name or product.name,
                'account_id': income_account.id,
                'price_unit': records.price,
                'quantity': 1,
                'product_id': product.id,
            })
            lines.append(value)
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': customer.id,
            'invoice_user_id': self.env.user.id,
            'invoice_origin': self.name,
            'salon_order_id': self.id,
            'invoice_line_ids': lines})
        self.invoice_id = invoice.id
        self.inv_stage_identifier = True
        self.state = 'invoiced'
        result = {
            'name': self.env.ref('account.action_move_out_invoice_type',
                                 raise_if_not_found=False).name,
            'type': 'ir.actions.act_window',
            'views': [[False, 'form']],
            'target': 'current',
            'res_id': invoice.id,
            'res_model': 'account.move',
        }
        return result

    def unlink(self):
        """ Unlink/delete salon order """
        for order in self:
            if order.state in ['invoiced', 'closed']:
                raise UserError(_("You can't delete an invoiced salon order!"))
        return super(SalonOrder, self).unlink()

    # def update_number_of_orders(self):
    #     """ Function to update the number of active orders for the chair."""
    #     self.chair_id.number_of_orders = len(self.env['salon.order'].search([
    #     ]).filtered(lambda order: order.chair_id.id == self.chair_id.id
    #                 and order.stage_id in [2, 3]))
