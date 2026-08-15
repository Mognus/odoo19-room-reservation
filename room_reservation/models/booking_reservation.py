from odoo import api, fields, models
from odoo.exceptions import ValidationError

STATES = [
    ("draft", "Draft"),
    ("to_approve", "To Approve"),
    ("confirmed", "Confirmed"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
]

# States that actually occupy the room. Drafts are not binding yet and
# cancellations release the room, so neither blocks another reservation.
BLOCKING_STATES = ("to_approve", "confirmed", "done")


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
        selection=STATES,
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
    _attendee_count_positive = models.Constraint(
        "CHECK(attendee_count > 0)",
        "A reservation needs at least one attendee.",
    )

    @api.depends("start", "stop")
    def _compute_duration(self):
        for reservation in self:
            if reservation.start and reservation.stop:
                delta = reservation.stop - reservation.start
                reservation.duration = delta.total_seconds() / 3600
            else:
                reservation.duration = 0

    @api.constrains("room_id", "start", "stop", "state")
    def _check_no_overlap(self):
        for reservation in self:
            if reservation.state not in BLOCKING_STATES:
                continue
            conflict = self.search(
                [
                    ("id", "!=", reservation.id),
                    ("room_id", "=", reservation.room_id.id),
                    ("state", "in", BLOCKING_STATES),
                    # Half-open intervals, so a reservation may start exactly
                    # when the previous one ends.
                    ("start", "<", reservation.stop),
                    ("stop", ">", reservation.start),
                ],
                limit=1,
            )
            if conflict:
                raise ValidationError(
                    self.env._(
                        "%(room)s is already booked from %(start)s to %(stop)s.",
                        room=reservation.room_id.display_name,
                        start=conflict.start,
                        stop=conflict.stop,
                    )
                )

    @api.constrains("attendee_count", "room_id")
    def _check_capacity(self):
        for reservation in self:
            if reservation.attendee_count > reservation.room_id.capacity:
                raise ValidationError(
                    self.env._(
                        "%(room)s holds %(capacity)s people, but %(requested)s are expected.",
                        room=reservation.room_id.display_name,
                        capacity=reservation.room_id.capacity,
                        requested=reservation.attendee_count,
                    )
                )

    @api.constrains("required_equipment_ids", "room_id")
    def _check_required_equipment(self):
        for reservation in self:
            missing = reservation.required_equipment_ids - reservation.room_id.equipment_ids
            if missing:
                raise ValidationError(
                    self.env._(
                        "%(room)s does not provide: %(equipment)s.",
                        room=reservation.room_id.display_name,
                        equipment=", ".join(missing.mapped("name")),
                    )
                )

    @api.onchange("attendee_count", "room_id")
    def _onchange_attendee_count(self):
        """Warn while editing. The binding rule is _check_capacity."""
        if self.room_id and self.attendee_count > self.room_id.capacity:
            return {
                "warning": {
                    "title": self.env._("Capacity exceeded"),
                    "message": self.env._(
                        "%(room)s holds %(capacity)s people.",
                        room=self.room_id.display_name,
                        capacity=self.room_id.capacity,
                    ),
                }
            }

    @api.model_create_multi
    def create(self, vals_list):
        reservations = super().create(vals_list)
        reservations._check_start_not_in_past()
        return reservations

    def write(self, vals):
        res = super().write(vals)
        # Only validated when the period is actually moved: a constraint would
        # otherwise turn invalid on its own as time passes, and freeze the
        # record against cancelling or completing it.
        if "start" in vals:
            self._check_start_not_in_past()
        return res

    def _check_start_not_in_past(self):
        now = fields.Datetime.now()
        for reservation in self:
            # Odoo returns False for unset fields, which cannot be compared.
            if reservation.start and reservation.start < now:
                raise ValidationError(
                    self.env._("A reservation cannot start in the past.")
                )
