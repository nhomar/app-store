# coding: utf-8

from openerp import models, fields


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    description = fields.Html(string='Attribute Description', index=True,
                              help="Description on Module from the descriptor "
                              "file and/or README.md")