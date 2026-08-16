from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class ReservationCase(TransactionCase):
    """Fixtures shared by all room reservation tests.

    Data is created in setUpClass because TransactionCase rolls every test
    method back to a savepoint, so the records are rebuilt for free.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        equipment = cls.env["booking.room.equipment"]
        cls.projector = equipment.create({"name": "Projector"})
        cls.whiteboard = equipment.create({"name": "Whiteboard"})

        rooms = cls.env["booking.room"]
        cls.small_room = rooms.create(
            {
                "name": "Room South",
                "capacity": 4,
                "equipment_ids": [(6, 0, cls.whiteboard.ids)],
            }
        )
        cls.large_room = rooms.create(
            {
                "name": "Room North",
                "capacity": 20,
                "equipment_ids": [(6, 0, (cls.projector | cls.whiteboard).ids)],
            }
        )

        users = cls.env["res.users"]
        cls.employee = users.create(
            {
                "name": "Ellen Employee",
                "login": "ellen",
                "group_ids": [
                    (6, 0, [cls.env.ref("room_reservation.group_booking_user").id])
                ],
            }
        )
        cls.manager = users.create(
            {
                "name": "Manuel Manager",
                "login": "manuel",
                "group_ids": [
                    (6, 0, [cls.env.ref("room_reservation.group_booking_manager").id])
                ],
            }
        )

        # Every fixture starts tomorrow, so the "no booking in the past" rule
        # never interferes with tests that are about something else.
        cls.tomorrow = fields.Datetime.now() + timedelta(days=1)

    @classmethod
    def _vals(cls, **overrides):
        vals = {
            "room_id": cls.large_room.id,
            "start": cls.tomorrow,
            "stop": cls.tomorrow + timedelta(hours=1),
            "purpose": "Team sync",
            "attendee_count": 2,
        }
        vals.update(overrides)
        return vals

    def _create(self, **overrides):
        return self.env["booking.reservation"].create(self._vals(**overrides))
