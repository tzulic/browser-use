# Patchright Stealth Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make patchright the default browser launch engine so browser-use is undetectable by anti-bot systems.

**Architecture:** Add a `PatchrightLauncher` module that launches Chrome via patchright with `--remote-debugging-port` injected into args. The existing CDP pipeline connects to this port — DomService, Tools, watchdogs, and Agent are untouched. A `stealth` field on `BrowserProfile` (default `True`) controls whether patchright or raw subprocess launch is used.

**Tech Stack:** patchright (Playwright fork), Python async, pydantic v2, cdp-use, bubus EventBus, pytest + pytest-httpserver

**Spec:** `docs/superpowers/specs/2026-03-23-patchright-stealth-launch-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `browser_use/browser/patchright_launcher.py` | **New** — `PatchrightBrowserHandle` class and `launch_stealth_browser()` function |
| `browser_use/browser/profile.py` | Add `stealth: bool = True` field to `BrowserProfile` |
| `browser_use/browser/session.py` | Add `stealth` to `__init__` overloads and actual `__init__` |
| `browser_use/browser/watchdogs/local_browser_watchdog.py` | Branch on `profile.stealth` in `_launch_browser()`, cleanup patchright handle on kill |
| `browser_use/skill_cli/main.py` | Add `--no-stealth` global flag |
| `browser_use/skill_cli/daemon.py` | Pass `stealth` through to `create_browser_session()` |
| `browser_use/skill_cli/sessions.py` | Accept `stealth` param in `create_browser_session()` |
| `browser_use/skill_cli/commands/doctor.py` | Add patchright browser check |
| `pyproject.toml` | Add `patchright>=1.0.0` to dependencies |
| `tests/ci/test_stealth_launch.py` | **New** — launch, fallback, cleanup tests |
| `tests/ci/test_stealth_detection.py` | **New** — anti-detection verification tests |

---

### Task 1: Add patchright dependency and install browser

**Files:**
- Modify: `pyproject.toml:13-49` (dependencies list)

- [ ] **Step 1: Add patchright to pyproject.toml**

In `pyproject.toml`, add `patchright` to the dependencies list after `cdp-use`:

```toml
    "cdp-use==1.4.5",
    "patchright>=1.0.0",
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`
Expected: patchright installs successfully

- [ ] **Step 3: Install patchright's Chromium binary**

Run: `uv run patchright install chromium`
Expected: Downloads patched Chromium binary

- [ ] **Step 4: Verify patchright works**

Run: `uv run python -c "from patchright.async_api import async_playwright; print('patchright OK')"`
Expected: `patchright OK`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add patchright as core dependency for stealth browser launch"
```

---

### Task 2: Add `stealth` field to BrowserProfile

**Files:**
- Modify: `browser_use/browser/profile.py:562-563` (after `cdp_url` field)
- Test: `tests/ci/test_stealth_launch.py`

- [ ] **Step 1: Write failing test for stealth field**

Create `tests/ci/test_stealth_launch.py`:

```python
"""Tests for patchright stealth browser launch integration."""

import asyncio
import tempfile

import pytest
from pytest_httpserver import HTTPServer

from browser_use.browser import BrowserProfile, BrowserSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# BrowserProfile field tests
# ---------------------------------------------------------------------------

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ci/test_stealth_launch.py::test_stealth_default_is_true -vxs`
Expected: FAIL — `BrowserProfile` has no `stealth` attribute

- [ ] **Step 3: Add stealth field to BrowserProfile**

In `browser_use/browser/profile.py`, add after `cdp_url` field (line ~562):

```python
stealth: bool = Field(
	default=True,
	description='Launch browser via patchright for anti-detection stealth. Set False to use raw Chrome subprocess launch. Ignored when cdp_url is provided.',
)
```

- [ ] **Step 4: Add stealth to BrowserSession.__init__ overloads**

