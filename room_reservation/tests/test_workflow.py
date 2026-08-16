from datetime import timedelta

from odoo.exceptions import UserError

from .common import ReservationCase


class TestReservationWorkflow(ReservationCase):
    """Covers the state machine and the approval rules."""

    def _in_state(self, state, offset):
        """Create a reservation in ``state`` in its own half-hour slot.

        Each record needs a distinct period, otherwise the blocking states
        would collide with the overlap constraint.
        """
        start = self.tomorrow + timedelta(hours=offset)
        return self._create(
            state=state, start=start, stop=start + timedelta(minutes=30)
        )

    def test_every_transition_follows_the_map(self):
        """Walks all source/target combinations declared in _TRANSITIONS."""
        transitions = self.env["booking.reservation"]._TRANSITIONS
        combinations = [(s, t) for s in transitions for t in transitions]

        for offset, (source, target) in enumerate(combinations):
            with self.subTest(source=source, target=target):
                reservation = self._in_state(source, offset)

                if target in transitions[source]:
                    reservation._transition_to(target)
                    self.assertEqual(reservation.state, target)
                else:
                    with self.assertRaises(UserError):
                        reservation._transition_to(target)
                    self.assertEqual(reservation.state, source)

    def test_approving_records_who_and_when(self):
        reservation = self._create(state="to_approve").with_user(self.manager)

        reservation.action_approve()

        self.assertEqual(reservation.state, "confirmed")
        self.assertEqual(reservation.approver_id, self.manager)
        self.assertTrue(reservation.approval_date)

    def test_only_managers_may_approve(self):
        """Writing and approving are separate privileges."""
        reservation = self._create(state="to_approve")

        with self.assertRaises(UserError):
            reservation.with_user(self.employee).action_approve()

        self.assertEqual(reservation.state, "to_approve")

    def test_resetting_clears_the_approval_trail(self):
        reservation = self._create(state="to_approve")
        reservation.with_user(self.manager).action_approve()

        reservation.action_cancel()
        reservation.action_reset_to_draft()

        self.assertEqual(reservation.state, "draft")
        self.assertFalse(reservation.approver_id)
        self.assertFalse(reservation.approval_date)

    def test_submitting_schedules_an_activity_for_the_managers(self):
        reservation = self._create()

        reservation.action_submit()

        self.assertIn(self.manager, reservation.activity_ids.mapped("user_id"))

    def test_a_done_reservation_is_final(self):
        reservation = self._create(state="done")

        with self.assertRaises(UserError):
            reservation.action_cancel()
