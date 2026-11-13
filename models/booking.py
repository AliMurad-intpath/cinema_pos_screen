from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError


class CinemaBooking(models.Model):
    _inherit = "cinema.booking"

    pos_order_id = fields.Many2one("pos.order", string="POS Order", copy=False, index="btree_not_null")

    # ------------------------------------------------------------------
    # Server side of the POS "Movies" screen
    # ------------------------------------------------------------------
    @api.model
    def pos_get_screen_data(self, config_id, date=None):
        """Showtimes of the POS cinema for one business day, grouped by movie."""
        config = self.env["pos.config"].browse(config_id).exists()
        cinema = config.cinema_id
        if not cinema:
            raise UserError(
                self.env._(
                    "No cinema is assigned to this point of sale. "
                    "Set it under Cinema > Configuration > POS Terminals."
                )
            )
        tz = pytz.timezone(cinema.tz or "UTC")
        today = (datetime.now(tz) - timedelta(hours=cinema.business_day_cutoff_hour or 0)).date()
        if date:
            try:
                business_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                raise UserError(self.env._("Invalid date."))
        else:
            business_date = today

        Showtime = self.env["cinema.showtime"]
        showtimes = Showtime.search(
            Showtime._sellable_domain(cinema_id=cinema.id, business_date=business_date),
            order="start_datetime",
        )
        movies = {}
        for showtime in showtimes:
            movie = showtime.movie_id
            entry = movies.setdefault(
                movie.id,
                {
                    "id": movie.id,
                    "title": movie.name,
                    "rating": dict(movie._fields["rating"].selection).get(movie.rating) if movie.rating else None,
                    "duration_minutes": movie.duration_minutes,
                    "has_poster": bool(movie.poster_256),
                    "showtimes": [],
                },
            )
            entry["showtimes"].append(
                {
                    "id": showtime.id,
                    "time": (showtime.start_local or "")[-5:],
                    "hall": showtime.hall_id.name,
                    "format": dict(showtime.hall_id._fields["hall_format"].selection).get(
                        showtime.hall_id.hall_format
                    ),
                    "audio_language": showtime.audio_language or "",
                    "available_count": showtime.available_count,
                    "availability": showtime.availability,
                    "price_from": showtime.base_price,
                }
            )

        default_product = self.env.ref("cinema_pos_screen.product_cinema_ticket", raise_if_not_found=False)
        ticket_types = [
            {
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "price_factor": t.price_factor,
                "product_tmpl_id": t.product_id.product_tmpl_id.id or default_product.id,
            }
            for t in self.env["cinema.ticket.type"].search([])
        ]
        return {
            "cinema": {"id": cinema.id, "name": cinema.name},
            "today": str(today),
            "date": str(business_date),
            "movies": list(movies.values()),
            "ticket_types": ticket_types,
        }

    @api.model
    def pos_get_seatmap(self, showtime_id):
        showtime = self.env["cinema.showtime"].browse(showtime_id).exists()
        if not showtime or showtime.state != "published":
            raise UserError(self.env._("This showtime is not on sale."))
        return showtime.get_seatmap()

    @api.model
    def pos_hold(self, showtime_id, seats, config_id=None):
        """Reserve seats for the order being built at the counter."""
        showtime = self.env["cinema.showtime"].browse(showtime_id).exists()
        config = self.env["pos.config"].browse(config_id).exists() if config_id else None
        if showtime and config and config.cinema_id and showtime.cinema_id != config.cinema_id:
            raise UserError(self.env._("This showtime belongs to another cinema."))
        minutes = int(self.env["ir.config_parameter"].sudo().get_param("cinema.pos_hold_minutes", 15))
        booking = self.create_hold(showtime_id, seats, channel="pos", hold_minutes=minutes)
        default_product = self.env.ref("cinema_pos_screen.product_cinema_ticket", raise_if_not_found=False)
        return {
            "booking_id": booking.id,
            "hold_expires_at": booking.hold_expires_at and booking.hold_expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "label": "%s · %s" % (booking.movie_id.name, showtime.start_local),
            "tickets": [
                {
                    "line_id": line.id,
                    "seat": line.seat_id.name,
                    "ticket_type": line.ticket_type_id.name,
                    "price": line.price,
                    "product_tmpl_id": line.ticket_type_id.product_id.product_tmpl_id.id or default_product.id,
                }
                for line in booking.line_ids
            ],
        }

    @api.model
    def pos_release(self, booking_id):
        """Free the seats of a hold that was not added to the order."""
        booking = self.browse(booking_id).exists()
        if booking and booking.channel == "pos" and booking.state == "hold":
            booking.action_cancel(reason="Released from POS")
        return True
