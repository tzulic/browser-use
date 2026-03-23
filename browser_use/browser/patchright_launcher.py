"""Patchright stealth browser launcher.

Launches Chrome via patchright (a Playwright fork with anti-detection patches)
and exposes a CDP debug port for browser-use's CDP client to connect to.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from patchright.async_api import Browser, BrowserContext, Playwright

	from browser_use.browser.profile import BrowserProfile

logger = logging.getLogger(__name__)

# Reason: these args conflict with patchright's built-in stealth patches or are
# handled via patchright's own API parameters (user_data_dir= kwarg, proxy= kwarg).
# Passing them as raw Chrome flags AND via the API would cause double-handling.
FILTERED_ARGS = frozenset(
	{
		'--enable-automation',
		'--disable-extensions',
		'--disable-default-apps',
		'--disable-component-update',
		'--user-data-dir',
		'--proxy-server',
		'--proxy-bypass-list',
	}
)

# Module-level set of active handles for atexit cleanup.
# Handles remove themselves on close(), preventing accumulation.
_active_handles: set[PatchrightBrowserHandle] = set()
_atexit_registered = False


class PatchrightBrowserHandle:
	"""Holds patchright resources for cleanup. Internal only — not a Pydantic model."""

	def __init__(
		self,
		cdp_url: str,
		debug_port: int,
		playwright: Playwright,
		browser: Browser | BrowserContext,
		temp_dir: str | None = None,
	):
		self.cdp_url = cdp_url
		self.debug_port = debug_port
		self._playwright = playwright
		# Reason: launch_persistent_context() returns BrowserContext, not Browser.
		# Both have async close() that tears down the browser process.
		self._browser = browser
		self._temp_dir = temp_dir
		self._closed = False

	async def close(self) -> None:
		"""Shut down browser and Playwright driver. Safe to call multiple times."""
		if self._closed:
			return
		self._closed = True
		_active_handles.discard(self)
		try:
			await self._browser.close()
		except Exception:
			pass
		try:
			await self._playwright.stop()
		except Exception:
			pass
		# Clean up temp user data dir if we created one
		if self._temp_dir:
			shutil.rmtree(self._temp_dir, ignore_errors=True)
			self._temp_dir = None


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


def _ensure_atexit_registered() -> None:
	"""Register a single atexit handler that cleans up all active handles."""
	global _atexit_registered
	if _atexit_registered:
		return
	_atexit_registered = True

	def _cleanup_all():
		for handle in list(_active_handles):
			if not handle._closed:
				try:
					loop = asyncio.new_event_loop()
					loop.run_until_complete(handle.close())
					loop.close()
				except Exception:
					pass

	atexit.register(_cleanup_all)


async def launch_stealth_browser(profile: BrowserProfile) -> PatchrightBrowserHandle:
	"""Launch browser via patchright and return a handle with CDP URL.

	Does not mutate the profile object. Uses profile settings to configure
	the patchright launch but keeps all state on the returned handle.

	Args:
		profile: BrowserProfile with launch configuration.

	Returns:
		PatchrightBrowserHandle with cdp_url and cleanup method.
	"""
	from patchright.async_api import async_playwright

	# Reuse port-finding and CDP-polling utilities from the watchdog
	from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog

	pw = await async_playwright().start()

	# Pick a free port for CDP over TCP (alongside patchright's pipe)
	debug_port = LocalBrowserWatchdog._find_free_port()

	# Ensure user_data_dir is set — Chrome 136+ requires a non-default --user-data-dir
	# for --remote-debugging-port to work. BrowserProfile's validator creates one on
	# construction, but direct BrowserProfile() without model_post_init may leave it None.
	temp_dir = None
	if profile.user_data_dir is None:
		import tempfile

		temp_dir = tempfile.mkdtemp(prefix='patchright-stealth-')
		profile.user_data_dir = temp_dir
	user_data_dir = str(profile.user_data_dir)

	# Build args: inject debug port + pass through profile args (filtered)
	profile_args = profile.get_args()
	extra_args = _filter_args(profile_args)
	launch_args = [f'--remote-debugging-port={debug_port}', *extra_args]

	# Map proxy via pydantic model_dump instead of manual dict construction
	proxy_config = profile.proxy.model_dump(exclude_none=True) if (profile.proxy and profile.proxy.server) else None

	if profile.executable_path:
		logger.warning(
			'Custom executable_path with stealth=True: stealth patches only apply to '
			"patchright's bundled Chromium. Your custom binary may lack anti-detection patches."
		)

	logger.info('Launching with patchright stealth mode. Use stealth=False or --no-stealth to disable.')

	try:
		# Reason: always use launch_persistent_context because BrowserProfile's validator
		# guarantees user_data_dir is set (creates a temp dir if needed). Chrome 136+
		# requires a non-default --user-data-dir for --remote-debugging-port to work.
		browser = await pw.chromium.launch_persistent_context(
			user_data_dir=user_data_dir,
			headless=profile.headless if profile.headless is not None else True,
			args=launch_args,
			proxy=proxy_config,
			executable_path=str(profile.executable_path) if profile.executable_path else None,
		)
	except Exception as e:
		await pw.stop()
		error_msg = str(e).lower()
		if 'executable' in error_msg or ('browser' in error_msg and 'not found' in error_msg):
			raise RuntimeError("Patchright's patched Chromium is not installed. Run: patchright install chromium") from e
		raise

	# Wait for CDP to be ready on the TCP port
	cdp_url = await LocalBrowserWatchdog._wait_for_cdp_url(debug_port)

	handle = PatchrightBrowserHandle(
		cdp_url=cdp_url,
		debug_port=debug_port,
		playwright=pw,
		browser=browser,
		temp_dir=temp_dir,
	)

	# Track for atexit cleanup (single handler, handles remove themselves on close)
	_active_handles.add(handle)
	_ensure_atexit_registered()

	return handle
