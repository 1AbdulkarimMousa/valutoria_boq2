from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BoqVariation(models.Model):
    _name = 'boq.variation'
    _description = 'BOQ Variation Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(
        'Variation Reference', 
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
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_submit', 'To Submit'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('applied', 'Applied'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    request_owner_id = fields.Many2one(
        'res.users', 
        string='Request Owner',
        default=lambda self: self.env.user,
        required=True,
        tracking=True
    )
    
    category = fields.Char(
        'Category', 
        default='Variation Order'
    )
    
    description = fields.Text(
        'Description',
        required=True
    )
    
    reason = fields.Text('Reason for Variation')
    
    # Approval workflow
    approver_ids = fields.Many2many(
        'res.users', 
        string='Approvers',
        help="Users who need to approve this variation"
    )
    
    approved_by_ids = fields.Many2many(
        'res.users',
        'variation_approved_users_rel',
        string='Approved By',
        readonly=True
    )
    
    approval_date = fields.Datetime(
        'Approval Date',
        readonly=True
    )
    
    # Variation lines organized by action type
    edit_line_ids = fields.One2many(
        'boq.variation.line', 
        'variation_id',
        string='Edit Sub-Activities',
        domain=[('action_type', '=', 'edit')]
    )
    
    add_line_ids = fields.One2many(
        'boq.variation.line', 
        'variation_id',
        string='Add Sub-Activities', 
        domain=[('action_type', '=', 'add')]
    )
    
    new_activity_line_ids = fields.One2many(
        'boq.variation.line', 
        'variation_id',
        string='Create New Activities',
        domain=[('action_type', '=', 'new_activity')]
    )
    
    # Financial impact
    total_variation_amount = fields.Monetary(
        'Total Variation Amount',
        compute='_compute_variation_totals',
        store=True
    )
    
    # Related fields
    currency_id = fields.Many2one(related='boq_id.currency_id')
    company_id = fields.Many2one(related='boq_id.company_id', store=True)
    customer_id = fields.Many2one(related='boq_id.customer_id')

    @api.model
    def create(self, vals):
        """Override create to set sequence"""
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('boq.variation') or _('New')
        return super().create(vals)

    @api.depends('edit_line_ids.variation_amount', 'add_line_ids.new_total_amount', 'new_activity_line_ids.new_total_amount')
    def _compute_variation_totals(self):
        for variation in self:
            edit_total = sum(variation.edit_line_ids.mapped('variation_amount'))
            add_total = sum(variation.add_line_ids.mapped('new_total_amount'))
            new_activity_total = sum(variation.new_activity_line_ids.mapped('new_total_amount'))
            variation.total_variation_amount = edit_total + add_total + new_activity_total

    def action_submit(self):
        """Submit variation for approval"""
        if not (self.edit_line_ids or self.add_line_ids or self.new_activity_line_ids):
            raise UserError(_('Cannot submit variation without any changes.'))
        
        self.state = 'submitted'

    def action_approve(self):
        """Approve variation"""
        self.approved_by_ids = [(4, self.env.user.id)]
        self.approval_date = fields.Datetime.now()
        self.state = 'approved'

    def action_refuse(self):
        """Refuse variation"""
        self.state = 'refused'

    def action_cancel(self):
        """Cancel variation"""
        self.state = 'cancelled'

    def action_apply_variation(self):
        """Apply variation changes to BOQ"""
        self.ensure_one()
        
        if self.state != 'approved':
            raise UserError(_('Only approved variations can be applied.'))
        
        # Process edit lines - modify existing subactivities
        for line in self.edit_line_ids:
            if line.target_subactivity_id:
                subactivity = line.target_subactivity_id
                if line.new_qty:
                    subactivity.master_qty = line.new_qty
                if line.new_cost:
                    subactivity.product_cost = line.new_cost
                if line.new_margin:
                    subactivity.margin_percent = line.new_margin
                
                subactivity.is_variation = True
                subactivity.source_variation_id = self.id
        
        # Process add lines - create new subactivities for existing activities
        for line in self.add_line_ids:
            if line.target_activity_id and line.product_id:
                self.env['boq.subactivity'].create({
                    'activity_id': line.target_activity_id.id,
                    'product_id': line.product_id.id,
                    'description': line.description,
                    'master_qty': line.new_qty,
                    'product_cost': line.new_cost,
                    'margin_percent': line.new_margin,
                    'activity_type': line.activity_type,
                    'is_variation': True,
                    'source_variation_id': self.id,
                })
        
        # Process new activity lines - create new activities with subactivities
        for line in self.new_activity_line_ids:
            if line.activity_name and line.product_id:
                # Create new activity
                activity = self.env['boq.activity'].create({
                    'boq_id': self.boq_id.id,
                    'name': line.activity_name,
                    'product_id': line.product_id.id,
                    'description': f'Added by variation {self.name}',
                })
                
                # Create subactivity for the new activity
                self.env['boq.subactivity'].create({
                    'activity_id': activity.id,
                    'product_id': line.product_id.id,
                    'description': line.description,
                    'master_qty': line.new_qty,
                    'product_cost': line.new_cost,
                    'margin_percent': line.new_margin,
                    'activity_type': line.activity_type,
                    'is_variation': True,
                    'source_variation_id': self.id,
                })
        
        self.state = 'applied'
        
        # Send notification
        self.message_post(
            body=_('Variation %s has been successfully applied to BOQ %s.') % (self.name, self.boq_id.name),
            message_type='notification'
        )

    @api.constrains('approver_ids')
    def _check_approvers(self):
        for variation in self:
            if variation.state in ['submitted', 'approved'] and not variation.approver_ids:
                raise ValidationError(_('At least one approver must be assigned for submitted variations.'))


