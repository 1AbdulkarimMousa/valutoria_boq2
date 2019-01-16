from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BoqSubactivity(models.Model):
    _name = 'boq.subactivity'
    _description = 'BOQ Sub-Activity'
    _order = 'sequence, id'

    # Basic Fields
    name = fields.Char('Name', compute='_compute_name', store=True)
    sequence = fields.Integer('Sequence', default=10)
    
    activity_id = fields.Many2one(
        'boq.activity', 
        string='Activity',
        required=True, 
        ondelete='cascade'
    )
    boq_id = fields.Many2one(
        related='activity_id.boq_id', 
        store=True
    )

    # Product Details
    product_id = fields.Many2one(
        'product.product', 
        string='Product', 
        required=True
    )
    description = fields.Text('Description')
    
    activity_type = fields.Selection([
        ('material', 'Material'),
        ('labor', 'Labor'),
        ('service', 'Service')
    ], string='Activity Type', default='material')

    # Quantities
    previous_qty = fields.Float(
        'Previous Quantity', 
        digits=(12, 2), 
        readonly=True,
        help="Previously invoiced quantity"
    )
    current_qty = fields.Float(
        'Current Quantity', 
        digits=(12, 2),
        help="Current period progress quantity"
    )
    master_qty = fields.Float(
        'Master Quantity', 
        digits=(12, 2), 
        required=True,
        help="Total contracted quantity"
    )
    
    uom_id = fields.Many2one(
        'uom.uom', 
        string='UoM',
        related='product_id.uom_id', 
        readonly=True
    )

    # Costs and Pricing
    product_cost = fields.Float(
        'Product Cost', 
        digits=(12, 2),
        help="Base unit cost of product"
    )
    total_cost = fields.Float(
        'Total Cost', 
        compute='_compute_costs', 
        store=True,
        help="Product cost + additional costs"
    )
    margin_percent = fields.Float(
        'Margin %', 
        digits=(5, 2),
        help="Margin percentage applied to total cost"
    )
    unit_price = fields.Float(
        'Unit Price', 
        compute='_compute_unit_price', 
        store=True,
        help="Final unit price with margin"
    )

    # Amounts
    total_previous = fields.Monetary(
        'Total Previous', 
        compute='_compute_amounts',
        store=True
    )
    total_current = fields.Monetary(
        'Total Current', 
        compute='_compute_amounts',
        store=True
    )
    total_cumulative = fields.Monetary(
        'Total Cumulative', 
        compute='_compute_amounts',
        store=True
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

    # Additional Costs
    additional_cost_ids = fields.One2many(
        'boq.subactivity.cost', 
        'subactivity_id',
        string='Additional Costs'
    )

    # Variation Tracking
    is_variation = fields.Boolean('Is Variation', default=False)
    source_variation_id = fields.Many2one('boq.variation', string='Source Variation')

    # Related fields
    currency_id = fields.Many2one(related='boq_id.currency_id')
    company_id = fields.Many2one(related='boq_id.company_id', store=True)
    state = fields.Selection(related='boq_id.state')

    @api.depends('product_id', 'description')
    def _compute_name(self):
        for sub in self:
            parts = []
            if sub.product_id:
                parts.append(sub.product_id.name)
            if sub.description:
                parts.append(sub.description)
            sub.name = ' - '.join(parts) if parts else 'New Sub-Activity'

    @api.depends('product_cost', 'additional_cost_ids.cost')
    def _compute_costs(self):
        for sub in self:
            additional_costs = sum(sub.additional_cost_ids.mapped('cost'))
            sub.total_cost = sub.product_cost + additional_costs

    @api.depends('total_cost', 'margin_percent')
    def _compute_unit_price(self):
        for sub in self:
            if sub.margin_percent:
                sub.unit_price = sub.total_cost * (1 + sub.margin_percent / 100)
            else:
                sub.unit_price = sub.total_cost

    @api.depends('previous_qty', 'current_qty', 'master_qty', 'unit_price')
    def _compute_amounts(self):
        for sub in self:
            sub.total_previous = sub.previous_qty * sub.unit_price
            sub.total_current = sub.current_qty * sub.unit_price
            sub.total_cumulative = sub.master_qty * sub.unit_price

    @api.depends('previous_qty', 'current_qty', 'master_qty')
    def _compute_progress(self):
        for sub in self:
            if sub.master_qty:
                sub.billed_progress_percent = (sub.previous_qty / sub.master_qty) * 100
                sub.onsite_progress_percent = ((sub.previous_qty + sub.current_qty) / sub.master_qty) * 100
            else:
                sub.billed_progress_percent = 0
                sub.onsite_progress_percent = 0

    def action_view_additional_costs(self):
        """View additional costs in popup"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Additional Costs',
            'res_model': 'boq.subactivity.cost',
            'view_mode': 'list,form',
            'domain': [('subactivity_id', '=', self.id)],
            'context': {'default_subactivity_id': self.id},
            'target': 'new'
        }

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Set default cost from product"""
        if self.product_id:
            self.product_cost = self.product_id.standard_price
            if not self.description:
                self.description = self.product_id.description_sale or self.product_id.name

    @api.onchange('activity_id')
    def _onchange_activity_id(self):
        """Inherit margin from activity"""
        if self.activity_id and self.activity_id.margin_percent:
            self.margin_percent = self.activity_id.margin_percent

    @api.constrains('current_qty', 'previous_qty', 'master_qty')
    def _check_quantities(self):
        for sub in self:
            if sub.current_qty < 0 or sub.previous_qty < 0 or sub.master_qty < 0:
                raise ValidationError(_("Quantities cannot be negative!"))
            
            if (sub.previous_qty + sub.current_qty) > sub.master_qty:
                raise ValidationError(
                    _("Total progress (%s) cannot exceed master quantity (%s) for %s!") % 
                    (sub.previous_qty + sub.current_qty, sub.master_qty, sub.name)
                )

    @api.constrains('margin_percent')
    def _check_margin(self):
        for sub in self:
            if sub.margin_percent < 0 or sub.margin_percent > 100:
                raise ValidationError(_("Margin must be between 0% and 100%!"))

    @api.constrains('product_cost')
    def _check_product_cost(self):
        for sub in self:
            if sub.product_cost < 0:
                raise ValidationError(_("Product cost cannot be negative!"))


class BoqSubactivityCost(models.Model):
    _name = 'boq.subactivity.cost'
    _description = 'BOQ Sub-Activity Additional Cost'
    _rec_name = 'name'

    subactivity_id = fields.Many2one(
        'boq.subactivity', 
        string='Sub-Activity',
        required=True, 
        ondelete='cascade'
    )
    name = fields.Char('Name', required=True)
    cost = fields.Float('Cost', digits=(12, 2), required=True)
    description = fields.Text('Description')

    @api.constrains('cost')
    def _check_cost(self):
        for cost in self:
            if cost.cost < 0:
                raise ValidationError(_("Cost cannot be negative!"))