#!/usr/bin/env python
import unittest, os, sys, base64, datetime

# get app engine's resources
SDK_PATH = sys.argv.pop() or '../google_appengine'

print 'Using SDK path %s' % SDK_PATH

sys.path.insert(0, SDK_PATH)
import dev_appserver
dev_appserver.fix_sys_path()
from webapp2 import Request
from google.appengine.ext import testbed

from main import application
from settings import AUTH_SECRET
from models import Domain, UserData


class TestCase(unittest.TestCase):
  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_memcache_stub()
    self.auth_header= (
      'Authorization', 'Basic %s' % base64.b64encode(':' + AUTH_SECRET)
    )
    self.domain = 'foobar'
    self.uri_config = '/config/' + self.domain


  def tearDown(self):
    self.testbed.deactivate()


  def test_index(self):
    response = application.get_response('/')
    self.assertEqual(response.status_int, 200)
    self.assertEqual('banner.min.js' in response.text, True)


  def _create_config(self, body=None):
    """Helper to create a basic domain config.

    Returns the response object.
    """
    request = Request.blank(self.uri_config, headers=[self.auth_header])
    request.method = 'POST'
    request.body = body
    return request.get_response(application)


  def test_config_post(self):
    body = '"foo":"bar"'
    response = self._create_config(body=body)
    self.assertEqual(response.status_int, 204)
    self.assertEqual(response.body, '')

    body = '{"foo":"bar", "clickcount":0, "money":0.0, "status":0.0}'
    request = Request.blank(self.uri_config, headers=[self.auth_header])
    response = request.get_response(application)
    self.assertEqual(response.body, body)


  def test_config_get_fail(self):
    # nothing at root
    response = application.get_response('/config')
    self.assertEqual(response.status_int, 404)

    # basic auth fail
    response = application.get_response(self.uri_config)
    self.assertEqual(response.status_int, 401)

    # basic auth success, but domain doesn't exist yet
    request = Request.blank(self.uri_config, headers=[self.auth_header])
    response = request.get_response(application)
    self.assertEqual(response.status_int, 404)


  def test_config_get_success(self):
    self._create_config()
    request = Request.blank(self.uri_config, headers=[self.auth_header])
    response = request.get_response(application)
    self.assertEqual(response.status_int, 200)


  def test_config_delete(self):
    self._create_config()

    # get 204 on actual delete
    request = Request.blank(self.uri_config, headers=[self.auth_header])
    request.method = 'DELETE'
    response = request.get_response(application)
    self.assertEqual(response.status_int, 204)

    # still get 204 on delete after deletion
    response = request.get_response(application)
    self.assertEqual(response.status_int, 204)


  def test_c_get(self):
    # no GET for /c
    response = application.get_response('/c')
    self.assertEqual(response.status_int, 405)


  def test_c_post_noexist(self):
    self._create_config()

    uri = '/c?domain=dontexist'
    request = Request.blank(uri, headers=[self.auth_header])
    request.method = 'POST'
    response = request.get_response(application)
    self.assertEqual(response.status_int, 404)


  def _test_c_post(self, uri, body):
    """Helper to actually test posting to /c, depending on uri and body."""
    request = Request.blank(uri, headers=[self.auth_header])
    request.method = 'POST'
    response = request.get_response(application)
    self.assertEqual(response.status_int, 200)
    self.assertEqual(response.body, body)


  def test_c_post_nocount(self):
    self._create_config()

    # all values should still be 0 on firstvisit == false
    uri = '/c?domain=' + self.domain + '&firstvisit=false&from=inside'
    body = '{ "clickcount":0, "money":0.0, "status":0.0}'
    self._test_c_post(uri, body)

    # all values should still be 0 on from == outside
    uri = '/c?domain=' + self.domain + '&firstvisit=true&from=outside'
    self._test_c_post(uri, body)


  def test_c_post_count(self):
    self._create_config()

    # this should count
    uri = '/c?domain=' + self.domain + '&firstvisit=true&from=inside'
    body = '{ "clickcount":1, "money":0.001, "status":0.0000002}'
    self._test_c_post(uri, body)

    # this should count again
    body = '{ "clickcount":2, "money":0.002, "status":0.0000004}'
    self._test_c_post(uri, body)


  def test_domain_python_to_json_float(self):
    to_json = Domain(name='').python_to_json_float
    self.assertEqual(to_json(0), '0.0')
    self.assertEqual(to_json(0.), '0.0')
    self.assertEqual(to_json(4.50000), '4.5')
    self.assertEqual(to_json(1e-07), '0.0000001')


  def test_userdata_add(self):
    remote_addr = '127.0.0.1'
    http_user_agent = 'foo agent'
    domain = 'foobar'
    referer = None

    class Request(object): pass
    request = Request()
    request.headers = {'HTTP_USER_AGENT': http_user_agent}
    request.referer = referer
    os.environ['REMOTE_ADDR'] = remote_addr
    UserData.add(request, domain)

    user_data = UserData.query(UserData.domain==domain).get()
    self.assertEqual(user_data.remote_addr, remote_addr)
    self.assertEqual(user_data.http_user_agent, http_user_agent)
    self.assertEqual(user_data.referer, referer)


  def _create_static(self, uri, body, content_type=None):
    """Helper to create a static file

    Returns the response object.
    """
    headers = [self.auth_header]
    if content_type:
      headers.append(('Content-type', content_type))
    request = Request.blank(uri, headers=headers)
    request.method = 'POST'
    request.body = body
    return request.get_response(application)


  def _static_post(self, uri, body, content_type=None):
    response = self._create_static(
      uri=uri, body=body, content_type=content_type)
    self.assertEqual(response.status_int, 204)
    self.assertEqual(response.body, '')


  def test_static_post_banner_min_js(self):
    self._static_post(
      uri='/static/banner.min.js',
      body='a = 23;',
      content_type='application/javascript')


  def test_static_post_banner_center_html(self):
    response = self._static_post(
      uri='/static/banner-center.html',
      body='<html><body></body></html>',
      content_type='text/html')


  def _static_get(self, uri, body, content_type=None):
    response = application.get_response(uri)
    self.assertEqual(response.status_int, 404)

    self._create_static(uri=uri, body=body, content_type=content_type)
    response = application.get_response(uri)
    self.assertEqual(response.body, body)
    if content_type:
      self.assertEqual(response.content_type, content_type)
    else:
      self.assertEqual(response.content_type, 'text/plain')
    self.assertEqual(response.status_int, 200)


  def test_static_get_banner_center_html(self):
    self._static_get(
      uri='/static/banner-center.html',
      body='<html><body></body></html>',
      content_type='text/html')


  def test_static_banner_center_html_get(self):
    self._static_get(
      uri='/static/banner-center.html',
      body='<html><body></body></html>',
      content_type='text/html')


  def test_static_banner_plain_get(self):
    self._static_get(
      uri='/static/banner.plain',
      body='plain text',
      content_type='text/plain')

  def test_static_no_content_type_get(self):
    self._static_get(
      uri='/static/banner.no-content-type',
      body='plain text')


if __name__ == '__main__':
    unittest.main()
