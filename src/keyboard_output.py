"""Keyboard simulation wrapper — cross-platform.

On Windows: uses the `keyboard` library (requires administrator).
On macOS:   uses `pynput` (requires Accessibility permission).

Provides press/release/tap/combination operations with state tracking
to prevent double-press and ensure cleanup.
"""

from __future__ import annotations

import sys
import time
import logging

logger = logging.getLogger(__name__)

_held_keys: set[str] = set()

# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

if sys.platform == "darwin":
    from pynput.keyboard import Controller as _Controller, Key as _Key

    _kb = _Controller()

    _SPECIAL_KEYS: dict[str, _Key] = {
        "ctrl": _Key.ctrl,
        "control": _Key.ctrl,
        "ctrl_l": _Key.ctrl,
        "ctrl_r": _Key.ctrl_r,
        "alt": _Key.alt,
        "alt_l": _Key.alt,
        "alt_r": _Key.alt_r,
        "option": _Key.alt,
        "shift": _Key.shift,
        "shift_l": _Key.shift,
        "shift_r": _Key.shift_r,
        "cmd": _Key.cmd,
        "command": _Key.cmd,
        "cmd_l": _Key.cmd,
        "cmd_r": _Key.cmd_r,
        "windows": _Key.cmd,
        "win": _Key.cmd,
        "super": _Key.cmd,
        "enter": _Key.enter,
        "return": _Key.enter,
        "tab": _Key.tab,
        "space": _Key.space,
        "backspace": _Key.backspace,
        "delete": _Key.delete,
        "escape": _Key.esc,
        "esc": _Key.esc,
        "up": _Key.up,
        "down": _Key.down,
        "left": _Key.left,
        "right": _Key.right,
        "home": _Key.home,
        "end": _Key.end,
        "page_up": _Key.page_up,
        "page_down": _Key.page_down,
        "caps_lock": _Key.caps_lock,
        "f1": _Key.f1,
        "f2": _Key.f2,
        "f3": _Key.f3,
        "f4": _Key.f4,
        "f5": _Key.f5,
        "f6": _Key.f6,
        "f7": _Key.f7,
        "f8": _Key.f8,
        "f9": _Key.f9,
        "f10": _Key.f10,
        "f11": _Key.f11,
        "f12": _Key.f12,
        "f13": _Key.f13,
        "f14": _Key.f14,
        "f15": _Key.f15,
        "f16": _Key.f16,
        "f17": _Key.f17,
        "f18": _Key.f18,
        "f19": _Key.f19,
        "f20": _Key.f20,
    }

    # Keys that exist on Windows but not macOS — map to closest equivalents
    _FALLBACK_KEYS: dict[str, str] = {
        "print_screen": "f13",
        "insert": "f14",
        "menu": "f15",
        "num_lock": "f16",
        "pause": "f17",
        "scroll_lock": "f18",
    }

    def _resolve_key(key_name: str):
        """Convert a key name string to a pynput key object."""
        lower = key_name.lower().strip()
        if lower in _SPECIAL_KEYS:
            return _SPECIAL_KEYS[lower]
        if lower in _FALLBACK_KEYS:
            fallback = _FALLBACK_KEYS[lower]
            return _SPECIAL_KEYS.get(fallback, fallback)
        if len(lower) == 1:
            return lower
        return lower

    def _get_vk(key_obj) -> int | None:
        """Extract virtual keycode from a pynput key object."""
        if hasattr(key_obj, "value") and hasattr(key_obj.value, "vk"):
            vk = key_obj.value.vk
            if vk is not None: return vk
        if hasattr(key_obj, "vk"):
            vk = key_obj.vk
            if vk is not None: return vk

        # Hardcode vk for common special keys to bypass pynput issues on macOS
        key_str = str(key_obj)
        if key_str == "Key.enter": return 36
        if key_str == "Key.esc": return 53
        if key_str == "Key.backspace": return 51
        if key_str == "Key.tab": return 48
        if key_str == "Key.space": return 49

        if isinstance(key_obj, str) and len(key_obj) == 1:
            # macOS US-keyboard virtual keycodes for letters and digits.
            # Without these, pynput synthesizes "type-a-character" events that
            # don't carry modifier state — so e.g. ctrl+1 silently became "1".
            _VK_CHAR = {
                "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5,
                "h": 4, "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45,
                "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17, "u": 32,
                "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
                "1": 18, "2": 19, "3": 20, "4": 21, "5": 23,
                "6": 22, "7": 26, "8": 28, "9": 25, "0": 29,
                "-": 27, "=": 24, "[": 33, "]": 30, "\\": 42,
                ";": 41, "'": 39, ",": 43, ".": 47, "/": 44, "`": 50,
            }
            vk = _VK_CHAR.get(key_obj.lower())
            if vk is not None:
                return vk
            return None
        return None

    _MODIFIER_KEY_NAMES = {
        "ctrl", "control", "ctrl_l", "ctrl_r",
        "alt", "option", "alt_l", "alt_r",
        "cmd", "command", "cmd_l", "cmd_r",
        "shift", "shift_l", "shift_r",
        "fn",
    }

    def _is_modifier_key(key_name: str) -> bool:
        return key_name.lower() in _MODIFIER_KEY_NAMES

    def _safe_pynput(key_obj, key_name: str, is_down: bool) -> None:
        """Send a key via pynput, but refuse if it would resolve to vk=0
        for anything that isn't actually the letter 'a' — pynput on macOS
        synthesizes vk=0 CGEvents for keys with no proper mapping (e.g. media
        keys), which the system interprets as the 'a' character.
        """
        # Probe vk that pynput would use, and block the rogue 'a' case.
        probe_vk = None
        if hasattr(key_obj, "value") and hasattr(key_obj.value, "vk"):
            probe_vk = key_obj.value.vk
        elif hasattr(key_obj, "vk"):
            probe_vk = key_obj.vk
        if probe_vk == 0 and str(key_obj).replace("'", "") != "a":
            logger.warning("Refusing pynput fallback for '%s' (would emit vk=0 → 'a')",
                           key_name)
            return
        try:
            if is_down:
                _kb.press(key_obj)
            else:
                _kb.release(key_obj)
        except ValueError:
            logger.error("pynput rejected key: '%s'", key_name)

    def _post_cg_event(key_name: str, is_down: bool) -> None:
        import Quartz
        try:
            key_obj = _resolve_key(key_name)
        except ValueError:
            logger.error("Invalid key: '%s'", key_name)
            return

        vk = _get_vk(key_obj)

        if vk is not None:
            # Note: Quartz.CGEventCreateKeyboardEvent takes a CGCharCode (vk) and a boolean for keydown
            # Make sure we don't accidentally pass vk 0 (which is 'a') if vk is None or something invalid
            try:
                vk_int = int(vk)
                # The only valid case where we want to send vk=0 is if the key actually resolves to the letter 'a'.
                # A common cause of the rogue 'a' bug is that a special key (like media keys, volume, etc)
                # doesn't map correctly, yields vk=0, and then triggers 'a'.
                if vk_int == 0 and str(key_obj).replace("'", "") != "a":
                    raise ValueError(f"Refusing to send vk 0 (a) for non-'a' key: {key_name} -> {key_obj}")
                event = Quartz.CGEventCreateKeyboardEvent(None, vk_int, is_down)
                # Force-clear the global modifier flag state on every standalone key event.
                # Without this, a previously synthesized modifier (e.g. alt_r down/up for ZR
                # hold) leaves the process-wide CGEvent flag bit set, and later "bare" keys
                # like Enter arrive at strict consumers (Ghostty / Claude Code TUI) as
                # Option+Enter — which TUIs interpret as "insert newline", not "submit".
                # Combination chords go through _do_send_combination_macos and set their
                # own flags explicitly, so this clear is safe for them too (they overwrite).
                if not _is_modifier_key(key_name):
                    Quartz.CGEventSetFlags(event, 0)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                logger.debug("CGEvent posted: '%s' vk=%d %s", key_name, vk_int, "down" if is_down else "up")
            except (ValueError, TypeError) as e:
                # Fallback to pynput if we couldn't resolve a valid int vk
                logger.debug("Falling back to pynput for key '%s': %s", key_name, e)
                _safe_pynput(key_obj, key_name, is_down)
        else:
            # Fallback to pynput if we couldn't resolve a vk
            logger.debug("Falling back to pynput for key '%s' (vk is None)", key_name)
            _safe_pynput(key_obj, key_name, is_down)

    def _do_press(key_name: str) -> None:
        _post_cg_event(key_name, True)

    def _do_release(key_name: str) -> None:
        _post_cg_event(key_name, False)

    # macOS-specific combination sender. Posts modifiers, then stamps the
    # final non-modifier key event with explicit CGEventFlags so apps see a
    # real chord (e.g. Ctrl+1) instead of a bare keystroke.
    _MAC_MOD_FLAGS = {
        "ctrl": 0x40000, "control": 0x40000, "ctrl_l": 0x40000, "ctrl_r": 0x40000,
        "alt": 0x80000, "option": 0x80000, "alt_l": 0x80000, "alt_r": 0x80000,
        "cmd": 0x100000, "command": 0x100000, "cmd_l": 0x100000, "cmd_r": 0x100000,
        "shift": 0x20000, "shift_l": 0x20000, "shift_r": 0x20000,
    }

    def _do_send_combination_macos(keys: list[str], hold: float) -> None:
        import Quartz
        # Compute the cumulative modifier flag from any modifier keys in the combo
        flag = 0
        for k in keys:
            f = _MAC_MOD_FLAGS.get(k.lower())
            if f:
                flag |= f
        # Press modifiers first (so any window manager etc. sees them held)
        mods = [k for k in keys if k.lower() in _MAC_MOD_FLAGS]
        non_mods = [k for k in keys if k.lower() not in _MAC_MOD_FLAGS]
        for k in mods:
            _do_press(k)
            time.sleep(0.005)
        # Now post non-modifier events with explicit flags set
        for k in non_mods:
            try:
                key_obj = _resolve_key(k)
                vk = _get_vk(key_obj)
                if vk is None:
                    _safe_pynput(key_obj, k, True)
                    time.sleep(0.005)
                    _safe_pynput(key_obj, k, False)
                    continue
                vk_int = int(vk)
                ev_down = Quartz.CGEventCreateKeyboardEvent(None, vk_int, True)
                Quartz.CGEventSetFlags(ev_down, flag)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
                time.sleep(0.005)
                ev_up = Quartz.CGEventCreateKeyboardEvent(None, vk_int, False)
                Quartz.CGEventSetFlags(ev_up, flag)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)
            except Exception as e:
                logger.error("combo key '%s' failed: %s", k, e)
        time.sleep(hold)
        # Release modifiers in reverse
        for k in reversed(mods):
            _do_release(k)

    # Bind module-level shim to this implementation
    globals()["_send_combination_macos"] = _do_send_combination_macos
    globals()["_IS_MACOS"] = True

    def _do_type_text(text: str) -> None:
        _kb.type(text)

    def is_valid_key(key_name: str) -> bool:
        """Check if a key name is recognized."""
        lower = key_name.lower().strip()
        if lower in _SPECIAL_KEYS:
            return True
        if lower in _FALLBACK_KEYS:
            return True
        if len(lower) == 1:
            return True
        return False

