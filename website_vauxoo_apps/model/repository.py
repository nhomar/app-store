# coding: utf-8
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    coded by: nhomar@vauxoo.com
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, tools
from openerp.tools.safe_eval import safe_eval
import base64
import requests
import subprocess
from subprocess import CalledProcessError
import os
from urlparse import urlparse
import lxml.html
import lxml.etree
import re
import logging

_logger = logging.getLogger(__name__)

GITHUB_REPO = "https://api.github.com/repos/{name}"
GITHUB_COMMIT = "https://api.github.com/repos/{name}/commits"
GITHUB_CLONE = "https://{token}@{clone_url}"


class ResUsers(models.Model):
    _inherit = 'res.users'

    # pylint: disable=E0101,C0103
    def __init__(self, pool, cr):
        """ Override of __init__ to add access rights on
        display_employees_suggestions fields. Access rights are disabled by
        default, but allowed on some specific fields defined in
        self.SELF_{READ/WRITE}ABLE_FIELDS.
        """
        init_res = super(ResUsers, self).__init__(pool, cr)
        #  duplicate list to avoid modifying the original reference
        self.SELF_WRITEABLE_FIELDS = list(self.SELF_WRITEABLE_FIELDS)
        self.SELF_WRITEABLE_FIELDS.append('token')
        #  duplicate list to avoid modifying the original reference
        self.SELF_READABLE_FIELDS = list(self.SELF_READABLE_FIELDS)
        self.SELF_READABLE_FIELDS.append('token')
        return init_res

    token = fields.Char(string='Token on Github',
                        password=True,
                        help="For Apps store we need the token "
                        "in order to know the necesary information "
                        " to download your set of apps.")


class Repository(models.Model):
    _name = "repository.repository"
    _inherit = ['mail.thread']
    _order = "name desc, id desc"
    _description = "Repository to pull modules from"

    name = fields.Char(index=True,
                       readonly=True, states={'draft': [('readonly', False)]},
                       help="Use something like: vauxoo/addons-vauxoo, we "
                       "will get versions from branch names")
    local_path = fields.Char(index=True,
                             readonly=True, states={'draft': [('readonly',
                                                               False)]},
                             help="Local path where the code was downloaded.")
    git_description = fields.Char(index=True,
                                  readonly=True, states={'draft': [('readonly',
                                                                    False)]},
                                  help="Github description")
    url = fields.Char(index=True,
                      readonly=True,
                      help="Connect to your repository")
    sha = fields.Char(index=True,
                      readonly=True, states={'draft': [('readonly', False)]},
                      help="Last sha synced ")
    clone_url = fields.Char(index=True,
                            readonly=True, states={'draft': [('readonly',
                                                              False)]},
                            help="URL to clone this repository")
    ssh_url = fields.Char(index=True,
                          readonly=True, states={'draft': [('readonly',
                                                            False)]},
                          help="Url to clone with ssh")
    addons = fields.Char(index=True,
                         readonly=True,
                         states={'draft': [('readonly', False)]},
                         help="If odoo modules are not on root path "
                         "tell which is the folder to set. Will get versions "
                         "from branch names")

    module_ids = fields.One2many('repository.module', 'repository_id',
                                 string='Modules', help='Modules Imported')
    version = fields.Char(
                          change_default=True, required=True,
                          readonly=True, states={'draft': [('readonly',
                                                            False)]},
                          track_visibility='always',
                          default='8.0',
                          help="A version is a branch on this "
                          "repository.")
    user_id = fields.Many2one('res.users',
                              change_default=True, required=True,
                              readonly=True, states={'draft': [('readonly',
                                                                False)]},
                              track_visibility='always',
                              help='User with which github credentials '
                              'will be used from')
    last_json_answer = fields.Text(readonly=True,
                                   help="All the json in case you "
                                   "need any info")

    state = fields.Selection([('draft', 'Draft'),
                              ('open', 'Open'),
                              ('cancel', 'Cancelled')],
                             index=True,
                             readonly=True,
                             default='draft',)

    @api.multi
    def _log_event(self):
        # TODO: implement messages system
        return True

