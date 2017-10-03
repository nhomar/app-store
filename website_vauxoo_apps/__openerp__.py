# coding: utf-8
{
    'name': 'Apps Page',
    'category': 'Vauxoo Website',
    'version': '1.0',
    'summary': """
List of Vauxoo apps to show in website. A view per official app.
    """,
    'author': 'Vauxoo',
    'license': 'AGPL-3',
    'depends': [
        'website_variants_extra',  # <- In order to have available the variants
        'document',  # <- need manage attachments to deliver doc per module
        'product_attr_description',  # <- Necesary to pre-load descriptions
    ],
    'demo': [
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/ir_access.xml',
        'views/website_vauxoo_apps.xml',
        'views/repository_view.xml',
        'views/res_users_view.xml',
        'data/data.xml',
    ],
    'qweb': [],
    'installable': True,
    'application': True,
}
