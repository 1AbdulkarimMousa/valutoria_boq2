from odoo import api, fields, models, _


class BoqCostType(models.Model):
    _name = 'boq.cost.type'
    _description = 'BOQ Cost Type'
    _order = 'name'

    name = fields.Char('Name', required=True)
    code = fields.Char('Code')
    description = fields.Text('Description')
    active = fields.Boolean('Active', default=True)
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Cost type name must be unique per company!'),
        ('code_uniq', 'unique(code, company_id)', 'Cost type code must be unique per company!'),
    ]