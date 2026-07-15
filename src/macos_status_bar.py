"""macOS menu-bar (NSStatusBar) integration for JoyVoice.

Why PyObjC instead of pystray:
- pystray on macOS calls NSApplication.run() which conflicts with
  Tk's mainloop and pegs the CPU at ~100%.
- Tk has already initialized NSApplication for us. We just attach an
  NSStatusItem to the existing shared NSApplication and drive its menu
  from a Tk after-loop. No second runloop, no thread contention.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _resource_dir() -> Path:
    """Return assets/icons directory in both dev and PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / "icons"
    return Path(__file__).resolve().parent.parent / "assets" / "icons"


class MacStatusBar:
    """A menu-bar item driven by NSStatusBar.

    The status item is created on the main thread (where Tk lives). The
    menu callbacks run on the main thread too — pyobjc dispatches them
    via the NSApplication runloop that Tk pumps for us.
    """

    def __init__(
        self,
        on_show_window: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_about: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        # Imported lazily so the file is importable on non-mac platforms
        # (we never instantiate this class outside macOS).
        import objc
        from AppKit import (
            NSStatusBar, NSImage, NSMenu, NSMenuItem,
            NSApplication, NSApp,
        )
        from Foundation import NSObject

        self._objc = objc
        self._AppKit_NSImage = NSImage
        self._AppKit_NSMenu = NSMenu
        self._AppKit_NSMenuItem = NSMenuItem

        # Make sure NSApplication exists (Tk normally creates it; this is
        # defensive in case we're called very early).
        NSApplication.sharedApplication()

        self._on_show_window = on_show_window
        self._on_open_settings = on_open_settings
        self._on_about = on_about
        self._on_quit = on_quit

        # Build a tiny ObjC target object that forwards selectors to
        # our Python callbacks. We define it at runtime so this module
        # stays importable without AppKit at module-load time.
        class _Target(NSObject):
            def initWithCallbacks_(self, callbacks):
                self = objc.super(_Target, self).init()
                if self is None:
                    return None
                self._cb = callbacks
                return self

            def showWindow_(self, sender):
                try:
                    self._cb["show"]()
                except Exception:
                    logger.exception("show window callback failed")

            def openSettings_(self, sender):
                try:
                    self._cb["settings"]()
                except Exception:
                    logger.exception("open settings callback failed")

            def showAbout_(self, sender):
                try:
                    self._cb["about"]()
                except Exception:
                    logger.exception("about callback failed")

            def quitApp_(self, sender):
                try:
                    self._cb["quit"]()
                except Exception:
                    logger.exception("quit callback failed")

        self._target = _Target.alloc().initWithCallbacks_({
            "show": on_show_window,
            "settings": on_open_settings,
            "about": on_about,
            "quit": on_quit,
        })

        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            -1.0  # NSVariableStatusItemLength
        )

        self._set_icon("disconnected")

        # Build menu (battery item is dynamic — keep a ref)
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        item_show = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "显示主界面", b"showWindow:", "",
        )
        item_show.setTarget_(self._target)
        menu.addItem_(item_show)

        item_settings = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "设置…", b"openSettings:", "",
        )
        item_settings.setTarget_(self._target)
        menu.addItem_(item_settings)

        menu.addItem_(NSMenuItem.separatorItem())

        item_about = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "关于 JoyHarness", b"showAbout:", "",
        )
        item_about.setTarget_(self._target)
        menu.addItem_(item_about)

        # Battery line — disabled (display only); we update its title later
        item_battery = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "电量: 未连接", b"", "",
        )
        item_battery.setEnabled_(False)
        menu.addItem_(item_battery)
        self._battery_item = item_battery

        menu.addItem_(NSMenuItem.separatorItem())

        item_quit = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "退出 JoyHarness", b"quitApp:", "q",
        )
        item_quit.setTarget_(self._target)
        menu.addItem_(item_quit)

        self._status_item.setMenu_(menu)
        logger.info("Menu bar status item created")

    # ------------------------------------------------------------------
    # State updates (call from main thread, e.g. via root.after)
    # ------------------------------------------------------------------

    def set_state(self, *, connected: bool, charging: bool = False,
                  low_battery: bool = False) -> None:
        """Update the menu-bar icon to reflect the current connection/battery state."""
        if not connected:
            state = "disconnected"
        elif charging:
            state = "charging"
        elif low_battery:
            state = "low_battery"
        else:
            state = "connected"
        self._set_icon(state)

    def set_battery_text(self, text: str) -> None:
        """Update the disabled '电量: ...' menu item."""
        self._battery_item.setTitle_(text)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _set_icon(self, state: str) -> None:
        path = _resource_dir() / f"menubar_{state}.png"
        if not path.exists():
            logger.warning("Menu-bar icon missing: %s", path)
            return
        img = self._AppKit_NSImage.alloc().initWithContentsOfFile_(str(path))
        if img is None:
            logger.warning("Failed to load menu-bar icon: %s", path)
            return
        # Colored icons: do NOT mark as template, otherwise macOS would
        # strip our state colors and tint the silhouette black/white.
        img.setTemplate_(False)
        # 22pt is the conventional menu-bar height
        from Foundation import NSMakeSize
        img.setSize_(NSMakeSize(22, 22))
        button = self._status_item.button()
        if button is not None:
            button.setImage_(img)
