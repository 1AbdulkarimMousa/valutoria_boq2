from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SubcontractWizard(models.TransientModel):
    _name = 'boq.subcontract.wizard'
    _description = 'Create Subcontract Purchase Order'

    boq_id = fields.Many2one(
        'boq.project',
        string='Source BOQ',
        required=True
    )
    
    vendor_id = fields.Many2one(
        'res.partner',
        string='Subcontractor',
        required=True,
        domain="[('supplier_rank', '>', 0)]"
    )
    
    project_name = fields.Char(
        'Project Reference',
        help="Reference for the subcontract project"
    )
    
    line_ids = fields.One2many(
        'boq.subcontract.wizard.line',
        'wizard_id',
        string='Activities to Subcontract'
    )
    
    company_id = fields.Many2one(
        related='boq_id.company_id'
    )
    
    currency_id = fields.Many2one(
        related='boq_id.currency_id'
    )

    @api.model
    def default_get(self, fields_list):
        """Populate wizard with BOQ activities"""
        defaults = super().default_get(fields_list)
        
        if 'boq_id' in self.env.context:
            boq = self.env['boq.project'].browse(self.env.context['boq_id'])
            defaults['boq_id'] = boq.id
            defaults['project_name'] = f"SUB-{boq.name}"
            
            # Create lines for activities
            line_vals = []
            for activity in boq.activity_line_ids:
                line_vals.append((0, 0, {
                    'activity_id': activity.id,
                    'selected': False,
                    'unit_cost': 0.0,  # Will be filled by user
                }))
            
            defaults['line_ids'] = line_vals
        
        return defaults

    def action_create_purchase_order(self):
        """Create purchase order for subcontracting"""
        self.ensure_one()
        
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Please select at least one activity to subcontract.'))
        
        # Create purchase order
        po_lines = []
        for line in selected_lines:
            # Create PO line for each subactivity in the activity
            for subactivity in line.activity_id.subactivity_ids:
                po_lines.append((0, 0, {
                    'product_id': subactivity.product_id.id,
                    'name': f"{line.activity_id.name} - {subactivity.name}",
                    'product_qty': subactivity.master_qty,
                    'product_uom': subactivity.uom_id.id,
                    'price_unit': line.unit_cost,
                    'date_planned': fields.Datetime.now(),
                    'analytic_distribution': {self.boq_id.analytic_account_id.id: 100} if self.boq_id.analytic_account_id else {},
                }))
        
        purchase_order = self.env['purchase.order'].create({
            'partner_id': self.vendor_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'origin': self.boq_id.name,
            'from_boq': True,
            'source_boq_id': self.boq_id.id,
            'order_line': po_lines,
            'boq_activity_ids': [(6, 0, selected_lines.mapped('activity_id').ids)],
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subcontract Purchase Order'),
            'res_model': 'purchase.order',
            'res_id': purchase_order.id,
            'view_mode': 'form',
        }

    @api.constrains('line_ids')
    def _check_lines(self):
        for wizard in self:
            selected_lines = wizard.line_ids.filtered('selected')
            for line in selected_lines:
                if line.unit_cost <= 0:
                    raise ValidationError(_('Unit cost must be greater than zero for selected activities.'))


class SubcontractWizardLine(models.TransientModel):
    _name = 'boq.subcontract.wizard.line'
    _description = 'Subcontract Wizard Line'

    wizard_id = fields.Many2one(
        'boq.subcontract.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    activity_id = fields.Many2one(
        'boq.activity',
        string='Activity',
        required=True
    )
    
    selected = fields.Boolean('Selected', default=False)
    
    unit_cost = fields.Float(
        'Unit Cost',
        digits=(12, 2),
        help="Cost per unit to pay to subcontractor"
    )
    
    # Display fields
    activity_name = fields.Char(related='activity_id.name')
    total_quantity = fields.Float(
        'Total Quantity',
        compute='_compute_totals'
    )
    estimated_total = fields.Monetary(
        'Estimated Total',
        compute='_compute_totals'
    )
    currency_id = fields.Many2one(related='wizard_id.currency_id')

    @api.depends('activity_id.subactivity_ids.master_qty', 'unit_cost')
    def _compute_totals(self):
        for line in self:
            line.total_quantity = sum(line.activity_id.subactivity_ids.mapped('master_qty'))
            line.estimated_total = line.total_quantity * line.unit_cost