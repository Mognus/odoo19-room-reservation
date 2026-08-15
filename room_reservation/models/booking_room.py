from odoo import api, fields, models


class BookingRoom(models.Model):
    """A room that can be reserved for a given period of time."""

    _name = "booking.room"
    _description = "Bookable Room"
    _order = "name"

    name = fields.Char(required=True)
    location = fields.Char(help="Building or floor where the room is located.")
    capacity = fields.Integer(
        required=True,
        default=1,
        help="Maximum number of attendees the room can hold.",
    )
    description = fields.Text()
    # Picked up by the calendar view to colour reservations per room.
    color = fields.Integer()
    active = fields.Boolean(default=True)

    equipment_ids = fields.Many2many(
        comodel_name="booking.room.equipment",
        relation="booking_room_equipment_rel",
        column1="room_id",
        column2="equipment_id",
        string="Equipment",
    )

    reservation_ids = fields.One2many(
        comodel_name="booking.reservation",
        inverse_name="room_id",
        string="Reservations",
    )
    reservation_count = fields.Integer(compute="_compute_reservation_count")

    _capacity_positive = models.Constraint(
        "CHECK(capacity > 0)",
        "Room capacity must be greater than zero.",
    )

    @api.depends("reservation_ids")
    def _compute_reservation_count(self):
        # read_group aggregates in SQL instead of loading every reservation.
        counts = dict(
            self.env["booking.reservation"]._read_group(
                domain=[("room_id", "in", self.ids)],
                groupby=["room_id"],
                aggregates=["__count"],
            )
        )
        for room in self:
            room.reservation_count = counts.get(room, 0)
