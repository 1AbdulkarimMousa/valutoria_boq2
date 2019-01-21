from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AdvancePaymentWizard(models.TransientModel):
    _name = 'boq.advance.payment.wizard'
    _description = 'Register Advanced Payment'

    boq_id = fields.Many2one(
        'boq.project',
        string='BOQ',
        required=True
    )
    
    line_type = fields.Selection([
        ('original', 'Original'),
        ('variation', 'Variation')
    ], string='Line Type', default='original', required=True)
    
    payment_method = fields.Selection([
        ('percentage', 'Percentage'),
        ('amount', 'Fixed Amount')
    ], string='Payment Method', default='percentage', required=True)
    
    lines_total = fields.Monetary(
        'Lines Total',
        compute='_compute_lines_total',
        help="Total amount of selected lines"
    )
    
    payment_date = fields.Date(
        'Payment Date',
        default=fields.Date.today,
        required=True
    )
    
    amount = fields.Monetary('Amount')
    percentage = fields.Float('Percentage', digits=(5, 2))
    
    line_ids = fields.One2many(
        'boq.advance.payment.wizard.line',
        'wizard_id',
        string='Lines'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True
    )
    
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        required=True
    )
    
    company_id = fields.Many2one(
        related='boq_id.company_id'
    )

    @api.model
    def default_get(self, fields_list):
        """Populate wizard with BOQ data"""
        defaults = super().default_get(fields_list)
        
        if 'boq_id' in self.env.context:
            boq = self.env['boq.project'].browse(self.env.context['boq_id'])
            defaults['boq_id'] = boq.id
            defaults['currency_id'] = boq.currency_id.id
            defaults['journal_id'] = boq.adv_payment_journal_id.id if boq.adv_payment_journal_id else False
            
            # Create lines for activities
            line_vals = []
            for activity in boq.activity_line_ids:
                for subactivity in activity.subactivity_ids:
                    # Check if it's variation or original
                    is_variation = subactivity.is_variation
                    line_vals.append((0, 0, {
                        'subactivity_id': subactivity.id,
                        'amount': subactivity.total_cumulative,
                        'is_variation': is_variation,
                        'selected': not is_variation,  # Select original by default
                    }))
            
            defaults['line_ids'] = line_vals
        
        return defaults

    @api.depends('line_ids.selected', 'line_ids.amount', 'line_type')
    def _compute_lines_total(self):
        for wizard in self:
            selected_lines = wizard.line_ids.filtered(
                lambda l: l.selected and (
                    (wizard.line_type == 'original' and not l.is_variation) or
                    (wizard.line_type == 'variation' and l.is_variation)
                )
            )
            wizard.lines_total = sum(selected_lines.mapped('amount'))

    @api.onchange('percentage', 'lines_total', 'payment_method')
    def _onchange_percentage(self):
        """Calculate amount from percentage"""
        if self.payment_method == 'percentage' and self.percentage and self.lines_total:
            self.amount = self.lines_total * (self.percentage / 100)

    @api.onchange('amount', 'lines_total', 'payment_method')
    def _onchange_amount(self):
        """Calculate percentage from amount"""
        if self.payment_method == 'amount' and self.amount and self.lines_total:
            self.percentage = (self.amount / self.lines_total) * 100

    @api.onchange('line_type')
    def _onchange_line_type(self):
        """Update line selection based on type"""
        for line in self.line_ids:
            if self.line_type == 'original':
                line.selected = not line.is_variation
            else:
                line.selected = line.is_variation

    def action_create_invoice(self):
        """Create advance payment invoice"""
        self.ensure_one()
        
        if not self.line_ids.filtered('selected'):
            raise UserError(_('Please select at least one line for advance payment.'))
        
        if not self.amount:
            raise UserError(_('Amount must be greater than zero.'))
        
        # Create advance payment invoice
        invoice_vals = {
            'partner_id': self.boq_id.customer_id.id,
            'move_type': 'out_invoice',
            'invoice_date': self.payment_date,
            'journal_id': self.journal_id.id,
            'ref': f'Advance Payment - {self.boq_id.name}',
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': f'Advance Payment ({self.line_type.title()}) - {self.percentage}%' if self.payment_method == 'percentage' else f'Advance Payment ({self.line_type.title()})',
                'quantity': 1,
                'price_unit': self.amount,
                'account_id': self._get_advance_payment_account().id,
                'analytic_distribution': {self.boq_id.analytic_account_id.id: 100} if self.boq_id.analytic_account_id else {},
            })]
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        
        # Update BOQ advanced payment fields
        if self.line_type == 'original':
            self.boq_id.advanced_payment_amount_original += self.amount
            self.boq_id.advanced_payment_percentage_original = self.percentage
        else:
            self.boq_id.advanced_payment_amount_variation += self.amount
            self.boq_id.advanced_payment_percentage_variation = self.percentage
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Advance Payment Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }

    def _get_advance_payment_account(self):
        """Get advance payment account"""
        # Try to get from journal default account
        if self.journal_id.default_account_id:
            return self.journal_id.default_account_id
        
        # Fallback to receivable account
        return self.boq_id.customer_id.property_account_receivable_id

    @api.constrains('percentage')
    def _check_percentage(self):
        for wizard in self:
            if wizard.payment_method == 'percentage' and (wizard.percentage <= 0 or wizard.percentage > 100):
                raise ValidationError(_('Percentage must be between 0% and 100%.'))

    @api.constrains('amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_('Amount must be greater than zero.'))


class AdvancePaymentWizardLine(models.TransientModel):
    _name = 'boq.advance.payment.wizard.line'
    _description = 'Advance Payment Wizard Line'

    wizard_id = fields.Many2one(
        'boq.advance.payment.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    subactivity_id = fields.Many2one(
        'boq.subactivity',
        string='Sub-activity',
        required=True
    )
    
    selected = fields.Boolean('Selected', default=False)
    amount = fields.Monetary('Amount', required=True)
    is_variation = fields.Boolean('Is Variation', default=False)
    
    # Display fields
    activity_name = fields.Char(related='subactivity_id.activity_id.name')
    product_name = fields.Char(related='subactivity_id.product_id.name')
    currency_id = fields.Many2one(related='wizard_id.currency_id')