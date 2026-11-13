from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_cinema_ticket = fields.Boolean(
        string="Cinema Ticket",
        help="Tickets must be sold through the POS Movies screen so that a seat is reserved.",
    )
