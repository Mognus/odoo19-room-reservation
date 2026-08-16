from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

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

    # Allowed state changes. Keeping them as data means adding a state changes
    # this mapping instead of every action method, and a single test can cover
    # every combination.
    _TRANSITIONS = {
        "draft": {"to_approve", "cancelled"},
        "to_approve": {"confirmed", "draft", "cancelled"},
        "confirmed": {"done", "cancelled"},
        "done": set(),
        "cancelled": {"draft"},
    }

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
                        "%(room)s holds %(capacity)s people, "
                        "but %(requested)s are expected.",
                        room=reservation.room_id.display_name,
                        capacity=reservation.room_id.capacity,
                        requested=reservation.attendee_count,
                    )
                )

    @api.constrains("required_equipment_ids", "room_id")
    def _check_required_equipment(self):
        for reservation in self:
            available = reservation.room_id.equipment_ids
            missing = reservation.required_equipment_ids - available
            if missing:
                raise ValidationError(
                    self.env._(
                        "%(room)s does not provide: %(equipment)s.",
                        room=reservation.room_id.display_name,
                        equipment=", ".join(missing.mapped("name")),
                    )
                )

    @api.constrains("start")
    def _check_start_not_in_past(self):
        """Rejects a period that begins in the past.

        Odoo runs a constraint only for the fields present in the create or
        write values, so this never fires when merely the state changes. A
        reservation that has already started therefore stays cancellable.
        """
        now = fields.Datetime.now()
        for reservation in self:
            # Odoo returns False for unset fields, which cannot be compared.
            if reservation.start and reservation.start < now:
                raise ValidationError(
                    self.env._("A reservation cannot start in the past.")
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
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "booking.reservation"
                ) or "/"
        return super().create(vals_list)

    def _transition_to(self, target, values=None):
        """Single entry point for state changes, validated against _TRANSITIONS.

        Actions and the scheduled job both go through here, so the rules can
        never drift apart between the user interface and automation.
        """
        labels = dict(self._fields["state"]._description_selection(self.env))
        for reservation in self:
            if target not in self._TRANSITIONS[reservation.state]:
                raise UserError(
                    self.env._(
                        "%(reference)s cannot move from %(current)s to %(target)s.",
                        reference=reservation.display_name,
                        current=labels[reservation.state],
                        target=labels[target],
                    )
                )
        self.write({"state": target, **(values or {})})

    def action_submit(self):
        self._transition_to("to_approve")
        self._schedule_approval_activity()

    def _schedule_approval_activity(self):
        """Put a to-do in the inbox of every booking manager.

        Uses Odoo's activity system rather than a custom notification, so the
        request shows up in the same place as every other pending task.
        """
        managers = self.env.ref("room_reservation.group_booking_manager").user_ids
        for reservation in self:
            for manager in managers:
                reservation.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=manager.id,
                    summary=self.env._("Approve room reservation"),
                    note=self.env._(
                        "%(room)s, %(start)s",
                        room=reservation.room_id.display_name,
                        start=reservation.start,
                    ),
                )

    @api.model
    def _cron_expire_pending(self):
        """Cancel requests that are still unapproved shortly before they start.

        The threshold is read from a configuration parameter so it can be tuned
        per database, and so tests can shift the rule instead of the clock.
        """
        hours = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("room_reservation.pending_expiry_hours", default=24)
        )
        deadline = fields.Datetime.now() + timedelta(hours=hours)
        stale = self.search(
            [("state", "=", "to_approve"), ("start", "<=", deadline)]
        )
        if not stale:
            return
        # Goes through the same state machine as the button in the form.
        stale._transition_to("cancelled")
        for reservation in stale:
            reservation.message_post(
                body=self.env._("Cancelled automatically: not approved in time.")
            )
        # Remove the now pointless approval task from the managers' inboxes.
        stale.activity_unlink(["mail.mail_activity_data_todo"])

    def action_approve(self):
        # Record rules let managers write any reservation, but approving is a
        # narrower privilege than writing and is checked explicitly.
        if not self.env.user.has_group("room_reservation.group_booking_manager"):
            raise UserError(
                self.env._("Only a booking manager can approve reservations.")
            )
        self._transition_to(
            "confirmed",
            {
                "approver_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            },
        )

    def action_cancel(self):
        self._transition_to("cancelled")

    def action_done(self):
        self._transition_to("done")

    def action_reset_to_draft(self):
        # Clear the approval trail so a resubmitted request is approved again.
        self._transition_to("draft", {"approver_id": False, "approval_date": False})
