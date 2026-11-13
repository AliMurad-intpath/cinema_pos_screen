from odoo import api, fields, models
from odoo.exceptions import UserError


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    cinema_booking_ref = fields.Integer(copy=False, index=True, help="ID of the cinema.booking holding this seat.")
    cinema_line_ref = fields.Integer(copy=False, help="ID of the cinema.booking.line (the seat).")
    cinema_ticket_barcode = fields.Char(copy=False, help="Filled once the order is paid.")

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields_list = super()._load_pos_data_fields(*args, **kwargs)
        # An empty list means "load every field": nothing to add in that case.
        if fields_list:
            fields_list = list(fields_list) + [
                "cinema_booking_ref",
                "cinema_line_ref",
                "cinema_ticket_barcode",
            ]
        return fields_list


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        res = super().action_pos_order_paid()
        self._cinema_sync_bookings()
        return res

    def _cinema_sync_bookings(self):
        """Confirm the bookings paid by this order and refund the ones it returns."""
        Booking = self.env["cinema.booking"].sudo()
        BookingLine = self.env["cinema.booking.line"].sudo()
        for order in self:
            ticket_lines = order.lines.filtered(
                lambda l: l.product_id.product_tmpl_id.is_cinema_ticket and l.qty > 0
            )
            if ticket_lines.filtered(lambda l: not l.cinema_booking_ref):
                raise UserError(
                    self.env._(
                        "A cinema ticket was sold without a seat. Remove it and sell tickets "
                        "from the Movies screen."
                    )
                )
            sales = order.lines.filtered(lambda l: l.cinema_booking_ref and l.qty > 0)
            bookings = Booking.browse(sorted(set(sales.mapped("cinema_booking_ref")))).exists()
            for booking in bookings:
                booking.action_confirm(payment_reference=order.pos_reference or order.name)
                booking.pos_order_id = order
            for line in sales:
                booking_line = BookingLine.browse(line.cinema_line_ref).exists()
                if booking_line:
                    line.cinema_ticket_barcode = booking_line.barcode
            # Returned tickets: release the seat of the original sale line.
            for line in order.lines.filtered(lambda l: l.qty < 0 and l.refunded_orderline_id):
                booking_line = BookingLine.browse(line.refunded_orderline_id.cinema_line_ref).exists()
                if booking_line:
                    booking_line.booking_id._refund_lines(booking_line)
