"""NS Joy-Con Keyboard Mapper — CLI entry point.

Maps Nintendo Switch Joy-Con controller inputs to keyboard shortcuts.
Supports configurable key mappings via JSON config files.
Cross-platform: Windows and macOS.

Usage:
    python -m src                    # Run with default mappings
    python src/main.py               # Also supported
    python -m src --discover         # Calibrate button indices
    python -m src --config my.json   # Use custom config
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

# Ensure the project root is on sys.path so that `src` is importable
# as a package when running `python src/main.py` directly.
if __package__ is None:
    _project_root = str(Path(__file__).resolve().parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    __package__ = "src"

# Prevent SDL2 from merging Joy-Con L+R into a single combined device.
# Without this, SDL2 exclusively consumes Joy-Con R's HID report stream,
# making it impossible for the battery reader to receive any reports from R.
# With this set, both Joy-Cons remain independent Joystick devices and
# hidapi can concurrently read battery reports from each one.
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_COMBINE_JOY_CONS", "0")

# macOS: prevent SDL2 from installing its NSApplication subclass.
# SDLApplication doesn't implement -macOSVersion, which Tk 9.0+ calls,
# causing a crash on GUI startup. We don't need video — only joystick —
# so the dummy video driver is safe and avoids the Cocoa hook.
if sys.platform == "darwin":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from .battery_reader import BatteryReader
from .config_loader import load_config, get_profile, get_platform_config_path, USER_CONFIG_PATH
from .gui import MainWindow
from .joycon_reader import (
    find_joycon,
    find_joycons,
    detect_connection_mode,
    run_discover_mode,
    run_polling_loop,
    wait_for_reconnection,
)
from .keep_alive import KeepAliveManager
from .key_mapper import KeyMapper
from .os_utils.permission import (
    has_required_permissions,
    get_permission_warning,
    request_macos_accessibility_prompt,
    open_macos_privacy_pane,
)
from .tray_icon import create_tray_icon, run_tray

logger = logging.getLogger(__name__)


def list_controls(config: dict) -> None:
    """Print all configured button/direction mappings."""
    from .constants import MODE_LABELS

    active_profile = config.get("active_profile", "single_right")
    profile_label = MODE_LABELS.get(active_profile, active_profile)
    print(f"\nActive profile: {profile_label} ({active_profile})")

    mappings = config.get("mappings", {})

    print("\n=== Button Mappings ===")
    for btn_name, mapping in mappings.get("buttons", {}).items():
        action = mapping["action"]
        if action == "combination":
            target = "+".join(mapping["keys"])
        else:
            target = mapping.get("key", "?")
        print(f"  {btn_name:8s} [{action:11s}] → {target}")

    print("\n=== Stick Direction Mappings ===")
    for direction, mapping in mappings.get("stick_directions", {}).items():
        action = mapping["action"]
        if action == "combination":
            target = "+".join(mapping["keys"])
        else:
            target = mapping.get("key", "?")
        print(f"  {direction:8s} [{action:11s}] → {target}")

    print(f"\nDeadzone: {config.get('deadzone', 0.15)}")
    print(f"Stick mode: {config.get('stick_mode', '4dir')}")
    print(f"Poll interval: {config.get('poll_interval', 0.01) * 1000:.0f}ms")

    profiles = config.get("profiles", {})
    if profiles:
        print("\nAvailable profiles:")
        for mode in profiles:
            label = MODE_LABELS.get(mode, mode)
            marker = " (active)" if mode == active_profile else ""
            print(f"  {label} ({mode}){marker}")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="NS Joy-Con Keyboard Mapper — Map controller buttons to keyboard shortcuts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py --discover       # Calibrate button indices first
  python src/main.py                  # Run with default mappings
  python src/main.py --config custom.json  # Use custom config
  python src/main.py --deadzone 0.2   # Override deadzone
  python src/main.py --list-controls  # Show current mappings
        """,
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to JSON config file (default: built-in defaults)",
    )
    parser.add_argument(
        "--discover", "-d",
        action="store_true",
        help="Discovery mode: print raw button/axis values for calibration",
    )
    parser.add_argument(
        "--deadzone",
        type=float,
        default=None,
        help="Override deadzone value (0.0 to 0.99)",
    )
    parser.add_argument(
        "--joystick", "-j",
        type=int,
        default=None,
        help="Specific joystick device index to use",
    )
    parser.add_argument(
        "--list-controls", "-l",
        action="store_true",
        help="List all control names and current mappings, then exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"NSJC {__import__('src.constants', fromlist=['__version__']).__version__}",
    )
    parser.add_argument(
        "--no-admin-warn",
        action="store_true",
        help="Suppress administrator/permission warning",
    )

    return parser


