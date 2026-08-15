from odoo import api, fields, models

STATES = [
    ("draft", "Draft"),
    ("to_approve", "To Approve"),
    ("confirmed", "Confirmed"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
]


class BookingReservation(models.Model):
    """A request to occupy a room for a given period of time."""

    _name = "booking.reservation"
    _description = "Room Reservation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start desc"

    name = fields.Char(
        default="/",
        copy=False,
        readonly=True,
        help="Reference assigned automatically when the reservation is created.",
    )
    room_id = fields.Many2one(
        comodel_name="booking.room",
        required=True,
        # Restrict rather than cascade: deleting a room must not silently
        # discard its booking history.
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Organizer",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    start = fields.Datetime(required=True, index=True, tracking=True)
    stop = fields.Datetime(required=True, tracking=True)
    duration = fields.Float(
        compute="_compute_duration",
        store=True,
        help="Length of the reservation in hours.",
    )
    attendee_count = fields.Integer(default=1)
    purpose = fields.Char(required=True)
    required_equipment_ids = fields.Many2many(
        comodel_name="booking.room.equipment",
        relation="booking_reservation_equipment_rel",
        column1="reservation_id",
        column2="equipment_id",
        string="Required Equipment",
    )
    state = fields.Selection(
        # Odoo leaves this parameter unannotated, so a static checker infers
        # its type from the sentinel default and flags the list.
        selection=STATES,  # type: ignore[arg-type]
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )
    approver_id = fields.Many2one(
        comodel_name="res.users",
        string="Approved By",
        readonly=True,
        copy=False,
    )
    approval_date = fields.Datetime(readonly=True, copy=False)

    _stop_after_start = models.Constraint(
        "CHECK(stop > start)",
        "A reservation must end after it starts.",
    )

    @api.depends("start", "stop")
    def _compute_duration(self):
        for reservation in self:
            if reservation.start and reservation.stop:
                delta = reservation.stop - reservation.start
                reservation.duration = delta.total_seconds() / 3600
            else:
                reservation.duration = 0