# Git section: All commands regarding to manipulation with git will be here.
# nothing regarding github it will be other section.

    @api.multi
    def git(self, cmd, cwd=False):
        """Execute git command cmd"""
        cmd = ['git'] + cmd
        _logger.info("git: %s", ' '.join(cmd))
        try:
            if cwd:
                return subprocess.check_output(cmd, cwd=self.local_path)
            else:
                return subprocess.check_output(cmd)
        except CalledProcessError as exc:
            _logger.error(exc.returncode)
            return None

    @api.multi
    def git_clone(self):
        """Execute git clone command over a known record"""
        token = self.user_id.token
        clone_url = self.clone_url and self.clone_url.replace('https://', '')
        cmd = ['clone', '-b', self.version,
               GITHUB_CLONE.format(token=token,
                                   clone_url=clone_url), self.local_path]
        self.git(cmd)

    @api.multi
    def git_pull(self):
        """Execute git clone command over a known record"""
        token = self.user_id.token
        clone_url = self.clone_url and self.clone_url.replace('https://', '')
        cmd = ['pull',
               GITHUB_CLONE.format(token=token,
                                   clone_url=clone_url)]
        self.git(cmd, cwd=1)

    @api.one
    def sync_repository(self):
        """Get repository info one time it is tested."""
        session = requests.Session()
        session.auth = (self.user_id.token, 'x-oauth-basic')
        res = session.get(GITHUB_REPO.format(name=self.name))
        res_commits = session.get(GITHUB_COMMIT.format(name=self.name))
        res_r = res.json()
        self.local_path = os.path.join(tools.config.filestore(self._cr.dbname),
                                       str(self.user_id.id),
                                       str(self.id))
        self.write({'url': res_r.get('html_url'),
                    'git_description': res_r.get('description'),
                    'clone_url': res_r.get('clone_url'),
                    'ssh_url': res_r.get('ssh_url'),
                    'last_json_answer': res_r,
                    'sha': res_commits.json()[0].get('sha')})

    @classmethod
    def clean_page(cls, path_mod, page):
        '''
        Cases attacked:
        - Converst oe_* classes on plain bootstrap classes.
        - Added Correct classes to images.

        Images:
        - Convert url images in readable images.
        '''
        all_files = re.findall('img .*?src="(.*?)"', page)
        for _file in all_files:
            if _file and urlparse(_file) and not urlparse(_file).scheme:
                page = page.replace(_file, '/'.join([path_mod, _file]))
        page = page.replace('oe_container', 'oe_container container ')
        root = lxml.etree.HTML(page)
        for img in root.iter("div"):
            cls_idet = img.get('class')
            if cls_idet.find('oe_span6') >= 0:
                img.set('class', '%s %s' % (cls_idet or '',
                                            ' col-md-6'))
        for img in root.iter("img"):
            cls_idet = img.get('class')
            img.set('class',
                    '%s %s' % (cls_idet or '',
                               ' img img-responsive img img-responsive mb16'))
        page = lxml.etree.tostring(root)
        return page

    def get_category(self, module):
        '''Look for the correct category to be setted.
        Due to we will have several ones in other module
        this part of the code make the map between the xml_ids
        and the text name on the Category.

        It returns the element prepared for the many2many value, here
        we will be adding elements necesary to set categories 1 by one.
        '''
        categories = []
        if module.application:
            c_id = self.env.ref(
                'website_vauxoo_apps.product_public_category_applications').id
            categories.append(c_id)
        return [(6, 0, categories)]

    @classmethod
    def get_descriptor(cls, des_file, module_id):
        '''Get securelly the descriptor reading directly the file in some
        servers it can bring errors.
        '''
        def get_main_image(des_file):
            des_folder = os.path.join(os.path.dirname(des_file),
                                      'static',
                                      'description')
            if os.path.isdir(des_folder):
                main_image = ''
                images = os.listdir(des_folder)
                icons = [i for i in images if i.find('icon.') >= 0]
                mimages = [i for i in images if i.find('main-image.') >= 0]
                if icons:
                    main_image = os.path.join(des_folder, icons[0])
                if mimages:
                    main_image = os.path.join(des_folder, mimages[0])
                return main_image and open(main_image).read() or False
            return ''
        try:
            descriptor = safe_eval(open(des_file).read())
            page_file = os.path.join(os.path.dirname(des_file),
                                     'static',
                                     'description',
                                     'index.html')
            main_image = get_main_image(des_file)
            desc_file_md = os.path.join(os.path.dirname(des_file),
                                        'README.md')
            desc_file_rst = os.path.join(os.path.dirname(des_file),
                                         'README.rst')
            if os.path.isfile(page_file):
                page = open(page_file, 'r')
                descriptor.update({'page': page.read()})
            descriptor.update({'main_image': main_image})
            if not descriptor.get('description'):
                # pylint: disable=fixme, line-too-long
                description_md = os.path.isfile(desc_file_md) and open(desc_file_md, 'r').read() or ''  # noqa
                description_rst = os.path.isfile(desc_file_rst) and open(desc_file_rst, 'r').read() or ''  # noqa
                description_full = '''{} \n\n {}'''.format(description_md,
                                                           description_rst)
                descriptor.update({'description': description_full})
            return descriptor
        except ValueError:
            _logger.error('Error %s', ValueError)
        return {}

    def prepare_modules(self):
        '''Just prepare the list of dics with module information
        be written on the repository information.
        '''
        addons = self.addons
        dir_modules = os.path.join(self.local_path,
                                   addons or '')
        res = os.listdir(dir_modules)
        modules = []
        for module in res:
            mod_info = os.path.join(dir_modules, module)
            if os.path.isdir(mod_info):
                _logger.info(
                    "Getting the folder for module %s", mod_info)
                des_file = os.path.join(mod_info, '__openerp__.py')
                _logger.info("Reading %s", des_file)
                if os.path.isfile(des_file) and \
                        (not module.startswith('.') or \
                        not module.startswith('_')):
                    descriptor = self.get_descriptor(des_file, module)
                    description = descriptor.get('description')
                    app = descriptor.get('application')
                    main_image = descriptor.get('main_image')
                    b64image = main_image and base64.encodestring(
                        main_image) or False
                    mod_dict = {'name': descriptor.get('name'),
                                'technical_name': module,
                                'version': descriptor.get('version'),
                                'summary': descriptor.get('summary'),
                                'description': description,
                                'page': descriptor.get('page'),
                                'application': app,
                                'image': b64image,
                                }
                    modules.append(mod_dict)
        return modules

    @api.multi
    def get_module_list(self):
        """Get repository info one time it is tested."""
        self.sync_repository()
        module_obj = self.env['repository.module']
        if not os.path.isdir(self.local_path):
            _logger.info("Clonning repository")
            self.git_clone()
        else:
            _logger.info("Pulling repository")
            self.git_pull()
        modules = self.prepare_modules()
        for module in modules:
            _logger.info("Creating %s", module)
            _logger.info("Updating module %s", module.get('name', 'False'))
            module.update({'repository_id': self.id})
            domain = [('repository_id', '=', self.id),
                      ('technical_name', '=', module.get('technical_name'))]
            module_exist = module_obj.search(domain)
            page = module.get('page') and module.get(
                'page') or module.get('description')
            module.pop('page')
            module.update({'website_description': page})
            if not module_exist:
                mo = module_obj.create(module)
                prod = self.get_product_id(mo)
                mo.product_id = prod.id
                url_img = '/appres/%s' % (mo.id)
                mo.product_id.website_description = self.clean_page(url_img,
                                                                    page)
            else:
                module_exist.write(module)
                prod = self.get_product_id(module_exist)
                module_exist.product_id = prod
                url_img = '/appres/%s' % (module_exist.id)
                module_exist.product_id.website_description = self.clean_page(
                    url_img, page)

    def get_product_id(self, module):
        ''' Create a product for a given dictionary module.'''
        product_obj = self.env['product.template']
        prod = {'name': module.name,
                'type': 'service',
                'default_code': '%s @ %s' % (module.technical_name,
                                             module.repository_id.id),
                'public_categ_ids': self.get_category(module),
                }
        if not module.product_id:
            product_id = product_obj.create(prod)
        else:
            module.product_id.write(prod)
            return module.product_id
        return product_id


