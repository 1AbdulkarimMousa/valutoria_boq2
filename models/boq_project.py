from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class BoqProject(models.Model):
    _name = 'boq.project'
    _description = 'Bill of Quantities'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'create_date desc, id desc'

    # Basic Fields
    name = fields.Char(
        'BOQ Reference', 
        required=True, 
        copy=False,
        default=lambda self: _('New'),
        tracking=True
    )
    
    project_id = fields.Many2one(
        'project.project', 
        string='Project',
        tracking=True
    )
    
    customer_id = fields.Many2one(
        'res.partner', 
        string='Customer', 
        required=True,
        tracking=True,
        domain="[('is_company', '=', True)]"
    )
    
    project_manager_id = fields.Many2one(
        'res.users', 
        string='Project Manager',
        default=lambda self: self.env.user,
        tracking=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
        tracking=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    
    type = fields.Selection([
        ('client', 'Client'), 
        ('subcontract', 'Subcontract')
    ], string='Type', default='client', required=True, tracking=True)
    
    # Date Fields
    start_date = fields.Date('Start Date', tracking=True)
    end_date = fields.Date('End Date', tracking=True)
    create_date = fields.Datetime('Created On', readonly=True)
    
    # State Management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Progress Fields
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
    margin_percent = fields.Float(
        'Global Margin %', 
        digits=(5, 2),
        tracking=True
    )
    
    # Relational Fields
    activity_line_ids = fields.One2many(
        'boq.activity', 
        'boq_id', 
        string='Activity Lines'
    )
    
    payment_certificate_ids = fields.One2many(
        'boq.payment.certificate', 
        'boq_id',
        string='Payment Certificates'
    )
    
    variation_ids = fields.One2many(
        'boq.variation', 
        'boq_id', 
        string='Variations'
    )
    
    sale_order_id = fields.Many2one(
        'sale.order', 
        string='Sale Order',
        readonly=True
    )
    
    origin_lead_id = fields.Many2one(
        'crm.lead', 
        string='Opportunity'
    )
    
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order'
    )
    
    # Accounting Tab Fields
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account'
    )
    
    # Retention Fields
    retention_tax = fields.Char(
        'Retention Tax',
        default='RET 5%'
    )
    retention_journal_id = fields.Many2one(
        'account.journal',
        string='Retention Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]"
    )
    retention_amount_total = fields.Monetary(
        'Retention Amount Total',
        compute='_compute_retention_amounts',
        store=True
    )
    
    # Advanced Payment Fields  
    adv_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Adv Payment Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]"
    )
    
    # Original Advanced Payment
    advanced_payment_amount_original = fields.Monetary(
        'Advanced Payment Amount Original'
    )
    advanced_payment_percentage_original = fields.Float(
        'Advanced Payment Percentage Original',
        digits=(5, 2)
    )
    outstanding_advanced_payment_original = fields.Monetary(
        'Outstanding Advanced Payment Amount Original',
        compute='_compute_outstanding_advances',
        store=True
    )
    
    # Variation Advanced Payment
    advanced_payment_amount_variation = fields.Monetary(
        'Advanced Payment Amount Variation'
    )
    advanced_payment_percentage_variation = fields.Float(
        'Advanced Payment Percentage Variation',
        digits=(5, 2)
    )
    outstanding_advanced_payment_variation = fields.Monetary(
        'Outstanding Advanced Payment Amount Variation',
        compute='_compute_outstanding_advances',
        store=True
    )
    
    # Cost Types
    cost_type_ids = fields.Many2many(
        'boq.cost.type',
        string='Cost Types'
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
    total = fields.Monetary(
        'Total',
        compute='_compute_totals',
        store=True
    )
    
    # Statistics
    payment_certificate_count = fields.Integer(
        'Payment Certificate Count',
        compute='_compute_counts'
    )
    variation_count = fields.Integer(
        'Variation Count',
        compute='_compute_counts'
    )
    
    @api.model
    def create(self, vals):
        """Override create to set sequence"""
        if vals.get('name', _('New')) == _('New'):
            if vals.get('type') == 'subcontract':
                vals['name'] = self.env['ir.sequence'].next_by_code('boq.subcontract') or _('New')
            else:
                vals['name'] = self.env['ir.sequence'].next_by_code('boq.project') or _('New')
        return super().create(vals)
    
    @api.depends('activity_line_ids.total_previous', 'activity_line_ids.total_current', 'activity_line_ids.total_cumulative')
    def _compute_totals(self):
        for boq in self:
            boq.total_previous = sum(boq.activity_line_ids.mapped('total_previous'))
            boq.total_current = sum(boq.activity_line_ids.mapped('total_current'))
            boq.total = sum(boq.activity_line_ids.mapped('total_cumulative'))
    
    @api.depends('activity_line_ids.billed_progress_percent', 'activity_line_ids.onsite_progress_percent')
    def _compute_progress(self):
        for boq in self:
            if boq.activity_line_ids:
                total_cumulative = sum(boq.activity_line_ids.mapped('total_cumulative'))
                if total_cumulative:
                    weighted_billed = sum(
                        activity.billed_progress_percent * activity.total_cumulative / 100
                        for activity in boq.activity_line_ids
                    )
                    weighted_onsite = sum(
                        activity.onsite_progress_percent * activity.total_cumulative / 100
                        for activity in boq.activity_line_ids
                    )
                    boq.billed_progress_percent = (weighted_billed / total_cumulative) * 100
                    boq.onsite_progress_percent = (weighted_onsite / total_cumulative) * 100
                else:
                    boq.billed_progress_percent = 0
                    boq.onsite_progress_percent = 0
            else:
                boq.billed_progress_percent = 0
                boq.onsite_progress_percent = 0
    
    @api.depends('total', 'retention_tax')
    def _compute_retention_amounts(self):
        for boq in self:
            if boq.retention_tax and '%' in boq.retention_tax:
                try:
                    # Extract percentage from retention_tax (e.g., "RET 5%" -> 5)
                    percentage = float(boq.retention_tax.split()[-1].replace('%', ''))
                    boq.retention_amount_total = boq.total * (percentage / 100)
                except (ValueError, IndexError):
                    boq.retention_amount_total = 0
            else:
                boq.retention_amount_total = 0
    
    @api.depends('advanced_payment_amount_original', 'advanced_payment_amount_variation')
    def _compute_outstanding_advances(self):
        for boq in self:
            # Calculate how much advance payment is still outstanding
            # This would need to be calculated based on recovery in payment certificates
            boq.outstanding_advanced_payment_original = boq.advanced_payment_amount_original
            boq.outstanding_advanced_payment_variation = boq.advanced_payment_amount_variation
    
    def _compute_counts(self):
        for boq in self:
            boq.payment_certificate_count = len(boq.payment_certificate_ids)
            boq.variation_count = len(boq.variation_ids)
    
    def action_set_margin(self):
        """Open wizard to set margin to all lines"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Set Margin',
            'res_model': 'boq.set.margin.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_boq_id': self.id}
        }
    
    def action_submit(self):
        """Submit BOQ and create Sales Order"""
        self.ensure_one()
        
        if not self.activity_line_ids:
            raise UserError(_('Cannot submit BOQ without activity lines.'))
        
        # Create sale order lines from activities
        order_lines = []
        for activity in self.activity_line_ids:
            if activity.total_cumulative > 0:
                order_lines.append((0, 0, {
                    'product_id': activity.product_id.id if activity.product_id else False,
                    'name': activity.name,
                    'product_uom_qty': 1,
                    'price_unit': activity.total_cumulative,
                    'tax_id': [(6, 0, [])],
                }))
        
        if not order_lines:
            raise UserError(_('No activities with amounts to create sale order.'))
        
        # Create sale order
        sale_order = self.env['sale.order'].with_context(from_boq_id=self.id).create({
            'partner_id': self.customer_id.id,
            'order_line': order_lines,
            'origin': self.name,
            'company_id': self.company_id.id,
        })
        
        self.sale_order_id = sale_order
        self.state = 'submitted'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
        }
    
    def action_approve(self):
        """Approve BOQ and confirm Sales Order"""
        self.ensure_one()
        
        if self.sale_order_id and self.sale_order_id.state == 'draft':
            self.sale_order_id.action_confirm()
        
        # Create analytic account if not exists
        if not self.analytic_account_id:
            analytic = self.env['account.analytic.account'].create({
                'name': self.name,
                'partner_id': self.customer_id.id,
                'company_id': self.company_id.id,
            })
            self.analytic_account_id = analytic
        
        # Create project if not exists
        if not self.project_id:
            project = self.env['project.project'].create({
                'name': self.name,
                'partner_id': self.customer_id.id,
                'user_id': self.project_manager_id.id,
                'analytic_account_id': self.analytic_account_id.id,
                'company_id': self.company_id.id,
            })
            self.project_id = project
        
        self.state = 'approved'
    
    def action_start_progress(self):
        """Start project progress"""
        self.state = 'in_progress'
    
    def action_done(self):
        """Mark BOQ as done"""
        self.state = 'done'
    
    def action_cancel(self):
        """Cancel BOQ"""
        self.state = 'cancelled'
    
    def action_draft(self):
        """Reset to draft"""
        self.state = 'draft'
    
    def action_register_advance_payment(self):
        """Open advance payment wizard"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Register Advanced Payment',
            'res_model': 'boq.advance.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_boq_id': self.id,
                'default_currency_id': self.currency_id.id,
            }
        }
    
    def action_create_payment_certificate(self):
        """Create payment certificate from current progress"""
        self.ensure_one()
        
        # Get all subactivities with current progress
        lines_to_invoice = []
        for activity in self.activity_line_ids:
            for sub in activity.subactivity_ids:
                if sub.current_qty > 0:
                    lines_to_invoice.append((0, 0, {
                        'subactivity_id': sub.id,
                        'completion_percent': (sub.current_qty / sub.master_qty) * 100 if sub.master_qty else 0,
                        'qty_completed': sub.current_qty,
                        'amount_completed': sub.current_qty * sub.unit_price,
                    }))
        
        if not lines_to_invoice:
            raise UserError(_("No progress to invoice!"))
        
        # Create certificate
        certificate = self.env['boq.payment.certificate'].create({
            'boq_id': self.id,
            'line_ids': lines_to_invoice,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'boq.payment.certificate',
            'res_id': certificate.id,
            'view_mode': 'form',
        }
    
    def action_request_variation(self):
        """Create new variation order"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request New Variation',
            'res_model': 'boq.variation',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_boq_id': self.id,
                'default_request_owner_id': self.env.user.id,
            }
        }
    
    def action_view_payment_certificates(self):
        """View payment certificates"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Payment Certificates',
            'res_model': 'boq.payment.certificate',
            'view_mode': 'list,form',
            'domain': [('boq_id', '=', self.id)],
            'context': {'default_boq_id': self.id}
        }
    
    def action_view_variations(self):
        """View variations"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Variation Orders',
            'res_model': 'boq.variation',
            'view_mode': 'list,form',
            'domain': [('boq_id', '=', self.id)],
            'context': {'default_boq_id': self.id}
        }
    
    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for boq in self:
            if boq.start_date and boq.end_date and boq.start_date > boq.end_date:
                raise ValidationError(_('End date must be after start date.'))
    
    @api.constrains('margin_percent')
    def _check_margin(self):
        for boq in self:
            if boq.margin_percent < 0:
                raise ValidationError(_('Margin cannot be negative.'))