from odoo.exceptions import AccessError

from .common import ReservationCase


class TestReservationSecurity(ReservationCase):
    """Verifies the access rights and record rules from the user's point of view."""

    def setUp(self):
        super().setUp()
        # Both stay in draft, which never blocks a room, so the two records may
        # share a period without tripping the overlap constraint.
        self.own_reservation = self._create(user_id=self.employee.id)
        self.foreign_reservation = self._create(user_id=self.manager.id)

    def test_a_user_sees_reservations_of_others(self):
        """Occupancy has to be transparent, otherwise planning is impossible."""
        visible = self.foreign_reservation.with_user(self.employee)

        self.assertEqual(visible.purpose, "Team sync")

    def test_a_user_cannot_change_a_foreign_reservation(self):
        with self.assertRaises(AccessError):
            self.foreign_reservation.with_user(self.employee).write(
                {"purpose": "Taken over"}
            )

    def test_a_user_can_change_their_own_reservation(self):
        own = self.own_reservation.with_user(self.employee)

        own.write({"purpose": "Retrospective"})

        self.assertEqual(own.purpose, "Retrospective")

    def test_a_manager_can_change_any_reservation(self):
        foreign = self.foreign_reservation.with_user(self.manager)

        foreign.write({"purpose": "Rescheduled by facility management"})

        self.assertEqual(foreign.purpose, "Rescheduled by facility management")

    def test_a_user_may_read_rooms(self):
        self.assertEqual(self.small_room.with_user(self.employee).capacity, 4)

    def test_a_user_may_not_create_rooms(self):
        """Denied one layer earlier than the record rules, by the access rights."""
        with self.assertRaises(AccessError):
            self.env["booking.room"].with_user(self.employee).create(
                {"name": "Unauthorised room", "capacity": 2}
            )

    def test_a_manager_may_create_rooms(self):
        room = (
            self.env["booking.room"]
            .with_user(self.manager)
            .create({"name": "Room West", "capacity": 6})
        )

        self.assertTrue(room.id)
