import os, sys
import json
import falcon
import jwt
import six
from falcon_cors import CORS
import logging
from datetime import datetime, date, time, timedelta
import pprint
import collections
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker


logging.basicConfig(format='%(asctime)s %(levelname)s - %(name)s %(message)s',
                    datefmt='%b %d %H:%M:%S', stream=sys.stdout, level=logging.DEBUG)

logger = logging.getLogger('api')

sqla_engine = create_engine(
    	'postgresql://{}:{}@localhost/{}'.format(
    		os.environ.get('ECARTE_DBUSER'),
    		os.environ.get('ECARTE_DBPWD'),
    		os.environ.get('ECARTE_DB', 'ecarte')))
# This could be probably hidden inside DBMiddleware, but alembic may need it
DBSession = scoped_session(sessionmaker(bind=sqla_engine))


# Usual 'datetime is not JSON serializable' shit
def _custom_serialize(_self, media):
	class ExtEncoder(json.JSONEncoder):
		def default(self, obj):
			if isinstance(obj, (datetime, date, time)):
				return obj.isoformat(sep=' ', timespec='milliseconds')
			return json.JSONEncoder(self, obj)
	result = json.dumps(media, cls=ExtEncoder)
	if six.PY3 or not isinstance(result, bytes):
		return result.encode('utf-8')
	return result
# Why provide your own handler when you can monkey patch? ;)
falcon.media.JSONHandler.serialize = _custom_serialize


class AuthMiddleware(object):
	def process_request(self, req, resp):
		if req.path == '/api/login':
			return
		token = req.get_header('Authorization')
		if not token:
			raise falcon.HTTPUnauthorized(
				title='401 Unauthorized',
				description='Missing Authorization Header',
				challenges=None)
		payload = jwt.decode(token, key=APP_JWT_SECRET, algoriths=['HS256'])
		logger.debug('** payload:'+pprint.pformat(payload))


class DBMiddleware(object):
	def process_resource(self, req, resp, resource, params):
		resource.session = DBSession()

	def process_response(self, req, resp, resource, req_succeeded):
		if hasattr(resource, 'session'):
			if not req_succeeded:
				resource.session.rollback()
			DBSession.remove()


class FooResource(object):
	def on_get(self, req, resp):
		logger.debug('foo')
		resp.media = {'success': True, 'now': datetime.now()}

	def on_post(self, req, resp):
		logger.debug('post data:' + pprint.pformat(req.params))
		resp.media = {'success': True}


APP_JWT_SECRET = 'n4 POHYB3l 5KURwYsYnO]\/['

class LoginResource(object):
	def on_post(self, req, resp):
		from .admin import AccountSvc
		from .models import Account, Role
		#logger.info('/api/login | post data:' + pprint.pformat(req.params))
		usernm, pwd = req.params.get('username', ''), req.params.get('password', '')
		acc = AccountSvc(DBSession).authentificate(usernm, pwd)
		if acc is not None:
			payload = {
				'user_id': acc.id,
				'exp': datetime.utcnow() + timedelta(minutes=60),
				'extra': 'Danielle is a slut',
			}
			token = jwt.encode(payload, APP_JWT_SECRET, 'HS256')
			resp.media = {'authToken': token.decode('utf-8')}
		else:
			resp.media = {'error': 'User name or password do not match'}



#########################

cors = CORS(allow_origins_list=['http://localhost:8080', 'http://localhost:8081'])

app = falcon.API(middleware=[cors.middleware,
                             DBMiddleware(),
	                         AuthMiddleware()])
# Make POST params available in req.params
app.req_options.auto_parse_form_urlencoded = True

app.add_route('/api/foo', FooResource())
app.add_route('/api/login', LoginResource())
