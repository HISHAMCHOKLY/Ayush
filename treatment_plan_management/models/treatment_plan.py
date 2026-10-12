from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TreatmentPlan(models.Model):
    _name = "treatment.plan"
    _description = "Treatment Plan"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id)
    price = fields.Monetary(required=True, currency_field="currency_id")
    validity_months = fields.Integer(required=True, default=6)
    pack_type = fields.Selection([
        ("individual", "Individual"),
        ("couple", "Couple Pack"),
        ("family", "Family Pack"),
    ], required=True, default="individual")
    treatment_type = fields.Selection([
        ("two_handed", "2-Handed (1 Therapist)"),
        ("four_handed", "4-Handed (2 Therapists)"),
    ], required=True, default="two_handed")
    member_limit = fields.Integer(compute="_compute_member_limit", store=True)
    line_ids = fields.One2many("treatment.plan.line", "plan_id", string="Included Services", copy=True)
    total_sessions = fields.Integer(compute="_compute_totals", store=True)
    per_session_price = fields.Monetary(compute="_compute_totals", store=True, currency_field="currency_id")
    purchase_count = fields.Integer(compute="_compute_purchase_count")

    @api.depends("pack_type")
    def _compute_member_limit(self):
        for rec in self:
            rec.member_limit = {"individual": 1, "couple": 2, "family": 4}.get(rec.pack_type, 1)

    @api.depends("line_ids.quantity", "price")
    def _compute_totals(self):
        for rec in self:
            count = sum(rec.line_ids.mapped("quantity"))
            rec.total_sessions = count
            rec.per_session_price = rec.price / count if count else 0.0

    def _compute_purchase_count(self):
        for rec in self:
            rec.purchase_count = self.env["treatment.plan.purchase"].search_count([("plan_id", "=", rec.id)])

    @api.constrains("price", "validity_months", "line_ids")
    def _check_plan(self):
        for rec in self:
            if rec.price <= 0:
                raise ValidationError(_("Plan price must be greater than zero."))
            if rec.validity_months <= 0:
                raise ValidationError(_("Plan validity must be at least one month."))
            if not rec.line_ids or rec.total_sessions <= 0:
                raise ValidationError(_("Add at least one service with a positive quantity."))


class TreatmentPlanLine(models.Model):
    _name = "treatment.plan.line"
    _description = "Treatment Plan Service"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    plan_id = fields.Many2one("treatment.plan", required=True, ondelete="cascade")
    service_id = fields.Many2one("treatment.service", required=True, ondelete="restrict")
    quantity = fields.Integer(required=True, default=1)
    unit_price = fields.Monetary(related="plan_id.per_session_price", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(related="plan_id.currency_id", store=True)

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("Service quantity must be at least one."))


