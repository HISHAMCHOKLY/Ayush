from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TreatmentService(models.Model):
    _name = "treatment.service"
    _description = "Treatment Service"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    duration_minutes = fields.Integer(string="Treatment Duration (minutes)", required=True, default=75)
    cleaning_minutes = fields.Integer(string="Cleaning Buffer (minutes)", default=10)
    price = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id, required=True)
    description = fields.Text()
    consumable_line_ids = fields.One2many("treatment.service.consumable", "service_id", string="Required Stock Products")

    @api.constrains("duration_minutes", "cleaning_minutes")
    def _check_durations(self):
        for rec in self:
            if rec.duration_minutes <= 0 or rec.cleaning_minutes < 0:
                raise ValidationError(_("Treatment duration must be positive and cleaning time cannot be negative."))


class TreatmentServiceConsumable(models.Model):
    _name = "treatment.service.consumable"
    _description = "Treatment Service Stock Requirement"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    service_id = fields.Many2one("treatment.service", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True, domain=[("is_storable", "=", True)], string="Storable Product")
    quantity = fields.Float(required=True, default=1.0)
    product_uom_id = fields.Many2one("uom.uom", related="product_id.uom_id", readonly=True, string="Unit of Measure")

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("Required product quantity must be greater than zero."))
