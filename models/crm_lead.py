from odoo import api, fields, models, _


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    boq_ids = fields.One2many(
        'boq.project', 
        'origin_lead_id', 
        string='BOQs'
    )
    
    boq_count = fields.Integer(
        'BOQ Count', 
        compute='_compute_boq_count'
    )

    def _compute_boq_count(self):
        for lead in self:
            lead.boq_count = len(lead.boq_ids)

    def action_create_boq(self):
        """Create BOQ from opportunity"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create BOQ'),
            'res_model': 'boq.project',
            'view_mode': 'form',
            'context': {
                'default_origin_lead_id': self.id,
                'default_customer_id': self.partner_id.id,
                'default_name': f"BOQ - {self.name}",
                'default_project_manager_id': self.user_id.id if self.user_id else self.env.user.id,
            },
            'target': 'current',
        }

    def action_view_boqs(self):
        """View BOQs related to this opportunity"""
        self.ensure_one()
        
        action = {
            'type': 'ir.actions.act_window',
            'name': _('BOQs'),
            'res_model': 'boq.project',
            'view_mode': 'list,form',
            'domain': [('origin_lead_id', '=', self.id)],
            'context': {
                'default_origin_lead_id': self.id,
                'default_customer_id': self.partner_id.id,
            }
        }
        
        if self.boq_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.boq_ids[0].id
        
        return action