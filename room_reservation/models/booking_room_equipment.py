from odoo import fields, models


class BookingRoomEquipment(models.Model):
    """Equipment a room can provide, such as a projector or a whiteboard."""

    _name = "booking.room.equipment"
    _description = "Room Equipment"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(
        default=True,
        help="Archive equipment instead of deleting it, "
        "so historical rooms stay intact.",
    )
    room_ids = fields.Many2many(
        comodel_name="booking.room",
        relation="booking_room_equipment_rel",
        column1="equipment_id",
        column2="room_id",
        string="Rooms",
    )

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Equipment with this name already exists.",
    )