else:
    import keyboard as _keyboard

    def _do_press(key_name: str) -> None:
        _keyboard.press(key_name)

    def _do_release(key_name: str) -> None:
        _keyboard.release(key_name)

    def _do_type_text(text: str) -> None:
        _keyboard.write(text)

    def is_valid_key(key_name: str) -> bool:
        """Check if a key name is recognized by the keyboard library."""
        try:
            codes = _keyboard.key_to_scan_codes(key_name)
            return len(codes) > 0
        except (ValueError, KeyError):
            return False


# ---------------------------------------------------------------------------
# Public API (unchanged interface)
# ---------------------------------------------------------------------------

def press(key: str) -> None:
    """Hold a key down. No-op if already held."""
    if key in _held_keys:
        return
    _do_press(key)
    _held_keys.add(key)
    logger.debug("pressed: %s", key)


def release(key: str) -> None:
    """Release a held key. No-op if not currently held."""
    if key not in _held_keys:
        return
    _do_release(key)
    _held_keys.discard(key)
    logger.debug("released: %s", key)


def tap(key: str, duration: float = 0.02) -> None:
    """Press and release a key immediately.

    If the key is currently held (tracked in _held_keys), temporarily
    release it, re-tap, then restore the held state.
    """
    was_held = key in _held_keys
    if was_held:
        _do_release(key)
        _held_keys.discard(key)

    _do_press(key)
    time.sleep(duration)
    _do_release(key)

    if was_held:
        _do_press(key)
        _held_keys.add(key)

    logger.debug("tapped: %s (was_held=%s)", key, was_held)


