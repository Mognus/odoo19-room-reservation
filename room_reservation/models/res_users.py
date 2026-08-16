from odoo import api, fields, models


class ResUsers(models.Model):
    """Extend the standard user with the reservations they organize."""

    # Both are set on purpose: without an explicit _name, Odoo derives it from
    # the class name, which would silently create a new model if the class were
    # ever renamed.
    _name = "res.users"
    _inherit = ["res.users"]

    reservation_ids = fields.One2many(
        comodel_name="booking.reservation",
        inverse_name="user_id",
        string="Reservations",
    )
    reservation_count = fields.Integer(compute="_compute_reservation_count")

    @api.depends("reservation_ids")
    def _compute_reservation_count(self):
        counts = dict(
            self.env["booking.reservation"]._read_group(
                domain=[("user_id", "in", self.ids)],
                groupby=["user_id"],
                aggregates=["__count"],
            )
        )
        for user in self:
            user.reservation_count = counts.get(user, 0)

    def action_view_reservations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Reservations"),
            "res_model": "booking.reservation",
            "view_mode": "list,calendar,form",
            "domain": [("user_id", "=", self.id)],
            "context": {"default_user_id": self.id},
        }
