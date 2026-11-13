from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    cinema_id = fields.Many2one(
        "cinema.cinema",
        string="Cinema",
        help="The cinema whose showtimes this point of sale sells.",
    )
