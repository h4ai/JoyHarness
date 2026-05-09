"""pygame-based Joy-Con detection and polling loop.

Handles controller discovery, button state polling, axis reading,
disconnection detection, and automatic reconnection.

Single-mode (single_left / single_right): one pygame Joystick, button events
dispatched as plain int indices.

Dual mode: two SEPARATE pygame Joystick devices on macOS (because
SDL_JOYSTICK_HIDAPI_COMBINE_JOY_CONS=0 is forced in main.py so BatteryReader
can read each side over HID). The polling loop holds both devices, tags every
button press with side ("L" or "R"), and dispatches (side, idx) tuples to
KeyMapper. The user picks which physical stick drives the direction mappings
via mappings.stick_source ("left" or "right").
"""

from __future__ import annotations

import threading
import time
import logging

import pygame

from .constants import (
    AXIS_RSTICK_X,
    AXIS_RSTICK_Y,
    BUTTON_NAMES,
    BUTTON_NAMES_BY_MODE,
    SNAPBACK_FRAMES,
)
from .joystick_handler import apply_deadzone, get_direction
from .key_mapper import KeyMapper

logger = logging.getLogger(__name__)

# Reconnection scan interval in seconds
RECONNECT_INTERVAL = 2.0


def _classify_side(name: str) -> str | None:
    """Classify a joystick name as a Joy-Con side.

    Returns "L", "R", or None if not a recognizable Joy-Con. We mirror the
    same rough heuristic as battery_reader._find_joycons: the SDL device
    name typically contains "(L)" / "Left" or "(R)" / "Right".
    """
    n = name.lower()
    if not any(kw in n for kw in ("joy-con", "joy con", "switch", "pro controller")):
        return None
    # Check explicit side markers. Order matters — check both before single-letter.
    if "(l)" in n or "left" in n:
        return "L"
    if "(r)" in n or "right" in n:
        return "R"
    # Fall back to standalone "l"/"r" tokens (e.g. "Joy-Con L")
    tokens = n.replace("(", " ").replace(")", " ").split()
    if "l" in tokens:
        return "L"
    if "r" in tokens:
        return "R"
    return None


def find_joycons() -> list[tuple[str, pygame.joystick.Joystick]]:
    """Find all connected Joy-Cons and return them tagged by side.

    Returns a list of (side, joystick) tuples where side ∈ {"L", "R"}.
    For unidentifiable single devices, defaults the side to "R" (preserves
    legacy behavior where unknown devices were treated as right Joy-Con).
    """
    pygame.joystick.init()
    count = pygame.joystick.get_count()

    if count == 0:
        return []

    logger.info("Found %d joystick(s)", count)
    found: list[tuple[str, pygame.joystick.Joystick]] = []
    seen_sides: set[str] = set()

    for i in range(count):
        js = pygame.joystick.Joystick(i)
        name = js.get_name()
        side = _classify_side(name)
        logger.info("  [%d] %s (buttons=%d, axes=%d) → side=%s",
                    i, name, js.get_numbuttons(), js.get_numaxes(), side)
        if side is None:
            continue
        # Avoid duplicating the same side (combined-device case where a single
        # SDL device spuriously matches both keywords)
        if side in seen_sides:
            continue
        seen_sides.add(side)
        found.append((side, js))

    # Fallback: if nothing classified but exactly one device present, treat as R.
    if not found and count == 1:
        js = pygame.joystick.Joystick(0)
        logger.info("Single unidentified joystick, defaulting side=R: %s", js.get_name())
        found.append(("R", js))

    return found


def find_joycon(joystick_index: int | None = None) -> pygame.joystick.Joystick | None:
    """Find and return a single Joy-Con joystick instance.

    Kept for backward compatibility with discover mode and reconnection in
    single-mode flows. Returns the first detected Joy-Con (R preferred).
    """
    if joystick_index is not None:
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        if 0 <= joystick_index < count:
            js = pygame.joystick.Joystick(joystick_index)
            logger.info("Using joystick #%d: %s", joystick_index, js.get_name())
            return js
        logger.error("Joystick index %d out of range (0-%d)", joystick_index, count - 1)
        return None

    found = find_joycons()
    if not found:
        return None
    # Prefer R when both present (legacy behavior)
    for side, js in found:
        if side == "R":
            return js
    return found[0][1]