def _get_pairing_instructions() -> str:
    """Return platform-specific Joy-Con pairing instructions."""
    if sys.platform == "darwin":
        return (
            "\nPairing instructions (macOS):\n"
            "  1. System Settings → Bluetooth\n"
            "  2. Hold the small pairing button on the Joy-Con rail for 3 seconds\n"
            "  3. Lights will flash rapidly — select 'Joy-Con (R)' or 'Joy-Con (L)' in Bluetooth list\n"
            "  4. Run --discover to verify connection"
        )
    else:
        return (
            "\nPairing instructions:\n"
            "  1. Windows Settings → Bluetooth & devices → Add device\n"
            "  2. Hold the small pairing button on the Joy-Con rail for 3 seconds\n"
            "  3. Lights will flash rapidly — select 'Joy-Con R' in Bluetooth list\n"
            "  4. Run --discover to verify connection"
        )


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
    ]
    if args.verbose:
        log_path = Path(__file__).resolve().parent.parent / "nsjc.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    # Single-instance check — must come BEFORE pygame init / GUI creation,
    # otherwise a duplicate launch will briefly grab the joystick / show a
    # second menu-bar icon before exiting.
    from .single_instance import acquire as _acquire_single_instance
    if not _acquire_single_instance():
        msg = "JoyHarness 已经在运行中。请检查菜单栏图标 (macOS) 或系统托盘 (Windows)。"
        logger.warning("Another instance is already running; exiting.")
        print(msg)
        if sys.platform == "darwin":
            try:
                _show_already_running_dialog()
            except Exception:
                logger.exception("already-running dialog failed")
        sys.exit(0)

    # Permission check
    if not args.no_admin_warn and not has_required_permissions():
        print(get_permission_warning())
        if sys.platform == "darwin":
            # Trigger the system Accessibility prompt (one-shot per install)
            # so the user sees Apple's official "Open System Settings" sheet.
            request_macos_accessibility_prompt()
            # Also show our own dialog with detailed Chinese guidance,
            # since the menu-bar app has no visible window otherwise.
            _show_macos_permission_dialog()

    # Load config — prefer platform-specific user config if it exists
    config_path = args.config
    if config_path is None:
        config_path = get_platform_config_path()
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}")
        sys.exit(1)

    # Override deadzone if specified
    if args.deadzone is not None:
        if not 0.0 <= args.deadzone < 1.0:
            print(f"Invalid deadzone: {args.deadzone} (must be 0.0 to 0.99)")
            sys.exit(1)
        config["deadzone"] = args.deadzone

    # List controls mode
    if args.list_controls:
        list_controls(config)
        return

    # Discover mode
    if args.discover:
        run_discover_mode(args.joystick)
        return

    # Normal mode — selectively init only the pygame subsystems we need.
    # pygame.init() starts ALL subsystems (video, audio, font, mixer, etc.)
    # which on macOS causes SDL2 to install Cocoa event handlers that
    # interfere with tkinter's window management (blocking minimize button).
    # We only need display (for event pump), joystick, and implicitly timer.
    pygame.display.init()
    pygame.joystick.init()

    joycons = find_joycons()
    if not joycons:
        # Don't block here — start the UI immediately and let the polling
        # thread wait for the controller in the background. Otherwise the
        # menu-bar / window never appears and the app looks frozen.
        print("No Joy-Con detected at startup; will keep scanning in background.")
        print(_get_pairing_instructions())
    else:
        for side, j in joycons:
            print(f"Controller [{side}]: {j.get_name()} "
                  f"buttons={j.get_numbuttons()} axes={j.get_numaxes()}")

    # Detect connection mode and load the appropriate profile
    connection_mode = detect_connection_mode() if joycons else "single_right"
    profile = get_profile(config, connection_mode)
    profile_mappings = profile.get("mappings", config.get("mappings", {}))
    config["mappings"] = profile_mappings
    config["active_profile"] = connection_mode

    from .constants import MODE_LABELS
    profile_label = MODE_LABELS.get(connection_mode, connection_mode)
    print(f"Connection mode: {profile_label} ({connection_mode})")
    print(f"Deadzone: {config['deadzone']}, Stick mode: {config['stick_mode']}")

    # Restore KNOWN_APPS from saved config
    from .window_switcher import set_known_apps
    known_apps = config.get("known_apps")
    if known_apps:
        set_known_apps(known_apps)

    key_mapper = KeyMapper(config, mode=connection_mode)
    stop_event = threading.Event()

    # Initialize WindowCycler with selected apps from config
    selected_apps = config.get("selected_apps")
    if selected_apps:
        key_mapper._window_cycler.app_names = selected_apps

    # Start battery reader
    battery_reader = BatteryReader(stop_event)
    battery_reader.start()

    # Start keep-alive manager (read enabled state from config)
    keep_alive_manager = KeepAliveManager(stop_event)
    keep_alive_manager.set_enabled(config.get("keep_alive_enabled", True))

    # Create GUI first so we can pass its mode-change callback to polling loop
    gui = MainWindow(
        key_mapper, key_mapper._window_cycler, config, stop_event,
        connection_mode=connection_mode,
        battery_reader=battery_reader,
        keep_alive_manager=keep_alive_manager,
    )
    key_mapper.set_tk_root(gui.root)

    # Start polling loop in background thread (after GUI so callback is available)
    poll_thread = threading.Thread(
        target=_run_polling,
        args=(joycons, key_mapper, config, stop_event, gui.update_connection_mode),
        daemon=True,
    )
    poll_thread.start()

    # Start tray icon in background thread (Windows only)
    # macOS: pystray would conflict with Tk's runloop; we use NSStatusBar
    # via PyObjC instead (see _setup_macos_menu_bar below).
    icon = None
    tray_thread = None
    if sys.platform != "darwin":
        icon = create_tray_icon(stop_event, on_show_window=gui.show)
        tray_thread = threading.Thread(target=run_tray, args=(icon,), daemon=True)
        tray_thread.start()

    status_bar = None
    if sys.platform == "darwin":
        status_bar = _setup_macos_menu_bar(gui, battery_reader, stop_event)
        # Launch hidden — user reopens via menu bar
        gui.root.withdraw()
        print("Menu-bar app active. Click the menu-bar icon to interact.")
    else:
        print("GUI and tray active. Close window or right-click tray to quit.")

    # Run GUI in main thread (blocks until window closed)
    gui.run()

    # Cleanup
    stop_event.set()
    if icon is not None:
        icon.stop()
    poll_thread.join(timeout=2.0)
    battery_reader.join(timeout=2.0)
    keep_alive_manager.join(timeout=2.0)
    key_mapper.release_all()
    pygame.joystick.quit()
    pygame.display.quit()
    print("Clean exit. All keys released.")


