"""Tests for patchright stealth browser launch integration."""

import asyncio
import shutil
import tempfile

import pytest
from pytest_httpserver import HTTPServer

from browser_use.browser import BrowserProfile, BrowserSession


@pytest.fixture(scope='session')
def http_server():
	"""Session-scoped HTTP server for stealth tests."""
	server = HTTPServer()
	server.start()
	server.expect_request('/hello').respond_with_data(
		'<html><body><h1>Hello</h1><button id="btn">Click me</button></body></html>',
		content_type='text/html',
	)
	yield server
	server.stop()


def test_stealth_default_is_true():
	"""stealth=True is the default on BrowserProfile."""
	profile = BrowserProfile()
	assert profile.stealth is True


def test_stealth_can_be_set_false():
	"""stealth can be explicitly set to False."""
	profile = BrowserProfile(stealth=False)
	assert profile.stealth is False


def test_stealth_in_browser_session_kwargs():
	"""BrowserSession accepts stealth as a keyword argument."""
	session = BrowserSession(stealth=False, headless=True)
	assert session.browser_profile.stealth is False


async def test_patchright_launcher_returns_cdp_url():
	"""launch_stealth_browser() returns a valid CDP URL and cleanup handle."""
	from browser_use.browser.patchright_launcher import launch_stealth_browser

	profile = BrowserProfile(headless=True)
	handle = await launch_stealth_browser(profile)
	try:
		assert handle.cdp_url.startswith('http://127.0.0.1:')
		assert handle.debug_port > 0

		# Verify CDP is actually responding
		import aiohttp

		async with aiohttp.ClientSession() as http_session:
			async with http_session.get(f'{handle.cdp_url}json/version') as resp:
				assert resp.status == 200
				data = await resp.json()
				assert 'webSocketDebuggerUrl' in data
	finally:
		await handle.close()


async def test_patchright_launcher_cleanup():
	"""Closing the handle shuts down browser and playwright."""
	from browser_use.browser.patchright_launcher import launch_stealth_browser

	profile = BrowserProfile(headless=True)
	handle = await launch_stealth_browser(profile)
	port = handle.debug_port
	await handle.close()

	# Verify CDP port is no longer responding
	import aiohttp

	await asyncio.sleep(0.5)
	try:
		async with aiohttp.ClientSession() as http_session:
			async with http_session.get(f'http://127.0.0.1:{port}/json/version', timeout=aiohttp.ClientTimeout(total=2)) as resp:
				assert False, 'CDP port still responding after close()'
	except (aiohttp.ClientError, asyncio.TimeoutError):
		pass  # Expected — port is closed


async def test_stealth_browser_session_e2e(http_server: HTTPServer):
	"""Full end-to-end: BrowserSession(stealth=True) launches via patchright, navigates, extracts DOM."""
	session = BrowserSession(stealth=True, headless=True)
	try:
		await session.start()
		await session.navigate_to(http_server.url_for('/hello'))
		state = await session.get_browser_state_summary(include_screenshot=False)
		text = state.dom_state.llm_representation()
		assert 'Hello' in text
	finally:
		await session.kill()


async def test_stealth_false_uses_subprocess(http_server: HTTPServer):
	"""stealth=False falls back to raw subprocess launch."""
	session = BrowserSession(stealth=False, headless=True)
	try:
		await session.start()
		await session.navigate_to(http_server.url_for('/hello'))
		state = await session.get_browser_state_summary(include_screenshot=False)
		text = state.dom_state.llm_representation()
		assert 'Hello' in text
	finally:
		await session.kill()


async def test_stealth_ignored_with_cdp_url(http_server: HTTPServer):
	"""When cdp_url is provided, stealth is ignored (remote connection)."""
	session1 = BrowserSession(stealth=True, headless=True)
	await session1.start()
	cdp_url = session1.cdp_url
	assert cdp_url is not None

	session2 = BrowserSession(cdp_url=cdp_url, stealth=True)
	await session2.start()
	await session2.navigate_to(http_server.url_for('/hello'))
	state = await session2.get_browser_state_summary(include_screenshot=False)
	assert state.dom_state is not None

	await session2.kill()
	await session1.kill()


async def test_stealth_with_user_data_dir(http_server: HTTPServer):
	"""Stealth mode works with user_data_dir (launch_persistent_context path)."""
	tmp_dir = tempfile.mkdtemp(prefix='browseruse-stealth-test-')
	session = BrowserSession(stealth=True, headless=True, user_data_dir=tmp_dir)
	try:
		await session.start()
		await session.navigate_to(http_server.url_for('/hello'))
		state = await session.get_browser_state_summary(include_screenshot=False)
		text = state.dom_state.llm_representation()
		assert 'Hello' in text
	finally:
		await session.kill()
		shutil.rmtree(tmp_dir, ignore_errors=True)
