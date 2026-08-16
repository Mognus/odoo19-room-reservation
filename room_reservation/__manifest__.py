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
