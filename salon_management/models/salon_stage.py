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
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalonStage(models.Model):
    """Creates 'salon_stage' to creates new stages dynamically"""
    _name = 'salon.stage'
    _order = 'sequence'
    _description = 'Salon Stage'

    name = fields.Char(string="Name", required=True, translate=True,
                       help="Name of the stages")
    sequence = fields.Integer('Sequence', default=1,
                              help="Used to order stages. Lower is first.")
    color = fields.Integer('Color')
    is_complete_state = fields.Boolean(string="Is Complete State", copy=False,
                                       help="If enabled, this stage will be "
                                            "considered as the completed stage.")

    @api.constrains('is_complete_state')
    def _check_complete_state(self):
        """Constraint to ensure only one stage is marked as complete."""
        for record in self:
            if record.is_complete_state:
                complete_stages = self.search([
                    ('is_complete_state', '=', True),
                    ('id', '!=', record.id)
                ])
                if complete_stages:
                    raise ValidationError(_(
                        "Only one stage can be marked as the complete state. "
                        "The stage '%s' is already marked.") %
                                          complete_stages[0].name)
