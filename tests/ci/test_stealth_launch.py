"""Tests for patchright stealth browser launch integration."""

import asyncio
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