def _run_polling(
    joycons,
    key_mapper: KeyMapper,
    config: dict,
    stop_event: threading.Event,
    on_mode_change=None,
) -> None:
    """Run polling loop in a background thread, handling exceptions.

    Args:
        joycons: list[(side, Joystick)] from find_joycons(). May be empty —
            the thread will then poll find_joycons() until at least one
            Joy-Con appears.
    """
    try:
        # If no controller was attached at launch, wait for one here
        # (off the main thread, so the GUI / menu bar stays responsive).
        if not joycons:
            logger.info("Polling thread: waiting for Joy-Con to connect…")
            while not stop_event.is_set():
                joycons = find_joycons()
                if joycons:
                    logger.info("Polling thread: %d controller(s) connected", len(joycons))
                    if on_mode_change is not None:
                        try:
                            on_mode_change(detect_connection_mode())
                        except Exception:
                            logger.exception("on_mode_change after first connect failed")
                    break
                time.sleep(2.0)
            if stop_event.is_set():
                return
        run_polling_loop(joycons, key_mapper, config, stop_event, on_mode_change=on_mode_change)
    except Exception:
        logger.exception("Polling thread error")


def _show_already_running_dialog() -> None:
    """macOS-only: show a small Tk dialog telling the user another instance is running."""
    import tkinter as tk
    import ttkbootstrap as ttk

    win = ttk.Window(themename="darkly")
    win.title("JoyHarness")
    win.resizable(False, False)
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass

    container = ttk.Frame(win, padding=24)
    container.pack(fill="both", expand=True)

    ttk.Label(
        container, text="JoyHarness 已经在运行",
        font=("Helvetica", 16, "bold"),
    ).pack(anchor="w")

    ttk.Label(
        container,
        text=(
            "已有一个 JoyHarness 进程在后台运行。\n"
            "请通过菜单栏图标 (顶部) 进行操作；\n"
            "如需重新启动，请先在菜单栏中选择「退出」。"
        ),
        font=("Helvetica", 11),
        justify="left",
    ).pack(anchor="w", pady=(8, 16))

    ttk.Button(
        container, text="知道了",
        bootstyle="primary",
        command=win.destroy, width=14,
    ).pack(anchor="e")

    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"+{x}+{y}")
    win.lift()
    win.focus_force()
    win.mainloop()