class BoqVariationLine(models.Model):
    _name = 'boq.variation.line'
    _description = 'BOQ Variation Line'
    _rec_name = 'display_name'

    variation_id = fields.Many2one(
        'boq.variation',
        string='Variation',
        required=True,
        ondelete='cascade'
    )
    
    action_type = fields.Selection([
        ('edit', 'Edit Existing Sub-Activity'),
        ('add', 'Add Sub-Activity to Existing Activity'),
        ('new_activity', 'Create New Activity')
    ], string='Action Type', required=True)
    
    # For editing existing subactivities
    target_subactivity_id = fields.Many2one(
        'boq.subactivity',
        string='Target Sub-Activity',
        domain="[('boq_id', '=', parent.boq_id)]"
    )
    
    # For adding to existing activities
    target_activity_id = fields.Many2one(
        'boq.activity',
        string='Target Activity',
        domain="[('boq_id', '=', parent.boq_id)]"
    )
    
    # For new activities
    activity_name = fields.Char('Activity Name')
    
    # Product and details
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Text('Description')
    activity_type = fields.Selection([
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('service', 'Service')
    ], string='Activity Type', default='material')
    
    # Original values (for edits)
    original_qty = fields.Float('Original Quantity', readonly=True)
    original_cost = fields.Float('Original Cost', readonly=True)
    original_margin = fields.Float('Original Margin %', readonly=True)
    original_total_amount = fields.Monetary('Original Total Amount', readonly=True)
    
    # New values
    new_qty = fields.Float('New Quantity', digits=(12, 2))
    new_cost = fields.Float('New Cost', digits=(12, 2))
    new_margin = fields.Float('New Margin %', digits=(5, 2))
    new_unit_price = fields.Float('New Unit Price', compute='_compute_new_amounts', store=True)
    new_total_amount = fields.Monetary('New Total Amount', compute='_compute_new_amounts', store=True)
    
    # Variation impact
    qty_variation = fields.Float('Qty Variation', compute='_compute_variations', store=True)
    cost_variation = fields.Float('Cost Variation', compute='_compute_variations', store=True)
    variation_amount = fields.Monetary('Variation Amount', compute='_compute_variations', store=True)
    
    # Display
    display_name = fields.Char('Display Name', compute='_compute_display_name')
    
    # Related
    currency_id = fields.Many2one(related='variation_id.currency_id')

    @api.depends('action_type', 'target_subactivity_id', 'target_activity_id', 'activity_name', 'product_id')
    def _compute_display_name(self):
        for line in self:
            if line.action_type == 'edit' and line.target_subactivity_id:
                line.display_name = f'Edit: {line.target_subactivity_id.name}'
            elif line.action_type == 'add' and line.target_activity_id:
                product_name = line.product_id.name if line.product_id else 'New Item'
                line.display_name = f'Add to {line.target_activity_id.name}: {product_name}'
            elif line.action_type == 'new_activity':
                line.display_name = f'New Activity: {line.activity_name or "Unnamed"}'
            else:
                line.display_name = 'Variation Line'

    @api.depends('new_cost', 'new_margin', 'new_qty')
    def _compute_new_amounts(self):
        for line in self:
            if line.new_margin:
                line.new_unit_price = line.new_cost * (1 + line.new_margin / 100)
            else:
                line.new_unit_price = line.new_cost
            
            line.new_total_amount = line.new_qty * line.new_unit_price

    @api.depends('original_qty', 'original_cost', 'original_total_amount', 'new_qty', 'new_cost', 'new_total_amount')
    def _compute_variations(self):
        for line in self:
            line.qty_variation = line.new_qty - line.original_qty
            line.cost_variation = line.new_cost - line.original_cost
            line.variation_amount = line.new_total_amount - line.original_total_amount

    @api.onchange('target_subactivity_id')
    def _onchange_target_subactivity(self):
        """Populate original values when selecting subactivity to edit"""
        if self.target_subactivity_id:
            sub = self.target_subactivity_id
            self.product_id = sub.product_id
            self.description = sub.description
            self.activity_type = sub.activity_type
            self.original_qty = sub.master_qty
            self.original_cost = sub.product_cost
            self.original_margin = sub.margin_percent
            self.original_total_amount = sub.total_cumulative
            # Set new values as defaults
            self.new_qty = sub.master_qty
            self.new_cost = sub.product_cost
            self.new_margin = sub.margin_percent

    @api.constrains('new_qty', 'new_cost', 'new_margin')
    def _check_new_values(self):
        for line in self:
            if line.new_qty < 0:
                raise ValidationError(_('New quantity cannot be negative.'))
            if line.new_cost < 0:
                raise ValidationError(_('New cost cannot be negative.'))
            if line.new_margin < 0 or line.new_margin > 100:
                raise ValidationError(_('New margin must be between 0% and 100%.'))

    @api.constrains('action_type', 'target_subactivity_id', 'target_activity_id', 'activity_name')
    def _check_required_fields(self):
        for line in self:
            if line.action_type == 'edit' and not line.target_subactivity_id:
                raise ValidationError(_('Target sub-activity is required for edit actions.'))
            if line.action_type == 'add' and not line.target_activity_id:
                raise ValidationError(_('Target activity is required for add actions.'))
            if line.action_type == 'new_activity' and not line.activity_name:
                raise ValidationError(_('Activity name is required for new activity actions.'))