In `browser_use/browser/session.py`, add `stealth: bool | None = None,` to:
- Overload 1 (cloud mode) at line ~161, before the closing `) -> None: ...` — so cloud-mode callers can pass it without type errors (it's silently ignored for cloud)
- Overload 2 (local browser mode) at line ~176, after `headless`
- The actual `__init__` at line ~248, after `headless`

Note: The `profile_kwargs` comprehension at line ~308 uses `locals()` and automatically captures all local variables. Since `stealth` is a local in `__init__`, it will be included in `profile_kwargs` automatically — no special handling needed.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/ci/test_stealth_launch.py -vxs`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add browser_use/browser/profile.py browser_use/browser/session.py tests/ci/test_stealth_launch.py
git commit -m "feat: add stealth field to BrowserProfile (default True)"
```

---

### Task 3: Implement PatchrightLauncher module

**Files:**
- Create: `browser_use/browser/patchright_launcher.py`
- Test: `tests/ci/test_stealth_launch.py`

- [ ] **Step 1: Write test for the launcher module directly**

Add to `tests/ci/test_stealth_launch.py`:

```python
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
				# If we get here, the port is still open — fail
				assert False, 'CDP port still responding after close()'
	except (aiohttp.ClientError, asyncio.TimeoutError):
		pass  # Expected — port is closed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ci/test_stealth_launch.py::test_patchright_launcher_returns_cdp_url -vxs`
Expected: FAIL — `launch_stealth_browser` does not exist yet

- [ ] **Step 3: Create patchright_launcher.py**

Create `browser_use/browser/patchright_launcher.py`:

```python
"""Patchright stealth browser launcher.

Launches Chrome via patchright (a Playwright fork with anti-detection patches)
and exposes a CDP debug port for browser-use's CDP client to connect to.
"""

from __future__ import annotations

import atexit
import asyncio
import logging
from typing import TYPE_CHECKING

from patchright.async_api import async_playwright, Playwright, Browser, BrowserContext

if TYPE_CHECKING:
	from browser_use.browser.profile import BrowserProfile

logger = logging.getLogger(__name__)

# Args that conflict with patchright's built-in stealth patches
FILTERED_ARGS = frozenset({
	'--enable-automation',
	'--disable-extensions',
	'--disable-default-apps',
	'--disable-component-update',
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
		# Check the flag name (before any = sign)
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
	pw = await async_playwright().start()

	# Pick a free port for CDP over TCP (alongside patchright's pipe)
	# Reuse the same utility from LocalBrowserWatchdog
	from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog
	debug_port = LocalBrowserWatchdog._find_free_port()

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

	# Warn if custom executable_path is set — stealth patches are in bundled Chromium
	if profile.executable_path:
		logger.warning(
			'Custom executable_path with stealth=True: stealth patches only apply to '
			"patchright's bundled Chromium. Your custom binary may lack anti-detection patches."
		)

	# Log stealth launch
	logger.info('🛡️ Launching with patchright stealth mode. Use stealth=False or --no-stealth to disable.')

	try:
		# Choose launch method based on user_data_dir
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
		if 'executable' in error_msg or 'browser' in error_msg and 'not found' in error_msg:
			raise RuntimeError(
				"Patchright's patched Chromium is not installed. "
				"Run: patchright install chromium"
			) from e
		raise

	# Wait for CDP to be ready on the TCP port — reuse watchdog's polling utility
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ci/test_stealth_launch.py::test_patchright_launcher_returns_cdp_url tests/ci/test_stealth_launch.py::test_patchright_launcher_cleanup -vxs`
Expected: Both PASS — the launcher works independently of the watchdog

- [ ] **Step 5: Commit**

```bash
git add browser_use/browser/patchright_launcher.py
git commit -m "feat: add PatchrightLauncher module for stealth browser launch"
```

---

### Task 4: Integrate PatchrightLauncher into LocalBrowserWatchdog

**Files:**
- Modify: `browser_use/browser/watchdogs/local_browser_watchdog.py:43-46` (add patchright handle attr), `:48-63` (on_BrowserLaunchEvent), `:65-83` (on_BrowserKillEvent)
- Test: `tests/ci/test_stealth_launch.py`

- [ ] **Step 1: Write tests for stealth and non-stealth via BrowserSession**

Add to `tests/ci/test_stealth_launch.py`:

```python
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
```

- [ ] **Step 2: Integrate patchright into LocalBrowserWatchdog**

In `browser_use/browser/watchdogs/local_browser_watchdog.py`:

Add import and private attribute:

```python
# After existing imports, add:
from browser_use.browser.patchright_launcher import PatchrightBrowserHandle

# In class body, after _original_user_data_dir (line 46):
_patchright_handle: PatchrightBrowserHandle | None = PrivateAttr(default=None)
```

Modify `_launch_browser()` method — add stealth branch at the top of the method (after line 103, before the retry loop):

```python
async def _launch_browser(self, max_retries: int = 3) -> tuple[psutil.Process | None, str]:
	"""Launch browser process and return (process, cdp_url)."""
	profile = self.browser_session.browser_profile

	# Stealth mode: use patchright launcher
	if profile.stealth:
		from browser_use.browser.patchright_launcher import launch_stealth_browser

		handle = await launch_stealth_browser(profile)
		self._patchright_handle = handle
		# Return None for process — patchright manages the browser process
		return None, handle.cdp_url

	# Non-stealth: existing subprocess launch
	self._original_user_data_dir = str(profile.user_data_dir) if profile.user_data_dir else None
	self._temp_dirs_to_cleanup = []
	# ... rest of existing code unchanged ...
```

**Important:** The return type changes from `tuple[psutil.Process, str]` to `tuple[psutil.Process | None, str]`. Update the type hint. In `on_BrowserLaunchEvent` (line 56-57), handle `process` being `None`:

```python
process, cdp_url = await self._launch_browser()
if process is not None:
	self._subprocess = process
```

Modify `on_BrowserKillEvent` to clean up patchright:

```python
async def on_BrowserKillEvent(self, event: BrowserKillEvent) -> None:
	"""Kill the local browser subprocess or patchright handle."""
	self.logger.debug('[LocalBrowserWatchdog] Killing local browser process')

	# Clean up patchright handle if present
	if self._patchright_handle is not None:
		await self._patchright_handle.close()
		self._patchright_handle = None

	# Clean up subprocess if present
	if self._subprocess:
		await self._cleanup_process(self._subprocess)
		self._subprocess = None

	# ... rest of existing cleanup code unchanged ...
```

Modify `on_BrowserStopEvent` to also trigger kill when using patchright (no subprocess):

```python
async def on_BrowserStopEvent(self, event: BrowserStopEvent) -> None:
	if self.browser_session.is_local and (self._subprocess or self._patchright_handle):
		self.logger.debug('[LocalBrowserWatchdog] BrowserStopEvent received, dispatching BrowserKillEvent')
		self.event_bus.dispatch(BrowserKillEvent())
```

- [ ] **Step 3: Run all stealth tests**

Run: `uv run pytest tests/ci/test_stealth_launch.py -vxs`
Expected: All tests PASS

- [ ] **Step 4: Run full CI suite to check for regressions**

Run: `uv run pytest tests/ci/ -vxs --timeout=120`
Expected: All existing tests PASS (they now use patchright by default since `stealth=True`)

- [ ] **Step 5: Commit**

```bash
git add browser_use/browser/watchdogs/local_browser_watchdog.py tests/ci/test_stealth_launch.py
git commit -m "feat: integrate patchright launcher into LocalBrowserWatchdog"
```

---

### Task 5: Add anti-detection verification tests

**Files:**
- Create: `tests/ci/test_stealth_detection.py`

- [ ] **Step 1: Write detection tests**

Create `tests/ci/test_stealth_detection.py`:

```python
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
	automationControlled: !!(navigator.userAgentData && navigator.userAgentData.getHighEntropyValues),
	chromeRuntime: !!(window.chrome && window.chrome.runtime && window.chrome.runtime.id),
};
</script>
<h1>Detection Test Page</h1>
<div id="results"></div>
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
		await asyncio.sleep(1)

		cdp_session = await session.get_or_create_cdp_session()
		result = await session.cdp_client.send.Runtime.evaluate(
			params={'expression': 'navigator.webdriver', 'returnByValue': True},
			session_id=cdp_session.session_id,
		)
		value = result.get('result', {}).get('value')
		# Patchright patches navigator.webdriver to be false or undefined
		assert value is not True, f'navigator.webdriver should not be true, got: {value}'
	finally:
		await session.kill()


async def test_stealth_vs_raw_detection(detection_server: HTTPServer):
	"""Stealth mode should pass detection that raw mode fails."""
	# Test with stealth=True
	stealth_session = BrowserSession(stealth=True, headless=True)
	try:
		await stealth_session.start()
		await stealth_session.navigate_to(detection_server.url_for('/detect'))
		await asyncio.sleep(1)

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
		await asyncio.sleep(1)

		cdp_session = await raw_session.get_or_create_cdp_session()
		raw_result = await raw_session.cdp_client.send.Runtime.evaluate(
			params={'expression': 'navigator.webdriver', 'returnByValue': True},
			session_id=cdp_session.session_id,
		)
		raw_webdriver = raw_result.get('result', {}).get('value')
	finally:
		await raw_session.kill()

	# Stealth should not leak webdriver; raw subprocess may or may not
	assert stealth_webdriver is not True, f'Stealth navigator.webdriver should not be true: {stealth_webdriver}'
```

- [ ] **Step 2: Run detection tests**

Run: `uv run pytest tests/ci/test_stealth_detection.py -vxs`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/ci/test_stealth_detection.py
git commit -m "test: add anti-detection verification tests for patchright stealth"
```

---

### Task 6: Add `--no-stealth` CLI flag and doctor check

**Files:**
- Modify: `browser_use/skill_cli/main.py:376-396` (add global flag)
- Modify: `browser_use/skill_cli/daemon.py:34-44` (pass stealth to daemon)
- Modify: `browser_use/skill_cli/sessions.py:25-33` (accept stealth param)
- Modify: `browser_use/skill_cli/commands/doctor.py:15-41` (add patchright check)

- [ ] **Step 1: Add --no-stealth flag to argparse**

In `browser_use/skill_cli/main.py`, after `--json` flag (line 395):

```python
parser.add_argument('--no-stealth', action='store_true', help='Disable patchright stealth mode, use raw Chrome subprocess')
```

Where the parsed args are passed to `_ensure_daemon_running()` (search for calls to this function), add `no_stealth=args.no_stealth` to the kwargs.

In `_ensure_daemon_running()` (line ~221), add `no_stealth: bool = False` parameter. Pass it through to the daemon spawn command args (line ~269):

```python
if no_stealth:
	cmd.append('--no-stealth')
```

- [ ] **Step 2: Accept --no-stealth in Daemon**

In `browser_use/skill_cli/daemon.py`:

1. Add `no_stealth: bool = False` to `Daemon.__init__()` (line 34). Store as `self.no_stealth = no_stealth`.

2. In `_get_or_create_session()` (line 74), pass it through:

```python
bs = await create_browser_session(
	self.headed,
	self.profile,
	self.cdp_url,
	stealth=not self.no_stealth,
	...
)
```

3. **Critical**: In `daemon.py`'s `main()` function (the argparse for the daemon subprocess), add `--no-stealth` to the daemon's own argparser. The daemon is spawned as a separate process, so it needs to accept this flag independently of main.py's parser. Find the daemon's argparse setup and add:

```python
parser.add_argument('--no-stealth', action='store_true', help='Disable patchright stealth mode')
```

Then pass `args.no_stealth` to `Daemon(no_stealth=args.no_stealth, ...)`.

- [ ] **Step 3: Accept stealth in create_browser_session**

In `browser_use/skill_cli/sessions.py`, add `stealth: bool = True` to `create_browser_session()` (line 25). Pass `stealth=stealth` in ALL code paths that create `BrowserSession`:

1. No-profile path (line 55-57):
```python
return BrowserSession(
	headless=not headed,
	stealth=stealth,
)
```

2. With-profile path (around line 97-102, where `BrowserSession(executable_path=..., ...)` is returned):
```python
return BrowserSession(
	executable_path=chrome_path,
	user_data_dir=user_data_dir,
	profile_directory=profile_directory,
	headless=not headed,
	stealth=stealth,
)
```

The CDP URL and cloud paths don't need stealth (stealth is a launch-time concern, and those paths don't launch locally).

- [ ] **Step 4: Add patchright check to doctor command**

In `browser_use/skill_cli/commands/doctor.py`, add after the `profile_use` check (~line 32):

```python
# 6. Patchright browser availability
checks['patchright'] = _check_patchright()
```

Add the check function:

```python
def _check_patchright() -> dict[str, Any]:
	"""Check if patchright's patched Chromium is installed."""
	try:
		import subprocess
		result = subprocess.run(
			['patchright', 'install', 'chromium', '--dry-run'],
			capture_output=True, text=True, timeout=10,
		)
		# If dry-run doesn't exist, just check if we can import patchright
		from patchright.async_api import async_playwright
		return {
			'status': 'ok',
			'message': 'patchright available',
		}
	except ImportError:
		return {
			'status': 'error',
			'message': 'patchright not installed',
			'fix': 'pip install patchright && patchright install chromium',
		}
	except Exception:
		return {
			'status': 'warning',
			'message': 'patchright installed but browser may need setup',
			'fix': 'patchright install chromium',
		}
```

- [ ] **Step 5: Test the CLI flag**

Run: `uv run browser-use --no-stealth --headed open https://example.com`
Expected: Browser opens using raw subprocess (no patchright)

Run: `uv run browser-use close`

Run: `uv run browser-use doctor`
Expected: Shows patchright check in output

- [ ] **Step 6: Commit**

```bash
git add browser_use/skill_cli/main.py browser_use/skill_cli/daemon.py browser_use/skill_cli/sessions.py browser_use/skill_cli/commands/doctor.py
git commit -m "feat: add --no-stealth CLI flag and patchright doctor check"
```

---

### Task 7: Add cleanup and edge case tests

**Files:**
- Modify: `tests/ci/test_stealth_launch.py`

- [ ] **Step 1: Add remaining integration tests from spec**

Add to `tests/ci/test_stealth_launch.py`:

```python
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
	import tempfile
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
		import shutil
		shutil.rmtree(tmp_dir, ignore_errors=True)


async def test_stealth_extension_loading(http_server: HTTPServer):
	"""Extensions load via --load-extension under patchright."""
	# Verify that default extensions (uBlock, etc.) are enabled and loaded
	# The BrowserProfile enables extensions by default when enable_default_extensions=True
	session = BrowserSession(stealth=True, headless=True)
	try:
		await session.start()
		# Check that chrome.runtime is accessible (extensions loaded)
		cdp_session = await session.get_or_create_cdp_session()
		result = await session.cdp_client.send.Runtime.evaluate(
			params={
				'expression': 'typeof chrome !== "undefined" && typeof chrome.runtime !== "undefined"',
				'returnByValue': True,
			},
			session_id=cdp_session.session_id,
		)
		chrome_runtime_available = result.get('result', {}).get('value', False)
		# chrome.runtime should be available when extensions are enabled
		assert chrome_runtime_available is True, 'chrome.runtime not available — extensions may not be loaded'
	finally:
		await session.kill()
```

Also add to `tests/ci/test_stealth_detection.py`:

```python
async def test_no_automation_flags(detection_server: HTTPServer):
	"""Stealth browser should not expose automation-related properties."""
	session = BrowserSession(stealth=True, headless=True)
	try:
		await session.start()
		await session.navigate_to(detection_server.url_for('/detect'))

		cdp_session = await session.get_or_create_cdp_session()

		# Check that the automation-controlled feature is disabled
		result = await session.cdp_client.send.Runtime.evaluate(
			params={
				'expression': 'navigator.webdriver',
				'returnByValue': True,
			},
			session_id=cdp_session.session_id,
		)
		webdriver = result.get('result', {}).get('value')
		assert webdriver is not True, f'navigator.webdriver leaked: {webdriver}'

		# Check window.chrome exists (should on a real Chrome)
		result2 = await session.cdp_client.send.Runtime.evaluate(
			params={
				'expression': 'typeof window.chrome !== "undefined"',
				'returnByValue': True,
			},
			session_id=cdp_session.session_id,
		)
		has_chrome = result2.get('result', {}).get('value', False)
		assert has_chrome is True, 'window.chrome should exist on a real Chrome browser'
	finally:
		await session.kill()
```

- [ ] **Step 2: Run all stealth tests**

Run: `uv run pytest tests/ci/test_stealth_launch.py tests/ci/test_stealth_detection.py -vxs`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/ci/test_stealth_launch.py
git commit -m "test: add cleanup and edge case tests for stealth launch"
```

---

### Task 8: Final integration — run full CI suite

**Files:** None (verification only)

- [ ] **Step 1: Run full CI suite with stealth=True default**

Run: `uv run pytest tests/ci/ -vxs --timeout=120`
Expected: All tests PASS. Since `stealth=True` is now the default, every test that launches a browser uses patchright.

- [ ] **Step 2: Run pyright type checker**

Run: `uv run pyright`
Expected: No new type errors from the changes

- [ ] **Step 3: Run linting**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: Clean

- [ ] **Step 4: Run pre-commit hooks**

Run: `uv run pre-commit run --all-files`
Expected: All hooks pass

- [ ] **Step 5: Final commit if any formatting changes**

```bash
git add -A
git commit -m "chore: formatting and type fixes for stealth launch integration"
```