def detect_connection_mode() -> str:
    """Detect the Joy-Con connection mode from connected joysticks.

    Returns:
        One of "single_left", "single_right", or "dual".
    """
    found = find_joycons()
    if not found:
        return "single_right"

    sides = {side for side, _ in found}
    if "L" in sides and "R" in sides:
        return "dual"
    if "L" in sides:
        return "single_left"
    return "single_right"


def run_discover_mode(joystick_index: int | None = None) -> None:
    """Run discovery mode: print raw button/axis values for calibration.

    Press Ctrl+C to exit. Use this to determine correct button indices
    for your specific controller/driver combination. In dual mode this
    polls both Joy-Cons and prefixes each event with the side.
    """
    pygame.init()

    mode = detect_connection_mode()

    if mode == "dual":
        joycons = find_joycons()
        if not joycons:
            print("No joystick found.")
            pygame.quit()
            return
    else:
        js = find_joycon(joystick_index)
        if js is None:
            print("No joystick found. Make sure your Joy-Con is connected via Bluetooth.")
            print("Tip: Windows Settings → Bluetooth → Add device → hold the small pairing")
            print("     button on the Joy-Con rail for 3 seconds until lights flash.")
            pygame.quit()
            return
        # Determine side for naming consistency with single mode
        side = _classify_side(js.get_name()) or ("L" if mode == "single_left" else "R")
        joycons = [(side, js)]

    btn_names_dual = BUTTON_NAMES_BY_MODE["dual"]  # {(side, idx): name}

    print(f"\n=== Discovery Mode ===")
    print(f"Connection mode: {mode}")
    for side, js in joycons:
        print(f"  [side={side}] {js.get_name()} GUID={js.get_guid()} "
              f"buttons={js.get_numbuttons()} axes={js.get_numaxes()}")
    print(f"\nPress buttons and move sticks to see their indices.")
    print(f"Press Ctrl+C to exit.\n")

    clock = pygame.time.Clock()
    prev_buttons: dict[str, set[int]] = {side: set() for side, _ in joycons}

    try:
        while True:
            pygame.event.pump()

            for side, js in joycons:
                current: set[int] = set()
                for i in range(js.get_numbuttons()):
                    if js.get_button(i):
                        current.add(i)

                pressed = current - prev_buttons[side]
                released = prev_buttons[side] - current

                for i in sorted(pressed):
                    name = btn_names_dual.get((side, i), "???")
                    print(f"  [{side}] BTN {i:2d} ({name:8s}) PRESSED")

                for i in sorted(released):
                    name = btn_names_dual.get((side, i), "???")
                    print(f"  [{side}] BTN {i:2d} ({name:8s}) released")

                prev_buttons[side] = current

                # Axis state (only print if changed significantly)
                for i in range(js.get_numaxes()):
                    val = js.get_axis(i)
                    if abs(val) > 0.1:
                        print(f"  [{side}] AXIS {i}: {val:+.3f}", end="\r")

            clock.tick(60)

    except KeyboardInterrupt:
        print("\nDiscovery mode ended.")
    finally:
        pygame.quit()


def _calibrate_baseline(
    joystick: pygame.joystick.Joystick,
    axis_x: int,
    axis_y: int,
    samples: int = 20,
) -> tuple[float, float]:
    """Read stick resting position and return average as baseline.

    Should be called at startup with the stick at rest.
    """
    num_axes = joystick.get_numaxes()
    if axis_x >= num_axes or axis_y >= num_axes:
        logger.warning("Axis index out of range (axes=%d, x=%d, y=%d), using (0,0) baseline",
                       num_axes, axis_x, axis_y)
        return (0.0, 0.0)

    clock = pygame.time.Clock()
    total_x = 0.0
    total_y = 0.0

    for _ in range(samples):
        pygame.event.pump()
        total_x += joystick.get_axis(axis_x)
        total_y += joystick.get_axis(axis_y)
        clock.tick(100)

    return (total_x / samples, total_y / samples)


def _select_stick_joystick(
    joycons: list[tuple[str, pygame.joystick.Joystick]],
    config: dict,
) -> pygame.joystick.Joystick | None:
    """Pick which joystick supplies stick axes based on mode and config.

    In single modes there is only one joystick and stick_source is ignored.
    In dual mode mappings.stick_source ("left" | "right") chooses the side;
    falls back to the right joystick if the requested side isn't present.
    """
    if not joycons:
        return None
    if len(joycons) == 1:
        return joycons[0][1]
    desired = (
        config.get("mappings", {}).get("stick_source", "right").lower()
    )
    target_side = "L" if desired.startswith("l") else "R"
    for side, js in joycons:
        if side == target_side:
            return js
    # Fallback: any joystick
    return joycons[0][1]


