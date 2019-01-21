from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SetMarginWizard(models.TransientModel):
    _name = 'boq.set.margin.wizard'
    _description = 'Set Margin to All Lines'

    boq_id = fields.Many2one(
        'boq.project',
        string='BOQ',
        required=True
    )
    
    margin_percent = fields.Float(
        'Margin %',
        required=True,
        digits=(5, 2),
        help="Margin percentage to apply to all activities and sub-activities"
    )
    
    apply_to = fields.Selection([
        ('all', 'All Activities and Sub-activities'),
        ('activities_only', 'Activities Only'),
        ('subactivities_only', 'Sub-activities Only'),
    ], string='Apply To', default='all', required=True)
    
    override_existing = fields.Boolean(
        'Override Existing Margins',
        default=True,
        help="If checked, will override existing margins. If unchecked, will only set margin where it's 0."
    )

    @api.constrains('margin_percent')
    def _check_margin(self):
        for wizard in self:
            if wizard.margin_percent < 0 or wizard.margin_percent > 100:
                raise ValidationError(_('Margin must be between 0% and 100%!'))

    def action_set_margin(self):
        """Apply margin to selected items"""
        self.ensure_one()
        
        boq = self.boq_id
        
        # Update BOQ global margin
        boq.margin_percent = self.margin_percent
        
        # Apply to activities
        if self.apply_to in ['all', 'activities_only']:
            for activity in boq.activity_line_ids:
                if self.override_existing or not activity.margin_percent:
                    activity.margin_percent = self.margin_percent
        
        # Apply to subactivities  
        if self.apply_to in ['all', 'subactivities_only']:
            for activity in boq.activity_line_ids:
                for subactivity in activity.subactivity_ids:
                    if self.override_existing or not subactivity.margin_percent:
                        subactivity.margin_percent = self.margin_percent
        
        # Show success message
        message = _('Margin of %s%% has been applied to %s.') % (
            self.margin_percent,
            dict(self._fields['apply_to'].selection)[self.apply_to]
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': message,
                'type': 'success',
            }
        }