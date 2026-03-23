# Patchright Stealth Launch Integration

**Date**: 2026-03-23
**Status**: Approved
**Scope**: Make patchright the default browser launch engine for anti-detection stealth

## Problem

Browser-use launches Chrome via subprocess with `--remote-debugging-port` and various automation flags. Modern bot detection systems (Cloudflare, DataDome, Kasada, Akamai) detect this through:

- `Runtime.enable` CDP signal leak
- `Console.enable` CDP signal leak
- `--enable-automation` and other Chrome flags
- `navigator.webdriver === true`
- Disabled extensions and default apps
- Closed Shadow Root inaccessibility

Proxies solve IP-level detection but not browser fingerprinting. Patchright (a Playwright fork) patches these 6 detection vectors at the browser launch level.

## Solution

Replace the default browser launch mechanism with patchright. The CDP pipeline, DomService, Tools, CLI, watchdogs, and Agent remain unchanged — only how Chrome gets spawned changes.

### Architecture

```
Current flow:
  BrowserProfile → LocalBrowserWatchdog → subprocess(chrome) → CDP URL → BrowserSession.connect()

New default flow:
  BrowserProfile(stealth=True) → LocalBrowserWatchdog → PatchrightLauncher
    → patchright.chromium.launch(args=['--remote-debugging-port={port}'])
    → poll http://localhost:{port}/json/version → CDP URL
    → BrowserSession.connect()

Fallback flow:
  BrowserProfile(stealth=False) → LocalBrowserWatchdog → subprocess(chrome) → CDP URL → BrowserSession.connect()
```

## Design

### 1. BrowserProfile Configuration

Add one field to `BrowserProfile` in `browser_use/browser/profile.py`:

```python
stealth: bool = Field(
	default=True,
	description='Launch browser via patchright for anti-detection stealth. Set False to use raw Chrome subprocess launch.',
)
```

- `stealth=True` (default): patchright launches the browser
- `stealth=False`: current subprocess launch behavior (escape hatch)
- `stealth` is **ignored** when `cdp_url` is provided (remote connection bypasses launch entirely)

Update `BrowserSession.__init__` overloads to include `stealth` as a direct keyword argument.

### 2. Dependency

Patchright becomes a core dependency in `pyproject.toml`:

```toml
dependencies = [
	...
	"patchright>=1.0.0",
]
```

Not an optional extra — it's the default engine. Import at module level in `patchright_launcher.py`, not lazily.

### 3. CDP Port Extraction (Core Technical Challenge)

Playwright/patchright normally connects to the browser via `--remote-debugging-pipe` (a pipe transport), NOT a TCP debug port. This means `chromium.launch()` does not expose an HTTP CDP endpoint by default — and browser-use's `CDPClient` from `cdp-use` needs an HTTP/WebSocket URL.

**Solution**: Force a TCP debug port alongside patchright's pipe by injecting `--remote-debugging-port={port}` into the launch args.

```python
debug_port = _find_free_port()
args = [f'--remote-debugging-port={debug_port}', *other_args]
browser = await playwright.chromium.launch(args=args, ...)
```

