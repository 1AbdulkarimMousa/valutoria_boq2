from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BoqPaymentCertificate(models.Model):
    _name = 'boq.payment.certificate'
    _description = 'Payment Certificate (Mustahlas)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(
        'Certificate Number', 
        required=True, 
        copy=False,
        default=lambda self: _('New'),
        tracking=True
    )
    
    boq_id = fields.Many2one(
        'boq.project', 
        string='BOQ', 
        required=True,
        tracking=True
    )
    
    certificate_date = fields.Date(
        'Certificate Date',
        default=fields.Date.today,
        required=True,
        tracking=True
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('invoiced', 'Invoiced'),
        ('paid', 'Paid')
    ], string='Status', default='draft', tracking=True)

    line_ids = fields.One2many(
        'boq.payment.certificate.line', 
        'certificate_id',
        string='Certificate Lines'
    )

    # Computed amounts
    amount_completed = fields.Monetary(
        'Work Completed Amount', 
        compute='_compute_amounts',
        store=True
    )
    amount_approved = fields.Monetary(
        'Approved Amount', 
        compute='_compute_amounts',
        store=True
    )
    amount_retention = fields.Monetary(
        'Retention Amount', 
        compute='_compute_amounts',
        store=True
    )
    amount_advance_recovery_orig = fields.Monetary(
        'Advance Recovery Original', 
        compute='_compute_amounts',
        store=True
    )
    amount_advance_recovery_var = fields.Monetary(
        'Advance Recovery Variation', 
        compute='_compute_amounts',
        store=True
    )
    amount_invoice = fields.Monetary(
        'Net Invoice Amount', 
        compute='_compute_amounts',
        store=True
    )

    # Relationships
    invoice_id = fields.Many2one(
        'account.move', 
        string='Invoice',
        readonly=True
    )
    
    # Related fields
    currency_id = fields.Many2one(related='boq_id.currency_id')
    company_id = fields.Many2one(related='boq_id.company_id', store=True)
    customer_id = fields.Many2one(related='boq_id.customer_id')

    @api.model
    def create(self, vals):
        """Override create to set sequence"""
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('boq.payment.certificate') or _('New')
        return super().create(vals)

    @api.depends('line_ids.amount_completed', 'line_ids.amount_approved', 'line_ids.approved_percent')
    def _compute_amounts(self):
        for cert in self:
            cert.amount_completed = sum(cert.line_ids.mapped('amount_completed'))
            cert.amount_approved = sum(cert.line_ids.mapped('amount_approved'))
            
            # Calculate retention (5% of approved amount)
            retention_percent = 5.0  # Default 5%
            if cert.boq_id.retention_tax and '%' in cert.boq_id.retention_tax:
                try:
                    retention_percent = float(cert.boq_id.retention_tax.split()[-1].replace('%', ''))
                except (ValueError, IndexError):
                    retention_percent = 5.0
            
            cert.amount_retention = cert.amount_approved * (retention_percent / 100)
            
            # Calculate advance payment recovery
            if cert.amount_approved and cert.boq_id.total:
                # Recovery proportional to this certificate
                cert_ratio = cert.amount_approved / cert.boq_id.total
                cert.amount_advance_recovery_orig = (cert.boq_id.outstanding_advanced_payment_original * cert_ratio)
                cert.amount_advance_recovery_var = (cert.boq_id.outstanding_advanced_payment_variation * cert_ratio)
            else:
                cert.amount_advance_recovery_orig = 0
                cert.amount_advance_recovery_var = 0
            
            # Net invoice amount
            cert.amount_invoice = (cert.amount_approved - 
                                 cert.amount_retention - 
                                 cert.amount_advance_recovery_orig - 
                                 cert.amount_advance_recovery_var)

    def action_set_approved_amount(self):
        """Copy completion percentages to approved percentages"""
        for line in self.line_ids:
            line.approved_percent = line.completion_percent
        return True

    def action_submit(self):
        """Submit certificate and create draft invoice"""
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_('Cannot submit certificate without lines.'))
        
        # Create invoice lines
        invoice_lines = []
        
        # Add work completed lines
        for line in self.line_ids:
            if line.amount_approved > 0:
                invoice_lines.append((0, 0, {
                    'name': f"{line.subactivity_id.name} - {line.approved_percent:.1f}% Completed",
                    'quantity': line.qty_approved,
                    'price_unit': line.subactivity_id.unit_price,
                    'product_id': line.subactivity_id.product_id.id,
                    'analytic_distribution': {self.boq_id.analytic_account_id.id: 100} if self.boq_id.analytic_account_id else {},
                }))
        
        # Add advance recovery (negative lines)
        if self.amount_advance_recovery_orig > 0:
            invoice_lines.append((0, 0, {
                'name': 'Advance Payment Recovery (Original)',
                'quantity': -1,
                'price_unit': self.amount_advance_recovery_orig,
                'analytic_distribution': {self.boq_id.analytic_account_id.id: 100} if self.boq_id.analytic_account_id else {},
            }))
        
        if self.amount_advance_recovery_var > 0:
            invoice_lines.append((0, 0, {
                'name': 'Advance Payment Recovery (Variation)',
                'quantity': -1,
                'price_unit': self.amount_advance_recovery_var,
                'analytic_distribution': {self.boq_id.analytic_account_id.id: 100} if self.boq_id.analytic_account_id else {},
            }))
        
        # Add retention (negative line)
        if self.amount_retention > 0:
            invoice_lines.append((0, 0, {
                'name': f'Retention ({self.boq_id.retention_tax})',
                'quantity': -1,
                'price_unit': self.amount_retention,
                'analytic_distribution': {self.boq_id.analytic_account_id.id: 100} if self.boq_id.analytic_account_id else {},
            }))
        
        if not invoice_lines:
            raise UserError(_('No approved amounts to invoice.'))
        
        # Create invoice
        invoice = self.env['account.move'].create({
            'partner_id': self.boq_id.customer_id.id,
            'move_type': 'out_invoice',
            'invoice_date': self.certificate_date,
            'invoice_line_ids': invoice_lines,
            'ref': self.name,
            'company_id': self.company_id.id,
        })
        
        self.invoice_id = invoice
        self.state = 'submitted'
        
        # Update subactivity previous quantities
        for line in self.line_ids:
            if line.approved_percent > 0:
                line.subactivity_id.previous_qty += line.qty_approved
                line.subactivity_id.current_qty -= line.qty_approved
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }

    def action_approve(self):
        """Approve certificate"""
        self.state = 'approved'

    def action_invoice(self):
        """Mark as invoiced when invoice is confirmed"""
        if self.invoice_id and self.invoice_id.state == 'posted':
            self.state = 'invoiced'

    def action_view_invoice(self):
        """View related invoice"""
        if not self.invoice_id:
            raise UserError(_('No invoice created yet.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }


class BoqPaymentCertificateLine(models.Model):
    _name = 'boq.payment.certificate.line'
    _description = 'Payment Certificate Line'

    certificate_id = fields.Many2one(
        'boq.payment.certificate', 
        string='Certificate',
        required=True, 
        ondelete='cascade'
    )
    
    subactivity_id = fields.Many2one(
        'boq.subactivity', 
        string='Sub-Activity',
        required=True
    )
    
    # Quantities and percentages
    completion_percent = fields.Float(
        'Completion %', 
        digits=(5, 2),
        help="Contractor's claimed completion percentage"
    )
    approved_percent = fields.Float(
        'Approved %', 
        digits=(5, 2),
        help="Client's approved completion percentage"
    )
    
    qty_completed = fields.Float(
        'Qty Completed',
        compute='_compute_quantities',
        store=True
    )
    qty_approved = fields.Float(
        'Qty Approved',
        compute='_compute_quantities',
        store=True
    )
    
    # Amounts
    amount_completed = fields.Monetary(
        'Amount Completed',
        compute='_compute_amounts',
        store=True
    )
    amount_approved = fields.Monetary(
        'Amount Approved',
        compute='_compute_amounts',
        store=True
    )
    
    # Related fields
    master_qty = fields.Float(related='subactivity_id.master_qty')
    unit_price = fields.Float(related='subactivity_id.unit_price')
    currency_id = fields.Many2one(related='certificate_id.currency_id')
    product_id = fields.Many2one(related='subactivity_id.product_id')

    @api.depends('completion_percent', 'approved_percent', 'master_qty')
    def _compute_quantities(self):
        for line in self:
            line.qty_completed = (line.completion_percent / 100) * line.master_qty if line.master_qty else 0
            line.qty_approved = (line.approved_percent / 100) * line.master_qty if line.master_qty else 0

    @api.depends('qty_completed', 'qty_approved', 'unit_price')
    def _compute_amounts(self):
        for line in self:
            line.amount_completed = line.qty_completed * line.unit_price
            line.amount_approved = line.qty_approved * line.unit_price

    @api.constrains('completion_percent', 'approved_percent')
    def _check_percentages(self):
        for line in self:
            if line.completion_percent < 0 or line.completion_percent > 100:
                raise ValidationError(_('Completion percentage must be between 0% and 100%.'))
            if line.approved_percent < 0 or line.approved_percent > 100:
                raise ValidationError(_('Approved percentage must be between 0% and 100%.'))
            if line.approved_percent > line.completion_percent:
                raise ValidationError(_('Approved percentage cannot exceed completion percentage.'))