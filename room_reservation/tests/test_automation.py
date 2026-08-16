from datetime import timedelta

from .common import ReservationCase


class TestReservationAutomation(ReservationCase):
    """Covers the sequence and the scheduled expiry of pending requests."""

    def _set_expiry_hours(self, hours):
        """Move the rule instead of the clock.

        Shifting the threshold keeps the test independent of the current time,
        which is the least reliable input a test can have.
        """
        self.env["ir.config_parameter"].sudo().set_param(
            "room_reservation.pending_expiry_hours", str(hours)
        )

    def test_a_reference_is_drawn_from_the_sequence(self):
        reservation = self._create()

        self.assertTrue(reservation.name.startswith("BOOK/"))

    def test_references_are_handed_out_in_order(self):
        later = self.tomorrow + timedelta(days=1)
        first = self._create()
        second = self._create(start=later, stop=later + timedelta(hours=1))

        self.assertGreater(second.name, first.name)

    def test_the_cron_cancels_requests_close_to_their_start(self):
        self._set_expiry_hours(100000)
        reservation = self._create(state="to_approve")

        self.env["booking.reservation"]._cron_expire_pending()

        self.assertEqual(reservation.state, "cancelled")

    def test_the_cron_keeps_requests_outside_the_window(self):
        self._set_expiry_hours(0)
        reservation = self._create(state="to_approve")

        self.env["booking.reservation"]._cron_expire_pending()

        self.assertEqual(reservation.state, "to_approve")

    def test_the_cron_leaves_approved_reservations_alone(self):
        self._set_expiry_hours(100000)
        reservation = self._create(state="confirmed")

        self.env["booking.reservation"]._cron_expire_pending()

        self.assertEqual(reservation.state, "confirmed")

    def test_the_cron_explains_itself_and_cleans_up(self):
        self._set_expiry_hours(100000)
        reservation = self._create()
        reservation.action_submit()
        self.assertTrue(reservation.activity_ids)

        self.env["booking.reservation"]._cron_expire_pending()

        self.assertEqual(reservation.state, "cancelled")
        self.assertFalse(reservation.activity_ids)
        self.assertTrue(
            reservation.message_ids.filtered(
                lambda message: "not approved in time" in (message.body or "")
            )
        )
