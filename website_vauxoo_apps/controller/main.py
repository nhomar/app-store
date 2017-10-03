# coding: utf-8
from openerp import http
from openerp.http import request
import openerp
import hashlib
import werkzeug
import os
import base64
import logging

LOGGER = logging.getLogger(__name__)


class Apps(http.Controller):

    @http.route(['/appres',
                 '/appres/<model("repository.module"):module>/<string:image>',
                 ], type='http', auth="public", website=True)
    def appres(self, module=None, image=None, **kw):

        last_update = '__last_update'
        headers = [('Content-Type', 'image/png')]
        etag = request.httprequest.headers.get('If-None-Match')
        hashed_session = hashlib.md5(request.session_id).hexdigest()
        retag = hashed_session
        try:
            if not request.uid:
                request.uid = openerp.SUPERUSER_ID
            date = module[last_update]
            if hashlib.md5(date).hexdigest() == etag:
                return werkzeug.wrappers.Response(status=304)
            image_path = os.path.join(module.local_path,
                                      module.addons or '',
                                      module.technical_name,
                                      'static',
                                      'description',
                                      image and image or 'not_exist.png')
            retag = hashlib.md5(date).hexdigest()
            image_file = open(image_path)
            image_base64 = base64.b64encode(image_file.read())
            image_data = base64.b64decode(image_base64)
        except IOError as err:
            LOGGER.warning('Image %s does not exist %s or it '
                           'is not an image', image_path, err.message)
            return werkzeug.wrappers.Response(status=404)
        except AttributeError:
            LOGGER.warning('Your are trying to use and incorrect attribute.')
            return werkzeug.wrappers.Response(status=404)
        headers.append(('ETag', retag))
        headers.append(('Content-Length', len(image_data)))
        try:
            ncache = int(kw.get('cache'))
            msg = 'no-cache' if ncache == 0 else 'max-age=%s' % (ncache)
            headers.append(('Cache-Control', msg))
        # pylint: disable=W0703
        except Exception:
            pass
        return request.make_response(image_data, headers)