def _show_macos_permission_dialog() -> None:
    """Show a startup dialog explaining required macOS permissions.

    Displayed once at launch when permissions are missing. Offers buttons
    that open the relevant System Settings panes directly.
    """
    import tkinter as tk
    import ttkbootstrap as ttk

    win = ttk.Window(themename="darkly")
    win.title("JoyHarness 需要授权")
    win.resizable(False, False)
    # Bring this transient dialog to the front of all apps
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass

    container = ttk.Frame(win, padding=24)
    container.pack(fill="both", expand=True)

    ttk.Label(
        container, text="首次运行需要授权",
        font=("Helvetica", 16, "bold"),
    ).pack(anchor="w")

    ttk.Label(
        container,
        text=(
            "JoyHarness 需要以下两项 macOS 权限才能正常工作：\n\n"
            "  1.  辅助功能 — 用于模拟键盘按键\n"
            "  2.  输入监控 — 用于触发系统语音输入 (ZR 键)\n\n"
            "点击下方按钮直接打开对应的设置面板，把\n"
            "JoyHarness 加入并勾选，然后退出再重新启动。"
        ),
        font=("Helvetica", 11),
        justify="left",
    ).pack(anchor="w", pady=(8, 16))

    btn_row = ttk.Frame(container)
    btn_row.pack(fill="x")

    def open_acc():
        open_macos_privacy_pane("Accessibility")

    def open_input():
        open_macos_privacy_pane("ListenEvent")

    ttk.Button(
        btn_row, text="打开「辅助功能」",
        bootstyle="primary",
        command=open_acc, width=18,
    ).pack(side="left", padx=(0, 8))

    ttk.Button(
        btn_row, text="打开「输入监控」",
        bootstyle="info",
        command=open_input, width=18,
    ).pack(side="left", padx=(0, 8))

    ttk.Button(
        btn_row, text="我已授权，继续",
        bootstyle="secondary",
        command=win.destroy, width=14,
    ).pack(side="right")

    # Center on screen
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"+{x}+{y}")
    win.lift()
    win.focus_force()
    win.mainloop()


