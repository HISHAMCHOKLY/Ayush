from datetime import datetime, timedelta, time
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class TreatmentBooking(models.Model):
    _name = "treatment.booking"
    _description = "Treatment Booking"
    _order = "start_datetime, room_id"
    _rec_name = "name"

    name = fields.Char(default="New", required=True, copy=False)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company, index=True,
    )
    customer_id = fields.Many2one("res.partner", string="Patient", required=True, domain=[("is_patient", "=", True)])
    contact_number = fields.Char(related="customer_id.phone", string="Contact Number", readonly=True)
    room_id = fields.Many2one("treatment.room", required=True, ondelete="restrict")
    service_id = fields.Many2one("treatment.service", ondelete="restrict", string="Primary Service")
    service_ids = fields.Many2many("treatment.service", "treatment_booking_service_rel", "booking_id", "service_id", string="Services", domain=[("active", "=", True)])
    service_names = fields.Char(compute="_compute_service_names", string="Service Names", readonly=True)
    mobile_number = fields.Char(related="customer_id.mobile", string="Patient Mobile Number", readonly=True)
    discount_percent = fields.Float(string="Discount %", default=0.0)
    discounted_price = fields.Monetary(string="Discounted Price", compute="_compute_booking_financials", currency_field="currency_id", readonly=True, store=True)
    paid_amount = fields.Monetary(string="Paid Amount", compute="_compute_booking_financials", currency_field="currency_id", readonly=True, store=True)
    therapist_ids = fields.Many2many("hr.employee", "treatment_booking_employee_rel", "booking_id", "employee_id", string="Therapists", domain=[("active", "=", True), ("is_therapist", "=", True)])
    # Keep the dashboard payload compatible while supporting multiple therapists.
    therapist_name = fields.Char(compute="_compute_therapist_name", string="Therapist Names", readonly=True)
    start_datetime = fields.Datetime(required=True, string="Start")
    end_datetime = fields.Datetime(required=True, string="End")
    cleaning_minutes = fields.Integer(default=10, string="Cleaning Buffer (minutes)")
    notes = fields.Text()
    state = fields.Selection([
        ("draft", "Draft"), ("confirmed", "Confirmed"),
        ("in_progress", "In Progress"), ("done", "Done"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, copy=False)
    color = fields.Selection([("red", "Booked"), ("green", "Confirmed")], default="red")
    payment_ids = fields.One2many("treatment.booking.payment", "booking_id", string="Payments")
    payment_status = fields.Selection([("unpaid", "Unpaid"), ("partial", "Partially Paid"), ("paid", "Paid")], compute="_compute_payment_status", store=True)
    payment_count = fields.Integer(compute="_compute_related_counts")
    balance_amount = fields.Monetary(string="Balance Amount", compute="_compute_balance_amount", currency_field="currency_id", store=False)
    inventory_count = fields.Integer(compute="_compute_related_counts")

    def _compute_related_counts(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids.filtered(lambda p: p.state == "posted" and p.account_payment_id))
            rec.inventory_count = 1 if rec.stock_picking_id else 0
    amount_total = fields.Monetary(compute="_compute_amount_total", store=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id", store=True, readonly=True)
    stock_picking_id = fields.Many2one("stock.picking", readonly=True, copy=False, string="Stock Consumption Transfer")

    @api.depends("service_id", "service_ids", "service_id.currency_id", "service_ids.currency_id")
    def _compute_currency_id(self):
        for rec in self:
            if rec.service_id and rec.service_id.currency_id:
                rec.currency_id = rec.service_id.currency_id
            elif rec.service_ids:
                rec.currency_id = rec.service_ids[0].currency_id
            else:
                rec.currency_id = self.env.company.currency_id

    @api.depends("therapist_ids", "therapist_ids.name")
    def _compute_therapist_name(self):
        for rec in self:
            rec.therapist_name = ", ".join(rec.therapist_ids.mapped("name"))

    @api.depends("service_id", "service_ids", "service_id.price", "service_ids.price")
    def _compute_amount_total(self):
        for rec in self:
            services = rec.service_ids or rec.service_id
            rec.amount_total = sum(services.mapped("price")) if services else 0.0

    @api.depends("service_id", "service_ids", "service_ids.name")
    def _compute_service_names(self):
        for rec in self:
            services = rec.service_ids or rec.service_id
            rec.service_names = ", ".join(services.mapped("name"))

    @api.depends("amount_total", "discount_percent", "payment_ids.state", "payment_ids.paid_amount", "payment_ids.discounted_price")
    def _compute_booking_financials(self):
        for rec in self:
            posted = rec.payment_ids.filtered(lambda p: p.state == "posted")
            rec.paid_amount = sum(posted.mapped("paid_amount"))
            latest = posted[-1] if posted else False
            # If a payment has been posted use its discounted_price, otherwise
            # derive it from the booking-level discount_percent.
            if latest:
                rec.discounted_price = latest.discounted_price
            else:
                discount = min(max(rec.discount_percent, 0.0), 100.0)
                rec.discounted_price = rec.amount_total * (1.0 - discount / 100.0)

    @api.depends("payment_ids.state", "payment_ids.paid_amount", "payment_ids.discounted_price", "amount_total")
    def _compute_balance_amount(self):
        for rec in self:
            posted = rec.payment_ids.filtered(lambda p: p.state == "posted")
            paid = sum(posted.mapped("paid_amount"))
            target = posted[-1].discounted_price if posted else rec.amount_total
            rec.balance_amount = max(target - paid, 0.0)

    @api.depends("payment_ids.state", "payment_ids.paid_amount", "payment_ids.discounted_price", "amount_total")
    def _compute_payment_status(self):
        # A payment wizard is only a draft until Register Payment successfully
        # creates and posts the Odoo account.payment. Draft wizard values must
        # never make the booking appear paid or block the Register Payment button.
        for rec in self:
            posted = rec.payment_ids.filtered(lambda payment: payment.state == "posted")
            paid = sum(posted.mapped("paid_amount"))
            target = posted[-1].discounted_price if posted else rec.amount_total
            rec.payment_status = "paid" if target > 0 and paid >= target else ("partial" if paid > 0 else "unpaid")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("treatment.booking") or "New"
            service_ids = vals.get("service_ids")
            selected_service_ids = []
            if service_ids and isinstance(service_ids, list):
                ids = []
                for cmd in service_ids:
                    if isinstance(cmd, (list, tuple)) and cmd[0] == 6: ids = cmd[2]
                    elif isinstance(cmd, (list, tuple)) and cmd[0] == 4: ids.append(cmd[1])
                selected_service_ids = ids
                if ids and not vals.get("service_id"): vals["service_id"] = ids[0]
            sid = vals.get("service_id")
            if (sid or selected_service_ids) and vals.get("start_datetime") and not vals.get("end_datetime"):
                services = self.env["treatment.service"].browse(selected_service_ids or ([sid] if sid else []))
                start = fields.Datetime.to_datetime(vals["start_datetime"])
                vals["end_datetime"] = start + timedelta(minutes=sum(services.mapped("duration_minutes")))
                vals.setdefault("cleaning_minutes", max(services.mapped("cleaning_minutes") or [10]))
        records = super().create(vals_list)
        records._check_room_overlap()
        records._check_stock_availability()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._check_room_overlap()
        if any(k in vals for k in ("service_id", "service_ids", "state", "start_datetime")):
            self.filtered(lambda r: r.state not in ("cancelled", "done"))._check_stock_availability()
        return result

    @api.onchange("service_ids")
    def _onchange_services(self):
        for rec in self:
            if rec.service_ids:
                if not rec.service_id or rec.service_id not in rec.service_ids:
                    rec.service_id = rec.service_ids[0]
                rec.cleaning_minutes = max(rec.service_ids.mapped("cleaning_minutes") or [10])
                if rec.start_datetime:
                    rec.end_datetime = rec.start_datetime + timedelta(minutes=sum(rec.service_ids.mapped("duration_minutes")))
                shortages = rec._get_stock_shortages()
                if shortages:
                    return {"warning": {"title": _("Insufficient Stock"), "message": "\n".join(shortages)}}

    @api.onchange("service_id", "start_datetime")
    def _onchange_service_start(self):
        for rec in self:
            services = rec.service_ids or rec.service_id
            if services:
                if not rec.service_ids and rec.service_id:
                    rec.service_ids = [(6, 0, rec.service_id.ids)]
                rec.cleaning_minutes = max(services.mapped("cleaning_minutes") or [10])
                if rec.start_datetime:
                    rec.end_datetime = rec.start_datetime + timedelta(minutes=sum(services.mapped("duration_minutes")))
                shortages = rec._get_stock_shortages()
                if shortages:
                    return {"warning": {"title": _("Insufficient Stock"), "message": "\n".join(shortages)}}

    def _get_stock_shortages(self):
        self.ensure_one()
        shortages = []
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        stock_location = warehouse.lot_stock_id if warehouse else self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
        if not stock_location:
            return shortages
        for line in (self.service_ids or self.service_id).mapped("consumable_line_ids"):
            product = line.product_id
            available = product.with_context(location=stock_location.id).qty_available
            if available < line.quantity:
                shortages.append(_("%s: required %s %s, available %s %s") % (product.display_name, line.quantity, line.product_uom_id.name, available, line.product_uom_id.name))
        return shortages

    def _check_stock_availability(self):
        for rec in self.filtered(lambda r: r.service_id and r.state not in ("cancelled", "done")):
            shortages = rec._get_stock_shortages()
            if shortages:
                raise ValidationError(_("Cannot create/update this booking because required service stock is unavailable:\n%s") % "\n".join(shortages))

    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                continue
            rec._check_stock_availability()
            rec.state = "confirmed"
            rec.color = "green"
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "cancelled"})
        return True

    def action_start(self):
        self.filtered(lambda r: r.state == "confirmed").write({"state": "in_progress"})
        return True

    def action_mark_done(self):
        for rec in self:
            if rec.state not in ("confirmed", "in_progress"):
                raise UserError(_("Only confirmed or in-progress bookings can be marked done."))
            rec._consume_service_stock()
            rec.state = "done"
        return True

    def _consume_service_stock(self):
        self.ensure_one()
        if self.stock_picking_id:
            return
        lines = (self.service_ids or self.service_id).mapped("consumable_line_ids")
        if not lines:
            return
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        source = warehouse.lot_stock_id if warehouse else self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
        destination = self.env.ref("stock.stock_location_customers")
        if not source:
            raise UserError(_("No internal stock location was found for this company."))
        shortages = self._get_stock_shortages()
        if shortages:
            raise ValidationError(_("Cannot complete booking due to insufficient stock:\n%s") % "\n".join(shortages))
        picking_type = warehouse.out_type_id if warehouse else self.env["stock.picking.type"].search([("code", "=", "outgoing"), ("company_id", "=", self.env.company.id)], limit=1)
        if not picking_type:
            raise UserError(_("No outgoing operation type is configured."))
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "origin": self.name,
            "partner_id": self.customer_id.id,
        })
        for line in lines:
            self.env["stock.move"].create({
                "name": _("%s - %s") % (self.name, line.product_id.display_name),
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.product_uom_id.id,
                "picking_id": picking.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
            })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.button_validate()
        self.stock_picking_id = picking.id

    def action_open_payment(self):
        self.ensure_one()
        if self.state not in ("confirmed", "done"):
            raise UserError(_("Payments can only be registered for confirmed or completed bookings."))
        if self.payment_status == "paid":
            raise UserError(_("This booking is already fully paid."))
        posted = self.payment_ids.filtered(lambda payment: payment.state == "posted")
        already_paid = sum(posted.mapped("paid_amount"))
        latest = posted[-1] if posted else False
        target_amount = latest.discounted_price if latest else self.discounted_price
        balance = max(target_amount - already_paid, 0.0)
        if balance <= 0:
            raise UserError(_("This booking is already fully paid."))
        return {"type": "ir.actions.act_window", "name": _("Receipt Payment"),
                "res_model": "treatment.booking.payment", "view_mode": "form",
                "target": "new", "context": {
                    "default_booking_id": self.id,
                    "default_discount_percent": latest.discount_percent if latest else self.discount_percent,
                    "default_paid_amount": balance,
                }}

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref("treatment_room_booking.action_report_treatment_booking_receipt").report_action(self)

    def action_view_payments(self):
        self.ensure_one()
        payments = self.payment_ids.filtered(lambda line: line.state == "posted" and line.account_payment_id).mapped("account_payment_id")
        if not payments:
            raise UserError(_("No registered customer payment records are linked to this booking yet."))
        return {"type": "ir.actions.act_window", "name": _("Customer Payments"),
                "res_model": "account.payment", "view_mode": "list,form",
                "domain": [("id", "in", payments.ids)], "context": {"create": False}}

    def action_view_inventory(self):
        self.ensure_one()
        if not self.stock_picking_id:
            return {"type": "ir.actions.act_window_close"}
        return {"type": "ir.actions.act_window", "name": _("Inventory Transfer"),
                "res_model": "stock.picking", "view_mode": "form",
                "res_id": self.stock_picking_id.id}

    @api.constrains("start_datetime", "end_datetime", "room_id", "cleaning_minutes", "state")
    def _check_room_overlap(self):
        for rec in self:
            if not rec.start_datetime or not rec.end_datetime:
                continue
            if rec.end_datetime <= rec.start_datetime:
                raise ValidationError(_("End time must be after start time."))

            # Odoo stores Datetime values in UTC in PostgreSQL. Convert both
            # values to the user's configured timezone before checking the
            # weekday and comparing with the configured local working hours.
            user_tz = rec.env.context.get("tz") or rec.env.user.tz or "UTC"
            local_rec = rec.with_context(tz=user_tz)
            local_start = fields.Datetime.context_timestamp(local_rec, rec.start_datetime)
            local_end = fields.Datetime.context_timestamp(local_rec, rec.end_datetime)

            if local_start.date() != local_end.date():
                raise ValidationError(_("A treatment booking must start and finish on the same local day."))

            weekday_key = str(local_start.weekday())
            work_hours = self.env["treatment.working.hours"].search(
                [("weekday", "=", weekday_key)], limit=1
            )
            if work_hours and work_hours.is_closed:
                raise ValidationError(
                    _("The treatment center is closed on %s.") % local_start.strftime("%A")
                )

            # Work-hour fields are decimal hours (e.g. 7.5 = 07:30).
            # Compare minute values consistently, including seconds.
            open_minute = int(round(work_hours.start_hour * 60)) if work_hours else 7 * 60
            close_minute = int(round(work_hours.end_hour * 60)) if work_hours else 19 * 60
            start_minute = local_start.hour * 60 + local_start.minute
            end_minute = local_end.hour * 60 + local_end.minute
            if local_end.second or local_end.microsecond:
                end_minute += 1

            if start_minute < open_minute or end_minute > close_minute:
                open_label = "%02d:%02d" % (open_minute // 60, open_minute % 60)
                close_label = "%02d:%02d" % (close_minute // 60, close_minute % 60)
                raise ValidationError(
                    _("Booking time %(start)s–%(end)s on %(weekday)s is outside the configured working hours %(opening)s–%(closing)s (%(tz)s).",
                      start=local_start.strftime("%H:%M"),
                      end=local_end.strftime("%H:%M"),
                      weekday=local_start.strftime("%A"),
                      opening=open_label,
                      closing=close_label,
                      tz=user_tz)
                )

            if rec.state == "cancelled":
                continue
            busy_end = rec.end_datetime + timedelta(minutes=rec.cleaning_minutes or 0)
            domain = [
                ("id", "!=", rec.id),
                ("room_id", "=", rec.room_id.id),
                ("state", "!=", "cancelled"),
                ("start_datetime", "<", busy_end),
            ]
            for other in self.search(domain):
                if other.end_datetime + timedelta(minutes=other.cleaning_minutes or 0) > rec.start_datetime:
                    raise ValidationError(_("This room is already booked during that time (including cleaning buffer)."))

    @api.model
    def get_dashboard_data(self, date_string=False):
        """Return rooms and bookings for the selected local calendar date."""
        from_date = fields.Date.to_date(date_string) if date_string else fields.Date.context_today(self)
        start = datetime.combine(from_date - timedelta(days=1), time.min)
        end = datetime.combine(from_date + timedelta(days=2), time.min)
        rooms = self.env["treatment.room"].search_read([("active", "=", True)], ["name", "sequence"], order="sequence, name")
        services = self.env["treatment.service"].search_read([("active", "=", True)], ["name", "duration_minutes", "cleaning_minutes"], order="name")
        weekday_hours = self.env["treatment.working.hours"].search([("weekday", "=", str(from_date.weekday()))], limit=1)
        working_hours = {"is_closed": weekday_hours.is_closed if weekday_hours else False, "start_hour": weekday_hours.start_hour if weekday_hours else 7.0, "end_hour": weekday_hours.end_hour if weekday_hours else 19.0, "weekday": from_date.strftime("%A")}
        today = fields.Date.context_today(self)
        tomorrow = today + timedelta(days=1)
        month_start = today.replace(day=1)
        next_month = month_start.replace(year=month_start.year + 1, month=1) if month_start.month == 12 else month_start.replace(month=month_start.month + 1)
        active_domain = [("state", "!=", "cancelled")]
        today_count = self.search_count(active_domain + [("start_datetime", ">=", fields.Datetime.to_string(datetime.combine(today, time.min))), ("start_datetime", "<", fields.Datetime.to_string(datetime.combine(tomorrow, time.min)))])
        month_count = self.search_count(active_domain + [("start_datetime", ">=", fields.Datetime.to_string(datetime.combine(month_start, time.min))), ("start_datetime", "<", fields.Datetime.to_string(datetime.combine(next_month, time.min)))])
        bookings = self.search_read([("start_datetime", ">=", fields.Datetime.to_string(start)), ("start_datetime", "<", fields.Datetime.to_string(end)), ("state", "!=", "cancelled")], ["name", "customer_id", "room_id", "service_id", "service_ids", "service_names", "therapist_name", "start_datetime", "end_datetime", "cleaning_minutes", "state", "notes", "contact_number", "mobile_number", "payment_status"])
        for booking in bookings:
            booking["dashboard_status"] = "paid" if booking.get("payment_status") == "paid" else booking.get("state")
        return {"rooms": rooms, "services": services, "bookings": bookings, "today_count": today_count, "month_count": month_count, "date": str(from_date), "working_hours": working_hours}


class TreatmentBookingPayment(models.Model):
    _name = "treatment.booking.payment"
    _description = "Treatment Booking Payment"
    _order = "date desc, id desc"

    booking_id = fields.Many2one("treatment.booking", required=True, ondelete="cascade", readonly=True)
    customer_id = fields.Many2one("res.partner", string="Patient", related="booking_id.customer_id", readonly=True)
    mobile_number = fields.Char(related="booking_id.contact_number", readonly=True)
    date = fields.Date(default=fields.Date.context_today, readonly=True, required=True)
    total_amount = fields.Monetary(related="booking_id.amount_total", readonly=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="booking_id.currency_id", readonly=True)
    discount_percent = fields.Float(string="Discount %", default=0.0)
    discounted_price = fields.Monetary(compute="_compute_amounts", currency_field="currency_id", store=True, readonly=True)
    paid_amount = fields.Monetary(currency_field="currency_id", required=True, default=0.0)
    payment_action = fields.Selection([
        ("keep_open", "Keep Open"),
        ("mark_paid", "Mark as Paid"),
    ], string="After Payment", default="keep_open", required=True)
    remaining_amount = fields.Monetary(compute="_compute_amounts", currency_field="currency_id", store=True, readonly=True)
    payment_status = fields.Selection([("paid", "Paid"), ("partial", "Partially Paid")], compute="_compute_amounts", store=True, readonly=True)
    journal_id = fields.Many2one("account.journal", string="Payment Journal", required=True,
                                  domain=[("type", "in", ["cash", "bank"])])
    state = fields.Selection([("draft", "Draft"), ("posted", "Posted")], default="draft", readonly=True, copy=False)
    account_payment_id = fields.Many2one("account.payment", string="Customer Payment", readonly=True, copy=False)

    @api.depends("total_amount", "discount_percent", "paid_amount")
    def _compute_amounts(self):
        for rec in self:
            discount = min(max(rec.discount_percent, 0.0), 100.0)
            net = rec.total_amount * (1 - discount / 100.0)
            rec.discounted_price = net
            posted = rec.booking_id.payment_ids.filtered(lambda p: p.state == "posted" and p.id != rec.id)
            already_paid = sum(posted.mapped("paid_amount"))
            rec.remaining_amount = max(net - already_paid - rec.paid_amount, 0.0)
            rec.payment_status = "paid" if net > 0 and already_paid + rec.paid_amount >= net else "partial"

    @api.onchange("discount_percent")
    def _onchange_discount_percent(self):
        for rec in self:
            net = rec.total_amount * (1 - min(max(rec.discount_percent, 0.0), 100.0) / 100.0)
            posted = rec.booking_id.payment_ids.filtered(lambda p: p.state == "posted")
            paid_before = sum(posted.mapped("paid_amount"))
            rec.paid_amount = max(net - paid_before, 0.0)

    @api.constrains("discount_percent", "paid_amount", "total_amount")
    def _check_payment_values(self):
        for rec in self:
            if rec.discount_percent < 0 or rec.discount_percent > 100:
                raise ValidationError(_("Discount must be between 0 and 100 percent."))
            if rec.paid_amount <= 0:
                raise ValidationError(_("Paid amount must be greater than zero."))
            if rec.paid_amount > rec.discounted_price:
                raise ValidationError(_("Paid amount cannot exceed the discounted price."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.booking_id.state not in ("confirmed", "done"):
                raise UserError(_("Payment can only be recorded for a confirmed or completed booking."))
        return records

    def action_register_payment(self):
        self.ensure_one()
        if self.state == "posted":
            raise UserError(_("This payment has already been registered."))
        if self.booking_id.state not in ("confirmed", "done"):
            raise UserError(_("Payment can only be registered for confirmed or completed bookings."))

        posted_payments = self.booking_id.payment_ids.filtered(lambda payment: payment.state == "posted")
        paid_before = sum(posted_payments.mapped("paid_amount"))
        previous_target = posted_payments[-1].discounted_price if posted_payments else self.total_amount
        balance_before = max(previous_target - paid_before, 0.0)
        if balance_before <= 0:
            raise UserError(_("This booking is already fully paid."))

        if self.journal_id.type not in ("cash", "bank"):
            raise ValidationError(_("Select a Cash or Bank journal."))
        if self.paid_amount <= 0 or self.paid_amount > balance_before:
            raise ValidationError(_("Paid amount must be greater than zero and cannot exceed the outstanding balance (%s).") % balance_before)

        # If requested, treat the cumulative amount received as the final
        # discounted price and recompute the discount accordingly.
        if self.payment_action == "mark_paid":
            cumulative_paid = paid_before + self.paid_amount
            if self.total_amount:
                self.discount_percent = min(max((1.0 - cumulative_paid / self.total_amount) * 100.0, 0.0), 100.0)
            # Computed amount fields are refreshed from discount_percent.
        else:
            # Keep the existing discount and leave the unpaid balance open.
            pass

        method_line = self.env["account.payment.method.line"].search([
            ("journal_id", "=", self.journal_id.id),
            ("payment_method_id.payment_type", "=", "inbound"),
        ], limit=1)
        if not method_line:
            raise UserError(_("The selected journal has no inbound payment method configured."))

        payment = self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.customer_id.id,
            "amount": self.paid_amount,
            "currency_id": self.currency_id.id,
            "date": self.date,
            "journal_id": self.journal_id.id,
            "payment_method_line_id": method_line.id,
            "memo": self.booking_id.name,
        })
        payment.action_post()
        self.write({"state": "posted", "account_payment_id": payment.id})
        return {"type": "ir.actions.act_window_close"}
