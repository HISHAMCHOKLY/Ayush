from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TreatmentBooking(models.Model):
    _inherit = "treatment.booking"

    booking_type = fields.Selection([("normal", "Normal Booking"), ("plan", "Treatment Plan")], string="Booking Type", default="normal", required=True)
    plan_purchase_id = fields.Many2one("treatment.plan.purchase", string="Patient Plan", ondelete="restrict", copy=False)
    plan_member_id = fields.Many2one("res.partner", string="Plan Member", ondelete="restrict", copy=False)
    # Patients receiving treatment under a couple/family plan. The purchasing
    # customer remains customer_id; patient_ids can contain other eligible members.
    patient_ids = fields.Many2many(
        "res.partner",
        "treatment_booking_patient_rel",
        "booking_id",
        "partner_id",
        string="Patients",
        domain=[("is_patient", "=", True)],
        copy=False,
    )
    eligible_member_ids = fields.Many2many(
        related="plan_purchase_id.member_ids",
        string="Eligible Plan Members",
        readonly=True,
    )
    plan_pack_type = fields.Selection(
        related="plan_purchase_id.plan_id.pack_type",
        string="Plan Type",
        readonly=True,
    )
    plan_covered = fields.Boolean(string="Covered by Plan", default=False, copy=False)

    @api.depends("booking_type", "payment_ids.state", "payment_ids.paid_amount", "payment_ids.discounted_price", "amount_total")
    def _compute_payment_status(self):
        super()._compute_payment_status()
        for rec in self:
            if rec.booking_type == "plan":
                rec.payment_status = "paid"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("booking_type") == "plan" and vals.get("plan_purchase_id") and not vals.get("therapist_ids"):
                purchase = self.env["treatment.plan.purchase"].browse(vals["plan_purchase_id"])
                if purchase.preferred_therapist_ids:
                    vals["therapist_ids"] = [(6, 0, purchase.preferred_therapist_ids.ids)]
        # The form makes customer_id readonly after a plan is selected.
        # Always persist the purchaser server-side so readonly/onchange client
        # behavior cannot cause the required customer_id to be missing.
        Purchase = self.env["treatment.plan.purchase"]
        for vals in vals_list:
            if vals.get("plan_purchase_id") and vals.get("booking_type", "normal") == "normal":
                vals["booking_type"] = "plan"
            if vals.get("booking_type") == "plan":
                purchase = Purchase.browse(vals.get("plan_purchase_id")).exists()
                if purchase:
                    vals["customer_id"] = purchase.customer_id.id
                vals["amount_total"] = 0.0
        return super().create(vals_list)

    def write(self, vals):
        Purchase = self.env["treatment.plan.purchase"]
        # Process each plan booking individually so multi-record writes never
        # accidentally assign one purchaser to another customer's booking.
        if "booking_type" in vals or "plan_purchase_id" in vals or any(rec.booking_type == "plan" for rec in self):
            for rec in self:
                rec_vals = dict(vals)
                target_type = rec_vals.get("booking_type", rec.booking_type)
                target_purchase_id = rec_vals.get("plan_purchase_id", rec.plan_purchase_id.id)
                if target_type == "plan":
                    purchase = Purchase.browse(target_purchase_id).exists()
                    if purchase:
                        rec_vals["customer_id"] = purchase.customer_id.id
                    rec_vals["amount_total"] = 0.0
                super(TreatmentBooking, rec).write(rec_vals)
            return True
        return super().write(vals)

    plan_treatment_type = fields.Selection(related="plan_purchase_id.treatment_type", string="Hands Type", readonly=True)

    @api.onchange("plan_purchase_id")
    def _onchange_plan_purchase_therapists(self):
        for rec in self:
            if rec.plan_purchase_id and rec.plan_purchase_id.preferred_therapist_ids:
                rec.therapist_ids = [(6, 0, rec.plan_purchase_id.preferred_therapist_ids.ids)]

    @api.onchange("service_id")
    def _onchange_plan_service_amount(self):
        for rec in self:
            if rec.booking_type == "plan":
                rec.amount_total = 0.0

    @api.onchange("booking_type")
    def _onchange_booking_type(self):
        for rec in self:
            if rec.booking_type == "normal":
                rec.plan_purchase_id = False
                rec.plan_member_id = False
                rec.patient_ids = [(5, 0, 0)]
                rec.plan_covered = False
            else:
                rec.amount_total = 0.0

    @api.onchange("plan_purchase_id")
    def _onchange_plan_purchase_id(self):
        for rec in self:
            rec.patient_ids = [(5, 0, 0)]
            if rec.plan_purchase_id:
                purchase = rec.plan_purchase_id
                # Customer always represents the purchaser of the plan.
                rec.customer_id = purchase.customer_id
                rec.plan_member_id = False
                rec.plan_covered = True
                rec.amount_total = 0.0
                allowed_lines = purchase.plan_id.line_ids.filtered(lambda line: line.quantity > 0)
                if rec.service_id not in allowed_lines.mapped("service_id") and allowed_lines:
                    rec.service_id = allowed_lines[0].service_id
                if rec.service_id:
                    rec.service_ids = [(6, 0, rec.service_id.ids)]

    # Do not modify patient_ids from an onchange handler. Odoo's many2many
    # selection is already restricted by the field domain, and rewriting the
    # value during onchange can clear the user's freshly selected tags.
    # patient_ids is cleared only when the plan itself changes, in
    # _onchange_plan_purchase_id; server-side constraints validate eligibility.

    @api.onchange("customer_id")
    def _onchange_customer_plan_member(self):
        for rec in self:
            if rec.booking_type == "plan" and rec.plan_purchase_id:
                # Keep the purchaser selected on the plan; patients are selected separately.
                if rec.customer_id != rec.plan_purchase_id.customer_id:
                    rec.customer_id = rec.plan_purchase_id.customer_id
                rec.amount_total = 0.0

    @api.constrains("booking_type", "plan_purchase_id", "patient_ids", "customer_id", "service_id", "therapist_ids", "state")
    def _check_plan_booking(self):
        for rec in self:
            if rec.booking_type == "normal":
                continue
            purchase = rec.plan_purchase_id
            if not purchase:
                raise ValidationError(_("Select a treatment plan for a plan booking."))
            if rec.customer_id != purchase.customer_id:
                raise ValidationError(_("The patient on the booking must match the patient who purchased this plan."))
            if purchase.plan_id.pack_type in ("couple", "family") and not rec.patient_ids:
                raise ValidationError(_("Select at least one eligible patient for this couple/family plan booking."))
            if rec.patient_ids - purchase.member_ids:
                raise ValidationError(_("All selected patients must be eligible members of this treatment plan."))
            if rec.service_id not in purchase.plan_id.line_ids.mapped("service_id"):
                raise ValidationError(_("The selected service is not included in this treatment plan."))
            if purchase.state != "active":
                raise ValidationError(_("Only active treatment plans can be used for bookings."))
            if purchase.expiry_date and purchase.expiry_date < fields.Date.context_today(rec):
                raise ValidationError(_("This treatment plan has expired."))
            required_therapists = 2 if purchase.plan_id.treatment_type == "four_handed" else 1
            if len(rec.therapist_ids) != required_therapists:
                raise ValidationError(_("This plan requires exactly %s therapist(s) for each treatment.") % required_therapists)
            if rec.state != "cancelled":
                if purchase.available_sessions <= 0 and rec.state != "done":
                    raise ValidationError(_("No paid treatment sessions remain on this plan. Register a plan payment before booking another treatment."))
                line = purchase.plan_id.line_ids.filtered(lambda l: l.service_id == rec.service_id)[:1]
                done_count = len(purchase.booking_ids.filtered(lambda b: b.state == "done" and b.service_id == rec.service_id and b.id != rec.id))
                reserved_count = len(purchase.booking_ids.filtered(lambda b: b.state not in ("cancelled", "done") and b.service_id == rec.service_id and b.id != rec.id))
                if line and done_count + reserved_count >= line.quantity:
                    raise ValidationError(_("The plan's included quantity for %s has already been used or reserved.") % rec.service_id.display_name)

    def action_mark_done(self):
        for rec in self:
            if rec.booking_type == "plan" and rec.plan_purchase_id:
                rec.amount_total = 0.0
            if rec.plan_purchase_id:
                purchase = rec.plan_purchase_id
                if purchase.state != "active":
                    raise UserError(_("The treatment plan is not active."))
                if purchase.expiry_date and purchase.expiry_date < fields.Date.context_today(rec):
                    raise UserError(_("The treatment plan has expired."))
                if purchase.available_sessions <= 0:
                    raise UserError(_("No paid treatment sessions remain on this plan."))
        return super().action_mark_done()
