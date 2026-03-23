"""Patchright stealth browser launcher.

Launches Chrome via patchright (a Playwright fork with anti-detection patches)
and exposes a CDP debug port for browser-use's CDP client to connect to.
"""

from __future__ import annotations

import atexit
import asyncio
import logging
import tempfile
from typing import TYPE_CHECKING

from patchright.async_api import async_playwright, Playwright, Browser, BrowserContext

if TYPE_CHECKING:
	from browser_use.browser.profile import BrowserProfile

logger = logging.getLogger(__name__)

# Args that conflict with patchright's built-in stealth patches or are handled
# via patchright's own API parameters (e.g. --user-data-dir is passed as user_data_dir=)
FILTERED_ARGS = frozenset({
	'--enable-automation',
	'--disable-extensions',
	'--disable-default-apps',
	'--disable-component-update',
	'--user-data-dir',
})


class PatchrightBrowserHandle:
	"""Holds patchright resources for cleanup. Internal only — not a Pydantic model."""

	def __init__(
		self,
		cdp_url: str,
		debug_port: int,
		playwright: Playwright,
		browser: Browser | BrowserContext,
	):
		self.cdp_url = cdp_url
		self.debug_port = debug_port
		self._playwright = playwright
		self._browser = browser  # Browser from launch(), BrowserContext from launch_persistent_context()
		self._closed = False

	async def close(self) -> None:
		"""Shut down browser and Playwright driver. Safe to call multiple times."""
		if self._closed:
			return
		self._closed = True
		try:
			await self._browser.close()
		except Exception:
			pass
		try:
			await self._playwright.stop()
		except Exception:
			pass


def _filter_args(args: list[str]) -> list[str]:
	"""Remove Chrome args that conflict with patchright's stealth patches."""
	filtered = []
	for arg in args:
		flag = arg.split('=', 1)[0]
		if flag in FILTERED_ARGS:
			logger.debug(f'Filtered conflicting arg: {arg}')
			continue
		filtered.append(arg)
	return filtered


async def launch_stealth_browser(profile: BrowserProfile) -> PatchrightBrowserHandle:
	"""Launch browser via patchright and return a handle with CDP URL.

	Args:
		profile: BrowserProfile with launch configuration.

	Returns:
		PatchrightBrowserHandle with cdp_url and cleanup method.
	"""
	# Reuse existing utilities from the watchdog
	from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog

	pw = await async_playwright().start()

	# Pick a free port for CDP over TCP (alongside patchright's pipe)
	debug_port = LocalBrowserWatchdog._find_free_port()

	# Ensure user_data_dir is set — get_args() requires it, and BrowserProfile's
	# field validator doesn't run for default None in Pydantic v2
	if profile.user_data_dir is None:
		profile.user_data_dir = tempfile.mkdtemp(prefix='patchright-stealth-')

	# Build args: inject debug port + pass through profile args (filtered)
	profile_args = profile.get_args()
	extra_args = _filter_args(profile_args)
	launch_args = [f'--remote-debugging-port={debug_port}', *extra_args]

	# Map proxy settings
	proxy_config = None
	if profile.proxy and profile.proxy.server:
		proxy_config = {'server': profile.proxy.server}
		if profile.proxy.bypass:
			proxy_config['bypass'] = profile.proxy.bypass
		if profile.proxy.username:
			proxy_config['username'] = profile.proxy.username
		if profile.proxy.password:
			proxy_config['password'] = profile.proxy.password

	# Warn if custom executable_path is set
	if profile.executable_path:
		logger.warning(
			'Custom executable_path with stealth=True: stealth patches only apply to '
			"patchright's bundled Chromium. Your custom binary may lack anti-detection patches."
		)

	logger.info('Launching with patchright stealth mode. Use stealth=False or --no-stealth to disable.')

	try:
		if profile.user_data_dir:
			# launch_persistent_context returns BrowserContext (not Browser)
			# Both have async close() — BrowserContext.close() also kills the browser
			actual_browser: Browser | BrowserContext = await pw.chromium.launch_persistent_context(
				user_data_dir=str(profile.user_data_dir),
				headless=profile.headless if profile.headless is not None else True,
				args=launch_args,
				proxy=proxy_config,
				executable_path=str(profile.executable_path) if profile.executable_path else None,
			)
		else:
			actual_browser = await pw.chromium.launch(
				headless=profile.headless if profile.headless is not None else True,
				args=launch_args,
				proxy=proxy_config,
				executable_path=str(profile.executable_path) if profile.executable_path else None,
			)
	except Exception as e:
		await pw.stop()
		error_msg = str(e).lower()
		if 'executable' in error_msg or ('browser' in error_msg and 'not found' in error_msg):
			raise RuntimeError(
				"Patchright's patched Chromium is not installed. "
				'Run: patchright install chromium'
			) from e
		raise

	# Wait for CDP to be ready on the TCP port
	cdp_url = await LocalBrowserWatchdog._wait_for_cdp_url(debug_port)

	handle = PatchrightBrowserHandle(
		cdp_url=cdp_url,
		debug_port=debug_port,
		playwright=pw,
		browser=actual_browser,
	)

	# Safety net: register atexit to clean up on unclean Python exit
	def _atexit_cleanup():
		if not handle._closed:
			try:
				loop = asyncio.new_event_loop()
				loop.run_until_complete(handle.close())
				loop.close()
			except Exception:
				pass

	atexit.register(_atexit_cleanup)

	return handle