def run_polling_loop(
    joysticks: list[tuple[str, pygame.joystick.Joystick]] | pygame.joystick.Joystick,
    key_mapper: KeyMapper,
    config: dict,
    stop_event: threading.Event | None = None,
    on_mode_change: callable = None,
) -> None:
    """Main polling loop: read controller state and dispatch to key_mapper.

    Args:
        joysticks: Either a list of (side, Joystick) tuples (preferred), or
            a single pygame.joystick.Joystick for legacy callers (treated as
            side="R" or "L" depending on detect_connection_mode()).
        key_mapper: KeyMapper instance for action dispatch.
        config: Complete configuration dict.
        stop_event: Threading event to signal loop exit. None = run until Ctrl+C.
    """
    from .config_loader import get_profile

    # Normalize input to list[(side, js)]
    if isinstance(joysticks, list):
        joycons = list(joysticks)
    else:
        # Legacy single-joystick caller — classify by name
        side = _classify_side(joysticks.get_name()) or "R"
        joycons = [(side, joysticks)]

    deadzone = config.get("deadzone", 0.2)
    poll_interval = max(config.get("poll_interval", 0.01), 0.001)
    stick_mode = config.get("stick_mode", "4dir")
    axis_x = config.get("axis_x", AXIS_RSTICK_X)
    axis_y = config.get("axis_y", AXIS_RSTICK_Y)

    clock = pygame.time.Clock()
    prev_buttons: dict[str, set[int]] = {side: set() for side, _ in joycons}
    prev_direction: str | None = None
    center_count: int = 0

    # Connection mode tracking — check every 5 seconds
    current_mode = config.get("active_profile", "single_right")
    mode_check_interval = 5.0  # seconds
    last_mode_check = time.monotonic()

    logger.info("Polling started (deadzone=%.2f, interval=%.0fms, mode=%s, joycons=%d)",
                deadzone, poll_interval * 1000, stick_mode, len(joycons))
    for side, js in joycons:
        logger.info("  [%s] %s", side, js.get_name())

    # Pick which joystick drives the stick directions and calibrate it
    stick_js = _select_stick_joystick(joycons, config)
    baseline_x, baseline_y = (0.0, 0.0)
    if stick_js is not None:
        baseline_x, baseline_y = _calibrate_baseline(stick_js, axis_x, axis_y)
        logger.info("Stick baseline: x=%.4f, y=%.4f (from %s)",
                    baseline_x, baseline_y, stick_js.get_name())

    def _make_btn_key(side: str, idx: int):
        """Construct the btn_key shape KeyMapper expects for the active mode."""
        if current_mode == "dual":
            return (side, idx)
        return idx

    try:
        while not (stop_event and stop_event.is_set()):
            try:
                pygame.event.pump()
                # macOS: pygame.event.pump() does NOT raise on disconnect.
                # Detect via JOYDEVICEREMOVED event or get_count() == 0.
                try:
                    events = pygame.event.get()
                    for ev in events:
                        if ev.type == pygame.JOYDEVICEREMOVED:
                            logger.info("JOYDEVICEREMOVED received (instance_id=%s)",
                                        getattr(ev, "instance_id", "?"))
                            raise pygame.error("Joystick device removed")
                except SystemError:
                    # SystemError: <built-in function get> returned a result with an exception set
                    # can happen after the pygame joystick subsystem is re-initialized
                    pygame.event.clear()

                # In dual mode all joysticks must remain connected
                if pygame.joystick.get_count() < len(joycons):
                    raise pygame.error("Joystick device count dropped")
                if pygame.joystick.get_count() == 0:
                    raise pygame.error("No joysticks connected")
            except pygame.error:
                # Joystick was disconnected
                logger.warning("Joystick disconnected, attempting reconnection...")
                key_mapper.release_all()
                from . import keyboard_output
                keyboard_output.release_all()

                joycons = wait_for_reconnection()
                if not joycons or (stop_event and stop_event.is_set()):
                    break

                # Re-initialize state with new joystick set
                prev_buttons = {side: set() for side, _ in joycons}
                prev_direction = None
                center_count = 0

                # Re-detect connection mode (may have changed L↔R↔dual)
                try:
                    detected_mode = detect_connection_mode()
                    if detected_mode != current_mode:
                        logger.info("Connection mode changed after reconnect: %s → %s",
                                    current_mode, detected_mode)
                        profile = get_profile(config, detected_mode)
                        profile_mappings = profile.get("mappings", config.get("mappings", {}))
                        config["mappings"] = profile_mappings
                        config["active_profile"] = detected_mode
                        key_mapper.switch_profile(config, detected_mode)
                        current_mode = detected_mode
                        if on_mode_change:
                            on_mode_change(detected_mode)
                except Exception:
                    logger.debug("Mode check after reconnect failed", exc_info=True)

                # Re-calibrate stick after profile may have switched stick_source
                stick_js = _select_stick_joystick(joycons, config)
                if stick_js is not None:
                    baseline_x, baseline_y = _calibrate_baseline(stick_js, axis_x, axis_y)
                    logger.info("Reconnected, baseline=(%.4f, %.4f) from %s",
                                baseline_x, baseline_y, stick_js.get_name())

                continue

            # --- Button polling (per side) ---
            for side, js in joycons:
                current: set[int] = set()
                for i in range(js.get_numbuttons()):
                    if js.get_button(i):
                        current.add(i)

                pressed = current - prev_buttons[side]
                released = prev_buttons[side] - current

                for btn_idx in sorted(pressed):
                    key_mapper.button_down(_make_btn_key(side, btn_idx))

                for btn_idx in sorted(released):
                    key_mapper.button_up(_make_btn_key(side, btn_idx))

                prev_buttons[side] = current

            # --- Stick polling (single source per the active profile) ---
            if stick_js is not None:
                num_axes = stick_js.get_numaxes()
                if axis_x < num_axes and axis_y < num_axes:
                    raw_x = stick_js.get_axis(axis_x) - baseline_x
                    raw_y = stick_js.get_axis(axis_y) - baseline_y
                else:
                    raw_x, raw_y = 0.0, 0.0
            else:
                raw_x, raw_y = 0.0, 0.0

            filt_x, filt_y = apply_deadzone(raw_x, raw_y, deadzone)
            direction = get_direction(filt_x, filt_y, stick_mode)

            if direction != prev_direction:
                if direction is None:
                    center_count += 1
                    if center_count >= SNAPBACK_FRAMES:
                        key_mapper.stick_centered()
                        prev_direction = None
                else:
                    center_count = 0
                    key_mapper.stick_direction(direction)
                    prev_direction = direction

            # Periodic connection mode check (detect Joy-Con hot-plug changes)
            now = time.monotonic()
            if now - last_mode_check >= mode_check_interval:
                last_mode_check = now
                try:
                    detected_mode = detect_connection_mode()
                    if detected_mode != current_mode:
                        logger.info("Connection mode changed: %s → %s", current_mode, detected_mode)
                        profile = get_profile(config, detected_mode)
                        profile_mappings = profile.get("mappings", config.get("mappings", {}))
                        config["mappings"] = profile_mappings
                        config["active_profile"] = detected_mode
                        key_mapper.switch_profile(config, detected_mode)
                        current_mode = detected_mode
                        if on_mode_change:
                            on_mode_change(detected_mode)
                        # Re-resolve joycon list and stick source after mode change
                        joycons = find_joycons() or joycons
                        prev_buttons = {side: set() for side, _ in joycons}
                        stick_js = _select_stick_joystick(joycons, config)
                        if stick_js is not None:
                            baseline_x, baseline_y = _calibrate_baseline(stick_js, axis_x, axis_y)
                except Exception:
                    logger.debug("Connection mode check failed", exc_info=True)

            # Process auto-action long press detection
            key_mapper.poll()

            clock.tick(1 / poll_interval)

    except KeyboardInterrupt:
        logger.info("Polling interrupted by user")
    finally:
        key_mapper.release_all()
        from . import keyboard_output
        keyboard_output.release_all()


def wait_for_reconnection(joystick_index: int | None = None) -> list[tuple[str, pygame.joystick.Joystick]]:
    """Scan for Joy-Con reconnection every RECONNECT_INTERVAL seconds.

    Returns a list of (side, joystick) tuples when at least one is found,
    or an empty list if interrupted.
    """
    logger.info("Controller disconnected. Waiting for reconnection...")

    try:
        while True:
            time.sleep(RECONNECT_INTERVAL)
            # Re-init joystick subsystem to scan for new devices
            pygame.joystick.quit()
            pygame.joystick.init()
            joycons = find_joycons()
            if joycons:
                logger.info("Controller(s) reconnected: %d Joy-Con(s)", len(joycons))
                for side, js in joycons:
                    logger.info("  [%s] %s", side, js.get_name())
                return joycons
    except KeyboardInterrupt:
        return []