This makes Chrome listen on both the pipe (for patchright internally) and the TCP port (for browser-use's CDP client). We use `_find_free_port()` (already exists in `local_browser_watchdog.py`) to pick a port, then poll `http://127.0.0.1:{port}/json/version` — exactly the same flow as the current subprocess launcher.

**Why this works**: Chrome supports `--remote-debugging-port` and `--remote-debugging-pipe` simultaneously. Patchright's patches (Runtime.enable bypass, etc.) are applied at the browser process level, so CDP connections via either transport benefit from the stealth patches.

**Risk**: If a future Chromium version drops dual-transport support, this breaks. Mitigation: pin patchright version in CI, test this in every CI run.

### 4. PatchrightLauncher Module

New file: `browser_use/browser/patchright_launcher.py`

```python
class PatchrightBrowserHandle:
	"""Holds patchright resources for cleanup. Not a Pydantic model — internal only."""

	def __init__(
		self,
		cdp_url: str,
		debug_port: int,
		playwright: Playwright,
		browser: Browser,
	):
		self.cdp_url = cdp_url
		self.debug_port = debug_port
		self._playwright = playwright  # Node.js driver process — must stay alive
		self._browser = browser        # Chrome process — managed by patchright
		self._closed = False

	async def close(self) -> None:
		"""Shut down browser and Playwright driver. Safe to call multiple times."""
		if self._closed:
			return
		self._closed = True
		try:
			await self._browser.close()
		except Exception:
			pass  # patchright manages the browser process; close() cascades to Chrome
		try:
			await self._playwright.stop()
		except Exception:
			pass  # Node.js driver cleanup; best-effort
```

Note: Playwright's Python API does not expose the browser PID. Cleanup relies entirely on `browser.close()` (which terminates Chrome) and `playwright.stop()` (which terminates the Node.js driver). No PID-based killing.

The main launch function:

```python
async def launch_stealth_browser(profile: BrowserProfile) -> PatchrightBrowserHandle:
	"""Launch browser via patchright, return handle with CDP URL and cleanup."""
```

**Lifecycle**: A new `Playwright` instance is created per launch. Accept the ~500ms Node.js driver startup cost — this is a launch-time operation, not per-action. The `Playwright` and `Browser` objects are stored on the handle and torn down together on close.

**Cleanup on crash**: If the Python process exits without calling `close()`, both the Chrome process and Node.js driver become orphans. Mitigation: register an `atexit` handler that calls `handle.close()` synchronously (via `asyncio.run()`). Since Playwright's Python API does not expose the browser PID, we cannot use PID-based cleanup. The `LocalBrowserWatchdog` already handles `BrowserStopEvent` → `handle.close()` for the normal path.

### 5. BrowserProfile → Patchright Option Mapping

| BrowserProfile field | Patchright option | Notes |
|---|---|---|
| `headless` | `headless` | Patchright's headless mode, not raw `--headless=new`. Stealth patches apply in both headful and headless, but anti-bot detection is harder to evade in headless. |
| `proxy.server` | `proxy.server` | Same format |
| `proxy.username` | `proxy.username` | Same format |
| `proxy.password` | `proxy.password` | Same format |
| `proxy.bypass` | `proxy.bypass` | Same format |
| `user_data_dir` | `user_data_dir` | Triggers `launch_persistent_context`. Receives the already-copied path from `BrowserProfile._copy_profile()` which runs in `model_post_init`. |
| `executable_path` | `executable_path` | **Warning**: user-provided Chrome binaries do NOT get patchright's stealth patches — those are baked into patchright's bundled Chromium. Log a warning when `executable_path` is set with `stealth=True`. |
| `extra_browser_args` | `args` | Passed as list |
| `disable_security` | `--disable-web-security` in args | Mapped to Chrome flag |
| `window_size` | `--window-size={w},{h}` in args | `detect_display_configuration()` results passed as Chrome args. Patchright does NOT have a `no_viewport` launch param — use `viewport=None` on context if needed. Let `window_size` from BrowserProfile take precedence. |

**Extension loading**: `--load-extension=path1,path2,...` from `BrowserProfile.get_args()` is passed through as a raw Chrome arg. Patchright (unlike stock Playwright) does NOT strip `--disable-extensions` — in fact, patchright removes that flag to enable extensions. So extension loading via `--load-extension` works the same as the current subprocess path. Verify in CI.

**Filtered args**: Args that conflict with patchright's patches are stripped:
- `--enable-automation` (patchright removes this)
- `--disable-extensions` (patchright enables extensions)
- `--disable-default-apps` (patchright enables default apps)
- `--disable-component-update` (patchright removes this)

### 6. CLI Integration

No new flags for the default case. One escape hatch:

```bash
browser-use --no-stealth open <url>    # Fall back to raw Chrome subprocess
```

Implemented as a global option in the CLI that sets `stealth=False` on the `BrowserProfile`. Verify no name collision with existing CLI flags.

### 7. Patchright Browser Installation

Patchright requires its patched Chromium binary. On first use or after install:

```bash
patchright install chromium
```

The `browser-use doctor` command gains a check for patchright's browser binary. If missing, it reports:

```
✗ patchright: Patched Chromium not installed
    Fix: patchright install chromium
```

### 8. Migration

Making `stealth=True` the default is a behavior change for existing users. On first stealth launch, log an info message:

```
INFO [BrowserSession] 🛡️ Launching with patchright stealth mode (default). Use stealth=False or --no-stealth to disable.
```

Users who have `executable_path` set to a custom Chrome get a warning:

```
WARNING [BrowserSession] Custom executable_path with stealth=True: stealth patches only apply to patchright's bundled Chromium. Your custom binary may not have anti-detection patches.
```

## What Doesn't Change

- `BrowserSession.connect()` — same CDP WebSocket flow
- `DomService` — same DOM snapshot extraction
- `Tools` / CLI commands — same `click`, `select`, `input`, `state`, `screenshot`
- Watchdogs (DOM, downloads, popups, security, about:blank) — same event bus
- `Agent` — same LLM loop
- Cloud browser mode — unaffected (cloud provides its own CDP URL)
- `cdp-use` — same typed CDP interface
- Remote CDP connections (`--cdp-url`, `--connect`) — bypass launch entirely, unaffected

## Testing

All tests use real objects, no mocking (per project conventions).

### Existing CI Suite

Run the full `tests/ci/` suite with `stealth=True` (the new default). If all 616 tests pass through patchright's browser, the integration is validated.

### New Tests

**`tests/ci/test_stealth_launch.py`**:
- `test_stealth_browser_launches` — patchright launches, CDP connects, `BrowserSession` gets a valid state
- `test_stealth_navigation` — navigate to a pytest-httpserver page, verify DOM extraction works
- `test_stealth_with_proxy` — launch with proxy settings, verify proxy is applied
- `test_stealth_with_user_data_dir` — launch with persistent context, verify user data dir is used
- `test_stealth_false_fallback` — `stealth=False` uses the old subprocess launch, verifying backward compat
- `test_stealth_ignored_with_cdp_url` — `stealth=True` + `cdp_url` set → stealth is ignored, remote connection used
- `test_stealth_extension_loading` — verify extensions load via `--load-extension` under patchright
- `test_stealth_cleanup_on_kill` — `BrowserStopEvent` tears down both browser and Playwright driver, no orphan processes

**`tests/ci/test_stealth_detection.py`**:
- `test_navigator_webdriver_is_false` — serve a page via pytest-httpserver that checks `navigator.webdriver`, verify it returns `false` (or `undefined`)
- `test_no_automation_flags` — serve a page that checks `window.chrome.runtime`, automation-related properties, verify clean
- `test_stealth_vs_raw_detection` — run the same detection page with `stealth=True` and `stealth=False`, verify stealth passes and raw fails

**Note on CDP-level leak testing**: `Runtime.enable` and `Console.enable` leaks are CDP protocol-level signals, not testable via in-page JavaScript alone. These are covered by patchright's own test suite (40+ tests). We rely on patchright's upstream CI for protocol-level stealth validation and test the integration boundary (launch → CDP connect → DOM extraction → actions) ourselves.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Patchright Chromium binary not installed | `browser-use doctor` check, clear error message on launch |
| Patchright version incompatibility | Pin minimum version, test in CI |
| Dual transport (pipe + TCP port) breaks in future Chromium | Pin patchright version, test in CI, fall back to subprocess on failure |
| `--load-extension` fails under patchright | Test extension loading explicitly in CI |
| Chrome args conflict with patchright patches | Filter known-conflicting args, log warnings |
| Patchright's patched browser breaks specific CDP commands | Existing CI suite (616 tests) catches this |
| Orphan processes on crash | `atexit` handler calls `handle.close()` as safety net |
| `executable_path` users lose stealth patches | Log warning explaining bundled Chromium has the patches |
| Default change surprises existing users | Info log on first stealth launch explaining the change |

## File Changes Summary

| File | Change |
|---|---|
| `browser_use/browser/profile.py` | Add `stealth: bool = True` field |
| `browser_use/browser/session.py` | Add `stealth` to `__init__` overloads |
| `browser_use/browser/patchright_launcher.py` | **New** — `PatchrightBrowserHandle`, `launch_stealth_browser()` |
| `browser_use/browser/watchdogs/local_browser_watchdog.py` | Branch on `profile.stealth` in launch handler, cleanup on stop |
| `browser_use/skill_cli/` | Add `--no-stealth` global option |
| `pyproject.toml` | Add `patchright>=1.0.0` to dependencies |
| `tests/ci/test_stealth_launch.py` | **New** — launch, fallback, cleanup, extension tests |
| `tests/ci/test_stealth_detection.py` | **New** — anti-detection verification tests |