class TreatmentPlanPurchase(models.Model):
    _name = "treatment.plan.purchase"
    _description = "Patient Treatment Plan"
    _order = "purchase_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(default="New", required=True, copy=False)
    plan_id = fields.Many2one("treatment.plan", required=True, ondelete="restrict")
    customer_id = fields.Many2one("res.partner", string="Patient", required=True, ondelete="restrict", domain=[("is_patient", "=", True)])
    member_ids = fields.Many2many("res.partner", "treatment_plan_purchase_member_rel",
                                  "purchase_id", "partner_id", string="Eligible Patients", domain=[("is_patient", "=", True)])
    preferred_therapist_ids = fields.Many2many("hr.employee", "treatment_plan_purchase_therapist_rel", "purchase_id", "employee_id", string="Preferred Therapist(s)", domain=[("active", "=", True)])
    plan_pack_type = fields.Selection(related="plan_id.pack_type", string="Plan Type", readonly=True)
    treatment_type = fields.Selection(related="plan_id.treatment_type", string="Treatment Type", readonly=True)
    purchase_date = fields.Date(required=True, default=fields.Date.context_today)
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    expiry_date = fields.Date(compute="_compute_expiry_date", store=True)
    validity_months = fields.Integer(related="plan_id.validity_months", store=True, readonly=True)
    currency_id = fields.Many2one(related="plan_id.currency_id", store=True)
    plan_price = fields.Monetary(related="plan_id.price", currency_field="currency_id", readonly=True)
    total_sessions = fields.Integer(related="plan_id.total_sessions", readonly=True)
    per_session_price = fields.Monetary(related="plan_id.per_session_price", currency_field="currency_id", readonly=True)
    amount_paid = fields.Monetary(compute="_compute_payment_totals", store=True, currency_field="currency_id")
    remaining_amount = fields.Monetary(compute="_compute_payment_totals", store=True, currency_field="currency_id")
    paid_sessions = fields.Integer(compute="_compute_entitlements", store=True)
    used_sessions = fields.Integer(compute="_compute_entitlements", store=True)
    available_sessions = fields.Integer(compute="_compute_entitlements", store=True)
    state = fields.Selection([
        ("draft", "Draft"), ("active", "Active"), ("expired", "Expired"), ("cancelled", "Cancelled")
    ], default="draft", required=True)
    payment_line_ids = fields.One2many("treatment.plan.payment", "purchase_id", string="Payments")
    booking_ids = fields.One2many("treatment.booking", "plan_purchase_id", string="Bookings")
    booking_count = fields.Integer(compute="_compute_counts")
    payment_count = fields.Integer(compute="_compute_counts")

    @api.onchange("customer_id")
    def _onchange_customer_add_member(self):
        for rec in self:
            if rec.customer_id and rec.customer_id not in rec.member_ids:
                rec.member_ids = [(4, rec.customer_id.id)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("treatment.plan.purchase") or "PLAN0001"
            plan = self.env["treatment.plan"].browse(vals.get("plan_id"))
            customer_id = vals.get("customer_id")
            if plan and customer_id:
                commands = vals.get("member_ids") or []
                member_ids = set()
                for command in commands:
                    if isinstance(command, (list, tuple)) and command:
                        if command[0] == 6:
                            member_ids.update(command[2])
                        elif command[0] == 4:
                            member_ids.add(command[1])
                member_ids.add(customer_id)
                vals["member_ids"] = [(6, 0, list(member_ids))]
        records = super().create(vals_list)
        for rec in records:
            if rec.name and rec.customer_id and " - " not in rec.name:
                rec.name = "%s - %s" % (rec.name, rec.customer_id.name)
        records._check_members()
        return records

    @api.depends("start_date", "validity_months")
    def _compute_expiry_date(self):
        for rec in self:
            rec.expiry_date = rec.start_date + relativedelta(months=rec.validity_months) if rec.start_date and rec.validity_months else False

    @api.depends("payment_line_ids.state", "payment_line_ids.amount")
    def _compute_payment_totals(self):
        for rec in self:
            paid = sum(rec.payment_line_ids.filtered(lambda p: p.state == "posted").mapped("amount"))
            rec.amount_paid = paid
            rec.remaining_amount = max(rec.plan_price - paid, 0.0)

    @api.depends("payment_line_ids.state", "payment_line_ids.amount", "booking_ids.state", "plan_id.total_sessions", "per_session_price")
    def _compute_entitlements(self):
        for rec in self:
            paid = sum(rec.payment_line_ids.filtered(lambda p: p.state == "posted").mapped("amount"))
            unit = rec.per_session_price
            rec.paid_sessions = min(rec.total_sessions, int((paid + 1e-6) / unit)) if unit else 0
            rec.used_sessions = len(rec.booking_ids.filtered(lambda b: b.state == "done" and b.plan_purchase_id == rec))
            rec.available_sessions = max(rec.paid_sessions - rec.used_sessions, 0)

    def _compute_counts(self):
        for rec in self:
            rec.booking_count = len(rec.booking_ids)
            rec.payment_count = len(rec.payment_line_ids.filtered(lambda p: p.state == "posted"))

    def write(self, vals):
        result = super().write(vals)
        if "customer_id" in vals:
            for rec in self:
                if rec.name and " - " in rec.name:
                    prefix = rec.name.split(" - ", 1)[0]
                    rec.name = "%s - %s" % (prefix, rec.customer_id.name)
        return result

    @api.constrains("member_ids", "customer_id", "plan_id")
    def _check_members(self):
        for rec in self:
            if rec.customer_id and rec.customer_id not in rec.member_ids:
                raise ValidationError(_("The purchasing customer must be included in eligible members."))
            if len(rec.member_ids) > rec.plan_id.member_limit:
                raise ValidationError(_("This %s supports at most %s member(s).") % (rec.plan_id.pack_type, rec.plan_id.member_limit))

    def action_activate(self):
        for rec in self:
            if rec.amount_paid <= 0:
                raise UserError(_("Register a payment before activating the plan."))
            if rec.state in ("cancelled", "expired"):
                raise UserError(_("A cancelled or expired plan cannot be activated."))
            rec.state = "active"
        return True

    def action_refresh_expiry(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state == "active" and rec.expiry_date and rec.expiry_date < today:
                rec.state = "expired"
        return True

    def action_open_payment(self):
        self.ensure_one()
        if self.state in ("expired", "cancelled"):
            raise UserError(_("Cannot take payment against an expired or cancelled plan."))
        return {
            "type": "ir.actions.act_window", "name": _("Plan Payment"),
            "res_model": "treatment.plan.payment", "view_mode": "form", "target": "new",
            "context": {"default_purchase_id": self.id, "default_amount": self.remaining_amount or 0.0,
                        "default_journal_id": self.env["account.journal"].search([
                            ("type", "in", ("cash", "bank")), ("company_id", "=", self.env.company.id)
                        ], limit=1).id},
        }

    def action_view_bookings(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Plan Bookings"),
                "res_model": "treatment.booking", "view_mode": "list,form",
                "domain": [("plan_purchase_id", "=", self.id)]}

    def action_view_payments(self):
        self.ensure_one()
        ids = self.payment_line_ids.filtered(lambda p: p.state == "posted" and p.account_payment_id).mapped("account_payment_id").ids
        return {"type": "ir.actions.act_window", "name": _("Patient Payments"),
                "res_model": "account.payment", "view_mode": "list,form",
                "domain": [("id", "in", ids)], "context": {"create": False}}

    @api.constrains("start_date", "expiry_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.expiry_date and rec.expiry_date < rec.start_date:
                raise ValidationError(_("Expiry date must be after the start date."))


class TreatmentPlanPayment(models.Model):
    _name = "treatment.plan.payment"
    _description = "Treatment Plan Payment"
    _order = "date desc, id desc"

    purchase_id = fields.Many2one("treatment.plan.purchase", required=True, ondelete="cascade")
    customer_id = fields.Many2one(related="purchase_id.customer_id", string="Patient", store=True, readonly=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one("account.journal", required=True, domain="[('type', 'in', ['cash', 'bank'])]")
    currency_id = fields.Many2one(related="purchase_id.currency_id", store=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    state = fields.Selection([("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Cancelled")], default="draft", required=True)
    account_payment_id = fields.Many2one("account.payment", readonly=True, copy=False)

    def action_register_payment(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("This plan payment has already been processed."))
        if self.amount <= 0:
            raise ValidationError(_("Payment amount must be greater than zero."))
        purchase = self.purchase_id
        if purchase.amount_paid + self.amount > purchase.plan_price + 1e-6:
            raise ValidationError(_("Payment cannot exceed the remaining plan amount."))
        method_line = self.env["account.payment.method.line"].search([
            ("journal_id", "=", self.journal_id.id),
            ("payment_method_id.payment_type", "=", "inbound"),
        ], limit=1)
        if not method_line:
            raise UserError(_("The selected journal has no inbound payment method configured."))
        payment = self.env["account.payment"].create({
            "payment_type": "inbound", "partner_type": "customer",
            "partner_id": purchase.customer_id.id, "amount": self.amount,
            "currency_id": purchase.currency_id.id, "date": self.date,
            "journal_id": self.journal_id.id, "payment_method_line_id": method_line.id,
            "memo": purchase.name,
        })
        payment.action_post()
        self.write({"state": "posted", "account_payment_id": payment.id})
        if purchase.state == "draft":
            purchase.state = "active"
        return {"type": "ir.actions.act_window_close"}
