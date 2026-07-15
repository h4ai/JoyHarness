# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

JoyHarness maps Nintendo Switch Joy-Con (Bluetooth) input to keyboard shortcuts on Windows 11 and macOS 13+. It auto-detects which Joy-Con(s) are connected (`single_left` / `single_right` / `dual`) and hot-swaps the active key-mapping profile accordingly.

## Common Commands

```bash
# Install (platform-aware: keyboard on Windows, pynput+PyObjC on macOS)
pip install -r requirements.txt

# Run
python -m src                      # normal launch
python -m src --discover           # raw button/axis indices for calibration
python -m src --list-controls      # dump current mappings and exit
python -m src --config <file>      # alternate config file
python -m src --deadzone 0.2       # override stick deadzone
python -m src --joystick <idx>     # force a specific SDL2 joystick device index
python -m src --verbose            # debug logging → also writes nsjc.log
python -m src --no-admin-warn      # suppress permission/admin warning at startup

# Standalone calibration walkthrough (interactive)
python calibrate.py

# macOS launcher (double-clickable)
./start.command

# Build macOS .app bundle (entry point: pyinstaller_entry.py)
pyinstaller joyvoice.spec          # outputs dist/JoyHarness.app
```

There is no test runner configured; `tests/` contains ad-hoc scripts (e.g. `python tests/test_keys.py`) used for manual verification of keyboard output, reconnection, etc. `tests/` is gitignored.

## Architecture

### Threading model (entry point: `src/main.py`)

`main()` orchestrates four cooperating threads coordinated by a single `threading.Event` (`stop_event`):

1. **Main thread** — Tk GUI mainloop (`gui.MainWindow`, styled with `ttkbootstrap` "darkly" theme). On macOS the window starts hidden (`LSUIElement`) and is reopened from a PyObjC `NSStatusBar` item (`macos_status_bar.py`) set up in `_setup_macos_menu_bar`; on Windows a `pystray` tray icon runs in its own thread.
2. **Polling thread** (`_run_polling` → `joycon_reader.run_polling_loop`) — pygame event pump at ~100 Hz; translates raw button/axis state into events fed to `KeyMapper`. If no Joy-Con is present at launch, it loops on `find_joycon()` so the UI can still appear.
3. **BatteryReader thread** (`battery_reader.py`) — direct hidapi reads bypass SDL2 to get charge state for L and R independently.
4. **KeepAliveManager thread** (`keep_alive.py`) — periodic zero-strength rumble to prevent Joy-Con sleep.

Single-instance enforcement runs before pygame/GUI init: `single_instance.py` binds a loopback TCP socket (port 51842); a second launch detects the bound port and exits immediately.

Cleanup is uniform: `stop_event.set()` → `join()` all threads → `key_mapper.release_all()` (critical — otherwise held modifier keys leak into the OS).

### Key translation pipeline

`joycon_reader` → raw pygame button/axis indices → `joystick_handler` (circular deadzone + 4dir/8dir detection) → `key_mapper.KeyMapper` (the core engine) → action dispatchers → `keyboard_output` (Windows: `keyboard` lib; macOS: `pynput`) **or** `window_switcher` + `switcher_overlay` (Win32 / Quartz+AppleScript) **or** `subprocess` (for `exec` action).

Action types live in `constants.VALID_ACTIONS`: `tap`, `hold`, `auto` (short=tap / long=hold, optional `repeat` for autorepeat), `combination` (chord), `sequence` (modifier+key, optional `repeat`), `window_switch`, `macro` (multi-step, optionally gated by `if_window`), `exec` (shell command — used on macOS for HID-only system shortcuts like Mission Control).

The `auto` action has two optional fine-grained fields: `short_keys` (list — fires a combo on short press instead of `key`) and `long_keys` (list — single element = press-and-hold until release; multiple elements = one-shot chord on long press).

### Connection-mode profiles

Three profiles share one config file. `joycon_reader.detect_connection_mode()` picks one of `single_right` / `single_left` / `dual`; `config_loader.get_profile()` returns the matching mappings; `KeyMapper` is built with that mode. Each mode has its own button-name set (see `MAPPABLE_BUTTONS_BY_MODE` in `constants.py`) — e.g. left mode exposes `L/ZL/Minus/Capture/LStick`, right mode exposes `R/ZR/Plus/Home/RStick`. Reconnects re-detect the mode and the GUI's `update_connection_mode` callback swaps the active profile live.

### Hardware indices (`src/constants.py`)

pygame button/axis indices are SDL2-version-dependent. Both **right** and **left** Joy-Con indices are calibrated (right: 2026-04-09; left: 2026-05-07 on macOS SDL 2.28.4). `dual` mode indices still need verification with `--discover` or `calibrate.py`. `BUTTON_NAMES_BY_MODE` / `BUTTON_INDICES_BY_MODE` are the lookup tables consumed by everything downstream — change indices here and the rest follows.

### Config resolution (`src/config_loader.py`)

Load order: `--config` arg → `config/user.json` → `config/user-{macos,windows}.json` → built-in `DEFAULT_CONFIGS`. `user.json` is gitignored (per-user). The platform presets are committed.

Key top-level config fields beyond mappings: `deadzone` (float), `stick_mode` (`"4dir"` or `"8dir"`), `poll_interval` (seconds), `long_press_threshold` (seconds, default 0.25), `switch_scroll_interval` (ms), `keep_alive_enabled` (bool), `selected_apps` (list, for `window_switch`), `known_apps` (list, persisted app names).

### Critical environment setup (top of `src/main.py`)

Two `os.environ.setdefault` calls run **before** `import pygame` and must stay there:

- `SDL_JOYSTICK_HIDAPI_COMBINE_JOY_CONS=0` — keeps L+R as separate devices so `BatteryReader` can read each one's HID reports concurrently. Without this, SDL2 monopolizes the R stream.
- `SDL_VIDEODRIVER=dummy` (macOS only) — prevents SDL2 from installing its NSApplication subclass, which lacks `-macOSVersion` and crashes Tk 9.0+ on startup. Joystick subsystem still works.

Also: `main()` calls `pygame.display.init()` + `pygame.joystick.init()` instead of `pygame.init()` to avoid SDL2 hooking Cocoa events that break Tk's window minimize button on macOS.

## Platform Notes (macOS)

- Requires **Accessibility** and **Input Monitoring** permissions; `os_utils/permission.py` checks them and `_show_macos_permission_dialog` opens the right Settings pane.
- Some system shortcuts (Mission Control, Launchpad) only respond to real HID events, not synthesized `pynput` keystrokes — bind them via the `exec` action (e.g. `{"action": "exec", "command": ["open", "-a", "Mission Control"]}`).
- Process names for `if_window` / `window_switch` are case-sensitive and locale-sensitive (e.g. `微信`, not `WeChat`).
- `window_switch` only sees windows in the current Space.
- On macOS SDL2, **SL and Minus** buttons on the left Joy-Con do not generate events — do not map them in `single_left` mode.
- SL/SR side buttons are unreliable on macOS via SDL2.

## When Editing

- Adding a new action type → register in `VALID_ACTIONS` (constants), implement dispatch in `key_mapper.py`, validate in `config_loader.py`.
- Adding a new mappable button → update both `BUTTON_NAMES_*` and `MAPPABLE_BUTTONS_BY_MODE` for the relevant mode, then expose it in `gui.py`/`settings_window.py`.
- Modifier-leak bugs almost always trace back to a code path that bypasses `KeyMapper.release_all()` — check shutdown and mode-swap paths first.
