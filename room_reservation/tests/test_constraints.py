from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import ReservationCase


class TestReservationConstraints(ReservationCase):
    """Covers the business rules documented in the README."""

    def test_overlapping_reservation_is_rejected(self):
        self._create(state="confirmed")
        with self.assertRaises(ValidationError):
            self._create(
                state="confirmed",
                start=self.tomorrow + timedelta(minutes=30),
                stop=self.tomorrow + timedelta(hours=2),
            )

    def test_back_to_back_reservations_are_allowed(self):
        """Half-open intervals: a booking may start when the previous ends."""
        first = self._create(state="confirmed")
        second = self._create(
            state="confirmed",
            start=first.stop,
            stop=first.stop + timedelta(hours=1),
        )
        self.assertEqual(second.state, "confirmed")

    def test_cancelling_frees_the_room(self):
        blocking = self._create(state="confirmed")
        blocking.action_cancel()
        self.assertTrue(self._create(state="confirmed"))

    def test_draft_does_not_block_the_room(self):
        self._create()  # stays in draft
        self.assertTrue(self._create(state="confirmed"))

    def test_another_room_is_unaffected(self):
        self._create(state="confirmed")
        self.assertTrue(self._create(state="confirmed", room_id=self.small_room.id))

    def test_attendees_above_capacity_are_rejected(self):
        with self.assertRaises(ValidationError):
            self._create(room_id=self.small_room.id, attendee_count=5)

    def test_attendees_matching_capacity_are_accepted(self):
        reservation = self._create(room_id=self.small_room.id, attendee_count=4)
        self.assertEqual(reservation.attendee_count, 4)

    def test_capacity_warning_is_offered_while_editing(self):
        """The onchange only warns; _check_capacity is what actually binds."""
        draft = self.env["booking.reservation"].new(
            self._vals(room_id=self.small_room.id, attendee_count=99)
        )
        self.assertIn("warning", draft._onchange_attendee_count())

    def test_equipment_missing_in_the_room_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create(
                room_id=self.small_room.id,  # provides the whiteboard only
                required_equipment_ids=[(6, 0, self.projector.ids)],
            )

    def test_equipment_available_in_the_room_is_accepted(self):
        reservation = self._create(
            required_equipment_ids=[(6, 0, (self.projector | self.whiteboard).ids)]
        )
        self.assertEqual(len(reservation.required_equipment_ids), 2)

    def test_start_in_the_past_is_rejected(self):
        yesterday = fields.Datetime.now() - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self._create(start=yesterday, stop=yesterday + timedelta(hours=1))

    def test_a_reservation_stays_editable_once_it_has_started(self):
        """Time passing must not freeze a record against being cancelled."""
        reservation = self._create(state="confirmed")
        past_start = fields.Datetime.now() - timedelta(hours=2)
        # Bypass the ORM on purpose: the rule under test guards writes, so the
        # record cannot be moved into the past through it.
        self.env.cr.execute(
            "UPDATE booking_reservation SET start = %s, stop = %s WHERE id = %s",
            (past_start, past_start + timedelta(hours=1), reservation.id),
        )
        reservation.invalidate_recordset()

        reservation.action_cancel()

        self.assertEqual(reservation.state, "cancelled")

    def test_stop_before_start_is_rejected_by_the_database(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self._create(stop=self.tomorrow - timedelta(hours=1))

    def test_duration_is_computed_in_hours(self):
        reservation = self._create(stop=self.tomorrow + timedelta(hours=2, minutes=30))
        self.assertEqual(reservation.duration, 2.5)
