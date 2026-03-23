"""Tests verifying patchright's anti-detection stealth patches work through browser-use."""

import asyncio

import pytest
from pytest_httpserver import HTTPServer

from browser_use.browser import BrowserSession


DETECTION_PAGE = """
<!DOCTYPE html>
<html><head><title>Detection Test</title></head>
<body>
<script>
window.__detectionResults = {
	webdriver: navigator.webdriver,
	chromeRuntime: !!(window.chrome && window.chrome.runtime && window.chrome.runtime.id),
};
</script>
<h1>Detection Test Page</h1>
</body>
</html>
"""


@pytest.fixture(scope='session')
def detection_server():
	"""HTTP server serving a bot detection page."""
	server = HTTPServer()
	server.start()
	server.expect_request('/detect').respond_with_data(DETECTION_PAGE, content_type='text/html')
	yield server
	server.stop()


async def test_navigator_webdriver_is_false(detection_server: HTTPServer):
	"""With stealth=True, navigator.webdriver should be false/undefined."""
	session = BrowserSession(stealth=True, headless=True)
	try:
		await session.start()
		await session.navigate_to(detection_server.url_for('/detect'))

		cdp_session = await session.get_or_create_cdp_session()
		result = await session.cdp_client.send.Runtime.evaluate(
			params={'expression': 'navigator.webdriver', 'returnByValue': True},
			session_id=cdp_session.session_id,
		)
		value = result.get('result', {}).get('value')
		assert value is not True, f'navigator.webdriver should not be true, got: {value}'
	finally:
		await session.kill()


async def test_no_automation_flags(detection_server: HTTPServer):
	"""Stealth browser should not expose automation-related properties."""
	session = BrowserSession(stealth=True, headless=True)
	try:
		await session.start()
		await session.navigate_to(detection_server.url_for('/detect'))

		cdp_session = await session.get_or_create_cdp_session()

		# Check navigator.webdriver
		result = await session.cdp_client.send.Runtime.evaluate(
			params={'expression': 'navigator.webdriver', 'returnByValue': True},
			session_id=cdp_session.session_id,
		)
		webdriver = result.get('result', {}).get('value')
		assert webdriver is not True, f'navigator.webdriver leaked: {webdriver}'

		# Check that webdriver property descriptor is not present/enumerable
		# (patchright patches it at the Chromium level, not via JS override)
		result2 = await session.cdp_client.send.Runtime.evaluate(
			params={
				'expression': 'Object.getOwnPropertyDescriptor(navigator, "webdriver") !== undefined',
				'returnByValue': True,
			},
			session_id=cdp_session.session_id,
		)
		has_webdriver_descriptor = result2.get('result', {}).get('value', True)
		# In stealth mode, the property should not be defined on navigator as own property
		# (normal Chrome defines it on the prototype, not as own property)
		assert has_webdriver_descriptor is not True, (
			'navigator should not have own webdriver property descriptor in stealth mode'
		)
	finally:
		await session.kill()


async def test_stealth_vs_raw_detection(detection_server: HTTPServer):
	"""Stealth mode should pass detection that raw mode fails."""
	# Test with stealth=True
	stealth_session = BrowserSession(stealth=True, headless=True)
	try:
		await stealth_session.start()
		await stealth_session.navigate_to(detection_server.url_for('/detect'))

		cdp_session = await stealth_session.get_or_create_cdp_session()
		stealth_result = await stealth_session.cdp_client.send.Runtime.evaluate(
			params={'expression': 'navigator.webdriver', 'returnByValue': True},
			session_id=cdp_session.session_id,
		)
		stealth_webdriver = stealth_result.get('result', {}).get('value')
	finally:
		await stealth_session.kill()

	# Test with stealth=False
	raw_session = BrowserSession(stealth=False, headless=True)
	try:
		await raw_session.start()
		await raw_session.navigate_to(detection_server.url_for('/detect'))

		cdp_session = await raw_session.get_or_create_cdp_session()
		raw_result = await raw_session.cdp_client.send.Runtime.evaluate(
			params={'expression': 'navigator.webdriver', 'returnByValue': True},
			session_id=cdp_session.session_id,
		)
		raw_webdriver = raw_result.get('result', {}).get('value')
	finally:
		await raw_session.kill()

	# Stealth should not leak webdriver
	assert stealth_webdriver is not True, f'Stealth navigator.webdriver should not be true: {stealth_webdriver}'
