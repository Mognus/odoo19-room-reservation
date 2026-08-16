# Odoo manifests are data, not code: a bare dict literal read with
# ast.literal_eval, which a static checker sees as an expression without effect.
# pyright: reportUnusedExpression=false
{
    "name": "Room Reservations",
    "summary": "Book meeting rooms with capacity checks and an approval workflow",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "license": "LGPL-3",
    "author": "Mognus",
    "website": "https://github.com/Mognus/odoo19-room-reservation",
    "depends": ["base", "mail"],
    "data": [
        # Groups must load before the access rights that reference them.
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "views/booking_room_equipment_views.xml",
        "views/booking_room_views.xml",
        "views/booking_reservation_views.xml",
        "views/res_users_views.xml",
        # Menus come last: they reference the actions defined above.
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
}
