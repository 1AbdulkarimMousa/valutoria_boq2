from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BoqActivity(models.Model):
    _name = 'boq.activity'
    _description = 'BOQ Activity'
    _order = 'sequence, id'

    name = fields.Char('Name', required=True)
    sequence = fields.Integer('Sequence', default=10)
    
    boq_id = fields.Many2one(
        'boq.project', 
        string='BOQ', 
        required=True, 
        ondelete='cascade'
    )
    
    product_id = fields.Many2one(
        'product.product', 
        string='Product'
    )
    
    unit_of_measure = fields.Many2one(
        'uom.uom', 
        string='Unit of Measure',
        related='product_id.uom_id',
        readonly=True
    )
    
    description = fields.Text('Description')
    
    # Subactivities
    subactivity_ids = fields.One2many(
        'boq.subactivity', 
        'activity_id', 
        string='Sub Activities'
    )
    
    # Computed Totals
    total_previous = fields.Monetary(
        'Total Previous', 
        compute='_compute_totals',
        store=True
    )
    total_current = fields.Monetary(
        'Total Current', 
        compute='_compute_totals',
        store=True
    )
    total_cumulative = fields.Monetary(
        'Total Cumulative', 
        compute='_compute_totals',
        store=True
    )
    
    margin_percent = fields.Float(
        'Margin %', 
        digits=(5, 2)
    )
    
    # Progress
    billed_progress_percent = fields.Float(
        'Billed Progress %', 
        compute='_compute_progress',
        store=True
    )
    onsite_progress_percent = fields.Float(
        'Onsite Progress %', 
        compute='_compute_progress',
        store=True
    )
    
    # Related fields
    currency_id = fields.Many2one(
        related='boq_id.currency_id'
    )
    company_id = fields.Many2one(
        related='boq_id.company_id',
        store=True
    )
    state = fields.Selection(
        related='boq_id.state'
    )
    
    @api.depends('subactivity_ids.total_previous', 'subactivity_ids.total_current', 'subactivity_ids.total_cumulative')
    def _compute_totals(self):
        for activity in self:
            activity.total_previous = sum(activity.subactivity_ids.mapped('total_previous'))
            activity.total_current = sum(activity.subactivity_ids.mapped('total_current'))
            activity.total_cumulative = sum(activity.subactivity_ids.mapped('total_cumulative'))
    
    @api.depends('subactivity_ids.previous_qty', 'subactivity_ids.current_qty', 'subactivity_ids.master_qty')
    def _compute_progress(self):
        for activity in self:
            total_master = sum(activity.subactivity_ids.mapped('master_qty'))
            total_previous = sum(activity.subactivity_ids.mapped('previous_qty'))
            total_current = sum(activity.subactivity_ids.mapped('current_qty'))
            
            if total_master:
                activity.billed_progress_percent = (total_previous / total_master) * 100
                activity.onsite_progress_percent = ((total_previous + total_current) / total_master) * 100
            else:
                activity.billed_progress_percent = 0
                activity.onsite_progress_percent = 0
    
    def action_view_subactivities(self):
        """View subactivities in popup"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Sub-Activities: {self.name}',
            'res_model': 'boq.subactivity',
            'view_mode': 'list,form',
            'domain': [('activity_id', '=', self.id)],
            'context': {
                'default_activity_id': self.id,
                'default_boq_id': self.boq_id.id,
            },
            'target': 'new'
        }
    
    @api.model
    def create(self, vals):
        """Set sequence automatically"""
        if not vals.get('sequence'):
            boq_id = vals.get('boq_id')
            if boq_id:
                last_activity = self.search([('boq_id', '=', boq_id)], order='sequence desc', limit=1)
                vals['sequence'] = (last_activity.sequence or 0) + 10
        return super().create(vals)
    
    @api.constrains('margin_percent')
    def _check_margin(self):
        for activity in self:
            if activity.margin_percent < 0:
                raise ValidationError(_('Margin cannot be negative.'))