def _setup_macos_menu_bar(gui, battery_reader, stop_event):
    """Create the NSStatusBar menu-bar item and wire its callbacks.

    The icon updates from a periodic root.after() poll that reads
    battery_reader's thread-safe state. All GUI mutations stay on the
    Tk main thread, so we don't need extra locking.
    """
    from .macos_status_bar import MacStatusBar
    from .constants import __version__

    def show_window():
        gui.show()

    def open_settings():
        gui.show()
        # Reuse the existing settings opener on the main window
        try:
            gui._open_settings()
        except Exception:
            logger.exception("open settings from menu bar failed")

    def show_about():
        gui.show()
        try:
            _show_about_dialog(gui.root, __version__)
        except Exception:
            logger.exception("about dialog failed")

    def quit_app():
        logger.info("Quit requested from menu bar")
        try:
            from .config_loader import save_config
            save_config(gui._config)
        except Exception:
            logger.exception("save_config on quit failed")
        stop_event.set()
        # Schedule destroy on main thread to break out of mainloop cleanly
        gui.root.after(0, gui.root.destroy)

    sb = MacStatusBar(
        on_show_window=show_window,
        on_open_settings=open_settings,
        on_about=show_about,
        on_quit=quit_app,
    )

    def refresh():
        if stop_event.is_set():
            return
        try:
            state = battery_reader.get_state()  # {"L": (status, pct), "R": (status, pct)}
            connected = False
            charging = False
            low = False
            parts = []
            for side in ("R", "L"):
                if side not in state:
                    continue
                status, pct = state[side]
                if status == "unknown" or pct < 0:
                    parts.append(f"{side}: 未知")
                    continue
                connected = True
                if status == "charging":
                    charging = True
                    parts.append(f"{side}: {pct}% 充电中")
                else:
                    parts.append(f"{side}: {pct}%")
                    if pct <= 25:
                        low = True
            if not parts:
                parts = ["未连接"]
            sb.set_state(connected=connected, charging=charging, low_battery=low)
            sb.set_battery_text("电量  " + "   ".join(parts))
        except Exception:
            logger.exception("status bar refresh failed")
        finally:
            gui.root.after(2000, refresh)

    gui.root.after(500, refresh)
    return sb


def _show_about_dialog(parent, version: str) -> None:
    """A small custom 'About' dialog with the app icon and version."""
    import tkinter as tk
    import ttkbootstrap as ttk
    from PIL import Image, ImageTk
    from .gui import _icon_path

    win = ttk.Toplevel(parent)
    win.title("关于 JoyHarness")
    win.resizable(False, False)
    win.transient(parent)

    container = ttk.Frame(win, padding=24)
    container.pack(fill="both", expand=True)

    # Icon
    photo = None
    icon_path = _icon_path("AppIcon-1024.png")
    if icon_path is not None:
        try:
            img = Image.open(icon_path).convert("RGBA").resize((128, 128), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img, master=win)
            ttk.Label(container, image=photo).pack(pady=(0, 12))
        except Exception:
            pass

    ttk.Label(
        container, text="JoyHarness",
        font=("Helvetica", 22, "bold"),
    ).pack()

    ttk.Label(
        container, text=f"版本 {version}",
        font=("Helvetica", 12),
    ).pack(pady=(2, 12))

    ttk.Label(
        container, text="Joy-Con 键盘映射 + 语音触发工具",
        font=("Helvetica", 11),
    ).pack()

    ttk.Label(
        container, text="macOS 菜单栏模式运行",
        font=("Helvetica", 10),
        bootstyle="secondary",
    ).pack(pady=(2, 16))

    ttk.Button(
        container, text="确定",
        bootstyle="primary",
        command=win.destroy, width=12,
    ).pack()

    # Hold a reference so the image survives garbage collection
    if photo is not None:
        win._about_photo = photo  # type: ignore[attr-defined]

    # Center on parent
    win.update_idletasks()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    ww = win.winfo_width()
    wh = win.winfo_height()
    win.geometry(f"+{px + (pw - ww) // 2}+{py + (ph - wh) // 2}")
    win.lift()
    win.focus_force()


if __name__ == "__main__":
    main()
