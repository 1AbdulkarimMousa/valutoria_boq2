from odoo import api, fields, models, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    from_boq = fields.Boolean('From BOQ?', default=False)
    source_boq_id = fields.Many2one('boq.project', string='Source BOQ')
    subcontract_boq_id = fields.Many2one('boq.project', string='Subcontract BOQ')

    # BOQ specific fields for subcontracting
    retention_tax = fields.Char('Retention Tax', default='RET 5% Purchase')
    retention_journal_id = fields.Many2one(
        'account.journal',
        string='Retention Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]"
    )
    adv_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Adv Payment Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]"
    )

    # Selected BOQ lines for subcontracting
    boq_activity_ids = fields.Many2many(
        'boq.activity',
        string='BOQ Activities',
        help="Activities from source BOQ to subcontract"
    )

    def button_confirm(self):
        """Create subcontractor BOQ on PO confirmation"""
        res = super().button_confirm()

        for order in self:
            if order.from_boq and order.source_boq_id and not order.subcontract_boq_id:
                # Create subcontractor BOQ
                subcontract_boq = self.env['boq.project'].create({
                    'name': f"SUB-{order.name}",
                    'type': 'subcontract',
                    'customer_id': order.partner_id.id,
                    'project_id': order.source_boq_id.project_id.id,
                    'analytic_account_id': order.source_boq_id.analytic_account_id.id,
                    'company_id': order.company_id.id,
                    'currency_id': order.currency_id.id,
                    'state': 'approved',
                    'purchase_order_id': order.id,
                })

                # Copy selected activities/subactivities to subcontractor BOQ
                for activity in order.boq_activity_ids:
                    # Create corresponding activity in subcontract BOQ
                    new_activity = self.env['boq.activity'].create({
                        'boq_id': subcontract_boq.id,
                        'name': activity.name,
                        'product_id': activity.product_id.id,
                        'description': activity.description,
                        'sequence': activity.sequence,
                    })

                    # Copy subactivities
                    for sub in activity.subactivity_ids:
                        # Find corresponding PO line to get subcontract price
                        po_line = order.order_line.filtered(
                            lambda l: l.product_id == sub.product_id
                        )
                        unit_cost = po_line[0].price_unit if po_line else sub.product_cost

                        self.env['boq.subactivity'].create({
                            'activity_id': new_activity.id,
                            'product_id': sub.product_id.id,
                            'description': sub.description,
                            'master_qty': sub.master_qty,
                            'product_cost': unit_cost,
                            'activity_type': sub.activity_type,
                            'margin_percent': 0,  # Usually no margin for subcontracts
                        })

                order.subcontract_boq_id = subcontract_boq

        return res

    def action_view_subcontract_boq(self):
        """View subcontract BOQ"""
        self.ensure_one()

        if not self.subcontract_boq_id:
            return {}

        return {
            'type': 'ir.actions.act_window',
            'name': _('Subcontract BOQ'),
            'res_model': 'boq.project',
            'res_id': self.subcontract_boq_id.id,
            'view_mode': 'form',
        }


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    boq_activity_id = fields.Many2one(
        'boq.activity',
        string='BOQ Activity'
    )
    boq_subactivity_ids = fields.Many2many(
        'boq.subactivity',
        string='BOQ Sub-activities'
    )