class RepositoryModule(models.Model):
    _name = "repository.module"
    _inherit = ['mail.thread']
    _description = "Module on repository"

    name = fields.Char(string='Module Name',
                       index=True,
                       readonly=True,
                       help="Use something like: vauxoo/addons-vauxoo, we "
                       "will get versions from branch names")
    product_id = fields.Many2one('product.template')
    image_medium = fields.Binary(string='Main Image',
                          related='product_id.image_medium')
    local_path = fields.Char(string='Local Path',
                             related='repository_id.local_path')
    addons = fields.Char(string='Relative Folder',
                         related='repository_id.addons')
    version = fields.Char(string='Module Version', index=True,
                          readonly=True,
                          help="Version declared on the module descriptor")
    technical_name = fields.Char(string='Technical Name',
                                 index=True,
                                 readonly=True,
                                 help="Technical Name of the module")
    summary = fields.Char(string='Summary',
                          index=True,
                          readonly=True,
                          help="Summary on descriptor")
    published = fields.Boolean(string='Published',
                               readonly=True, track_visibility='always',
                               help="This module is published in the website")
    application = fields.Boolean(string='Application',
                                 readonly=True,
                                 help="This module is an application")
    repository_id = fields.Many2one('repository.repository',
                                    string='Repository',
                                    index=True,
                                    readonly=True,
                                    ondelete='cascade',
                                    help="Repository which this "
                                    "module is developed in")
    description = fields.Text(readonly=True,
                              help="Description on Module from the descriptor "
                              "file and/or README.md")
    website_description = fields.Html(string='Page',
                                      related='product_id.website_description',
                                      store=True,
                                      readonly=True,
                                      help="Website description to be used "
                                      "to sell. it is synced with index.html "
                                      "file on module.")
    state = fields.Selection([('draft', 'Draft'),
                              ('open', 'Open'),
                              ('cancel', 'Cancelled')],
                             string='Status',
                             index=True,
                             readonly=True,
                             default='draft',)
    _sql_constraints = [
        ('technical_name_unique', 'unique(repository_id, technical_name)',
         'Technical Name for a module in a repository must be unique!'),
    ]

    @api.one
    def publish_module(self):
        '''Make the module public'''
        self.published = True

    @api.one
    def unpublish_module(self):
        '''Make the module not public'''
        self.published = False