def send_combination(keys: list[str], hold: float = 0.05) -> None:
    """Press multiple keys simultaneously, then release in reverse order.

    Example: send_combination(["ctrl", "c"]) -> Ctrl+C

    Keys that are currently held via press() are temporarily released,
    then restored after the combination completes.

    Args:
        keys: Key names in press order.
        hold: Duration to hold all keys before releasing (seconds).
    """
    held_in_combo = [k for k in keys if k in _held_keys]
    for k in held_in_combo:
        _do_release(k)
        _held_keys.discard(k)

    # On macOS, CGEvent does not implicitly carry modifier state across separate
    # events when posted rapidly. We post the modifiers first with their flags,
    # then explicitly stamp the non-modifier key event with the accumulated
    # CGEventFlags so the system sees e.g. Ctrl+1 not bare 1.
    _send_combination_macos(keys, hold) if _IS_MACOS else _send_combination_generic(keys, hold)

    for k in held_in_combo:
        _do_press(k)
        _held_keys.add(k)

    logger.debug("combination: %s", "+".join(keys))


def _send_combination_generic(keys: list[str], hold: float) -> None:
    for key in keys:
        _do_press(key)
        time.sleep(0.01)
    time.sleep(hold)
    for key in reversed(keys):
        _do_release(key)


# macOS: stamp the final key event with explicit modifier flags so combinations
# like ctrl+1 actually register as a chord rather than a bare keystroke.
if "_IS_MACOS" not in globals():
    _IS_MACOS = False
if "_send_combination_macos" not in globals():
    def _send_combination_macos(keys: list[str], hold: float) -> None:
        pass  # Replaced when running on macOS


def release_all() -> None:
    """Release every currently held key. Used for cleanup on exit or disconnect."""
    # On macOS, don't proactively release keys during init to avoid accidental a presses
    # when _held_keys might be empty but we might be iterating. We only release what we explicitly hold.
    for key in list(_held_keys):
        _do_release(key)
        logger.debug("cleanup released: %s", key)
    _held_keys.clear()


def is_held(key: str) -> bool:
    """Check if a key is currently being held."""
    return key in _held_keys


def type_text(text: str) -> None:
    """Type a string."""
    _do_type_text(text)
    logger.debug("typed: %s", text)
