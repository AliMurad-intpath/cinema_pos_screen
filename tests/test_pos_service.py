from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCinemaPosService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cinema = cls.env["cinema.cinema"].create({"name": "POS Cinema", "tz": "Asia/Baghdad"})
        hall = cls.env["cinema.hall"].create({"name": "P1", "cinema_id": cinema.id})
        cls.env["cinema.hall.generate.seats"].create(
            {"hall_id": hall.id, "rows": 2, "seats_per_row": 3}
        ).action_generate()
        movie = cls.env["cinema.movie"].create({"name": "POS Movie", "duration_minutes": 90})
        cls.showtime = cls.env["cinema.showtime"].create(
            {
                "movie_id": movie.id,
                "hall_id": hall.id,
                "start_datetime": fields.Datetime.now() + timedelta(hours=3),
                "base_price": 8000,
                "state": "published",
            }
        )
        cls.seats = hall.seat_ids.sorted(lambda s: (s.row_index, s.number))
        cls.Booking = cls.env["cinema.booking"]

    def test_hold_returns_ticket_lines_with_a_product(self):
        result = self.Booking.pos_hold(self.showtime.id, [{"seat_id": self.seats[0].id}])
        self.assertEqual(len(result["tickets"]), 1)
        ticket = result["tickets"][0]
        self.assertAlmostEqual(ticket["price"], 8000)
        self.assertTrue(ticket["product_tmpl_id"])
        booking = self.Booking.browse(result["booking_id"])
        self.assertEqual((booking.channel, booking.state), ("pos", "hold"))

    def test_release_frees_the_seat(self):
        result = self.Booking.pos_hold(self.showtime.id, [{"seat_id": self.seats[0].id}])
        self.Booking.pos_release(result["booking_id"])
        again = self.Booking.pos_hold(self.showtime.id, [{"seat_id": self.seats[0].id}])
        self.assertTrue(again["booking_id"])

    def test_cannot_hold_a_taken_seat(self):
        self.Booking.pos_hold(self.showtime.id, [{"seat_id": self.seats[0].id}])
        with self.assertRaises(UserError):
            self.Booking.pos_hold(self.showtime.id, [{"seat_id": self.seats[0].id}])

    def test_ticket_product_is_flagged(self):
        product = self.env.ref("cinema_pos_screen.product_cinema_ticket")
        self.assertTrue(product.is_cinema_ticket)
        self.assertTrue(product.available_in_pos)
