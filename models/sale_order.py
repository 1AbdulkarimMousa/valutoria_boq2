from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    boq_id = fields.Many2one(
        'boq.project', 
        string='BOQ',
        readonly=True
    )
    
    from_boq = fields.Boolean(
        'From BOQ',
        default=False
    )

    @api.model
    def create(self, vals):
        """Auto-link to BOQ if created from BOQ submit"""
        if self.env.context.get('from_boq_id'):
            vals['boq_id'] = self.env.context.get('from_boq_id')
            vals['from_boq'] = True
        return super().create(vals)

    def action_confirm(self):
        """Create project and link to BOQ on confirmation"""
        res = super().action_confirm()
        
        for order in self:
            if order.boq_id:
                # Update BOQ state to approved and in progress
                if order.boq_id.state == 'submitted':
                    order.boq_id.action_approve()
                    order.boq_id.action_start_progress()
                
                # Create project if not exists
                if not order.boq_id.project_id:
                    project = self.env['project.project'].create({
                        'name': order.boq_id.name,
                        'partner_id': order.partner_id.id,
                        'user_id': order.boq_id.project_manager_id.id,
                        'analytic_account_id': order.boq_id.analytic_account_id.id,
                        'company_id': order.company_id.id,
                        'sale_order_id': order.id,
                    })
                    order.boq_id.project_id = project
        
        return res

    def action_view_boq(self):
        """View related BOQ"""
        self.ensure_one()
        
        if not self.boq_id:
            return {}
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('BOQ'),
            'res_model': 'boq.project',
            'res_id': self.boq_id.id,
            'view_mode': 'form',
        }