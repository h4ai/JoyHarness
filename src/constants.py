"""Joy-Con hardware constants for pygame button/axis mapping.

NOTE: Button and axis indices are based on SDL2's Switch controller mapping.
These MUST be verified using `python src/main.py --discover` mode,
as indices may vary across SDL2 versions and Windows driver updates.

Three connection modes are supported:
- single_right: Only right Joy-Con connected
- single_left:  Only left Joy-Con connected
- dual:         Both Joy-Cons connected (as TWO separate SDL2 devices on
                macOS — see SDL_JOYSTICK_HIDAPI_COMBINE_JOY_CONS=0 in main.py).
                In dual mode each side keeps its single-mode pygame indices;
                the polling layer tags every event with a side ("L" / "R")
                so left and right buttons never collide.
"""

# === Right Joy-Con Button Indices (calibrated 2026-04-09) ===
# Face buttons
BTN_X = 0       # X (上位)
BTN_A = 1       # A (右位)
BTN_Y = 2       # Y (左位)
BTN_B = 3       # B (下位)

# System / Home
BTN_HOME = 5    # Home (圆形)
BTN_PLUS = 6    # + 按钮
BTN_RSTICK = 7  # 摇杆按下

# Shoulder / trigger
BTN_SL = 9      # SL (侧边左)
BTN_R = 16      # R 肩键
BTN_SR = 10     # SR (侧边右)
BTN_ZR = 18     # ZR 扳机

# === Left Joy-Con Button Indices (calibrated 2026-05-07 on macOS, SDL 2.28.4) ===
# NOTE: macOS SDL2 only emits events for A/B/X/Y, L, ZL, SR, Capture, LStick on
# Joy-Con L. SL and Minus do NOT generate button events on this platform.
#
# Joy-Con L face buttons map by PHYSICAL POSITION (vertical hold), so that the
# experience exactly mirrors Joy-Con R when held normally:
#   ▲ up   position → X    ▼ down position → B
#   ◀ left position → Y    ▶ right position → A
BTN_L_B = 0       # ▼ down   (B 下位)
BTN_L_Y = 1       # ◀ left   (Y 左位)
BTN_L_A = 2       # ▶ right  (A 右位)
BTN_L_X = 3       # ▲ up     (X 上位)
BTN_L_MINUS = 4   # - 按钮 (macOS: not detected by SDL2)
BTN_L_CAPTURE = 5 # Capture 按钮
BTN_L_LSTICK = 7  # 左摇杆按下 (macOS SDL2 实测为 7，非 6)
BTN_L_SL = 9      # SL (macOS: not detected by SDL2)
BTN_L_SR = 10     # SR
BTN_L_L = 17      # L 肩键
BTN_L_ZL = 19     # ZL 扳机

# === Axis Indices (calibrated) ===
AXIS_RSTICK_Y = 0   # 垂直 (上=负, 下=正)
AXIS_RSTICK_X = 1   # 水平 (左=负, 右=正)
# Left Joy-Con stick uses the same axis indices on its own SDL device.
AXIS_LSTICK_Y = 0
AXIS_LSTICK_X = 1

# === Default Values ===
DEFAULT_DEADZONE = 0.2
DIRECTION_THRESHOLD = 0.5
POLL_INTERVAL = 0.01       # 100Hz polling
SNAPBACK_FRAMES = 2        # Frames required at center before registering release

# === Right Joy-Con Button Name Lookup ===
BUTTON_NAMES: dict[int, str] = {
    BTN_A: "A",
    BTN_B: "B",
    BTN_X: "X",
    BTN_Y: "Y",
    BTN_R: "R",
    BTN_ZR: "ZR",
    BTN_PLUS: "Plus",
    BTN_RSTICK: "RStick",
    BTN_HOME: "Home",
    BTN_SL: "SL",
    BTN_SR: "SR",
}

# Reverse lookup: name → index
BUTTON_INDICES: dict[str, int] = {v: k for k, v in BUTTON_NAMES.items()}

# === Left Joy-Con Button Name Lookup ===
BUTTON_NAMES_LEFT: dict[int, str] = {
    BTN_L_A: "A",
    BTN_L_B: "B",
    BTN_L_X: "X",
    BTN_L_Y: "Y",
    BTN_L_L: "L",
    BTN_L_ZL: "ZL",
    BTN_L_MINUS: "Minus",
    BTN_L_CAPTURE: "Capture",
    BTN_L_LSTICK: "LStick",
    BTN_L_SL: "SL",
    BTN_L_SR: "SR",
}
BUTTON_INDICES_LEFT: dict[str, int] = {v: k for k, v in BUTTON_NAMES_LEFT.items()}

# === Dual Mode Button Name Lookup ===
# In dual mode both Joy-Cons appear as separate pygame devices, so each name
# maps to a (side, idx) pair where side ∈ {"L", "R"}. ABXY are explicitly
# split into L_* and R_* so the user can map both sides independently.
# Side-only buttons that already had a unique name (ZL/L/Minus/Capture/LStick
# on L; ZR/R/Plus/Home/RStick on R) keep their single-mode names. Side
# buttons get a side suffix (SL_L / SR_L / SL_R / SR_R).
BUTTON_INDICES_DUAL: dict[str, tuple[str, int]] = {
    # Left Joy-Con face buttons (split from single-mode A/B/X/Y)
    "L_A":     ("L", BTN_L_A),
    "L_B":     ("L", BTN_L_B),
    "L_X":     ("L", BTN_L_X),
    "L_Y":     ("L", BTN_L_Y),
    # Left Joy-Con shoulder / system / stick
    "L":       ("L", BTN_L_L),
    "ZL":      ("L", BTN_L_ZL),
    "Minus":   ("L", BTN_L_MINUS),
    "Capture": ("L", BTN_L_CAPTURE),
    "LStick":  ("L", BTN_L_LSTICK),
    "SL_L":    ("L", BTN_L_SL),
    "SR_L":    ("L", BTN_L_SR),
    # Right Joy-Con face buttons (split from single-mode A/B/X/Y)
    "R_A":     ("R", BTN_A),
    "R_B":     ("R", BTN_B),
    "R_X":     ("R", BTN_X),
    "R_Y":     ("R", BTN_Y),
    # Right Joy-Con shoulder / system / stick
    "R":       ("R", BTN_R),
    "ZR":      ("R", BTN_ZR),
    "Plus":    ("R", BTN_PLUS),
    "Home":    ("R", BTN_HOME),
    "RStick":  ("R", BTN_RSTICK),
    "SL_R":    ("R", BTN_SL),
    "SR_R":    ("R", BTN_SR),
}

# Reverse lookup: (side, idx) → name. Used by discover mode.
BUTTON_NAMES_DUAL: dict[tuple[str, int], str] = {v: k for k, v in BUTTON_INDICES_DUAL.items()}

# === Mode-based lookup tables ===
# For single modes the name dict is {idx: name}; for dual it is {(side, idx): name}.
BUTTON_NAMES_BY_MODE: dict = {
    "single_right": BUTTON_NAMES,
    "single_left": BUTTON_NAMES_LEFT,
    "dual": BUTTON_NAMES_DUAL,
}

# For single modes the index dict is {name: idx}; for dual it is {name: (side, idx)}.
BUTTON_INDICES_BY_MODE: dict = {
    "single_right": BUTTON_INDICES,
    "single_left": BUTTON_INDICES_LEFT,
    "dual": BUTTON_INDICES_DUAL,
}

MAPPABLE_BUTTONS_BY_MODE: dict[str, tuple[str, ...]] = {
    "single_right": ("A", "B", "X", "Y", "R", "ZR", "Plus", "Home", "RStick", "SL", "SR"),
    "single_left": ("A", "B", "X", "Y", "L", "ZL", "Minus", "Capture", "LStick", "SL", "SR"),
    "dual": (
        # Left Joy-Con
        "L_A", "L_B", "L_X", "L_Y",
        "L", "ZL", "Minus", "Capture", "LStick", "SL_L", "SR_L",
        # Right Joy-Con
        "R_A", "R_B", "R_X", "R_Y",
        "R", "ZR", "Plus", "Home", "RStick", "SL_R", "SR_R",
    ),
}

# Buttons in dual mode that belong to the left Joy-Con (used by the settings
# UI to render groups). Anything not in this set belongs to the right side.
DUAL_LEFT_BUTTONS: frozenset[str] = frozenset({
    "L_A", "L_B", "L_X", "L_Y",
    "L", "ZL", "Minus", "Capture", "LStick", "SL_L", "SR_L",
})

MODE_LABELS: dict[str, str] = {
    "single_right": "右手柄",
    "single_left": "左手柄",
    "dual": "左右手柄",
}


def get_button_names(mode: str = "single_right"):
    """Get button name lookup table for a connection mode.

    Returns {idx: name} for single modes, {(side, idx): name} for dual mode.
    """
    return BUTTON_NAMES_BY_MODE.get(mode, BUTTON_NAMES)


def get_button_indices(mode: str = "single_right"):
    """Get button index lookup table for a connection mode.

    Returns {name: idx} for single modes, {name: (side, idx)} for dual mode.
    """
    return BUTTON_INDICES_BY_MODE.get(mode, BUTTON_INDICES)


# === Stick Direction Names ===
STICK_DIRECTIONS = ("up", "down", "left", "right", "up-left", "up-right", "down-left", "down-right")

# === Default Key Mapping (used when no config file is loaded) ===
DEFAULT_MAPPINGS: dict = {
    "buttons": {
        "A":      {"action": "tap", "key": "enter"},
        "B":      {"action": "sequence", "keys": ["shift", "tab"]},
        "X":      {"action": "auto", "key": "f2"},
        "Y":      {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        "R":      {"action": "window_switch"},
        "ZR":     {
            "action": "macro",
            "if_window": "code.exe",
            "steps": [
                {"type": "combination", "keys": ["ctrl", "shift", "p"]},
                {"type": "delay", "ms": 100},
                {"type": "type", "text": "Claude Code: Focus input"},
                {"type": "delay", "ms": 100},
                {"type": "tap", "key": "enter"},
            ],
        },
        "Plus":   {"action": "combination", "keys": ["shift", "tab"]},
        "Home":   {"action": "tap", "key": "windows"},
        "RStick": {"action": "tap", "key": "tab"},
        "SL":     {"action": "hold", "key": "alt"},
        "SR":     {"action": "window_switch"},
    },
    "stick_directions": {
        "up":    {"action": "auto", "key": "down", "repeat": 100},
        "down":  {"action": "auto", "key": "up", "repeat": 100},
        "left":  {"action": "auto", "key": "left", "repeat": 100},
        "right": {"action": "auto", "key": "right", "repeat": 100},
    },
}

DEFAULT_MAPPINGS_LEFT: dict = {
    # Mirrored from DEFAULT_MAPPINGS (right). Button name translation:
    # R→L, ZR→ZL, Plus→Minus, Home→Capture, RStick→LStick.
    # Capture keeps its screenshot semantic (print_screen on Windows).
    "buttons": {
        "A":       {"action": "tap", "key": "enter"},
        "B":       {"action": "sequence", "keys": ["shift", "tab"]},
        "X":       {"action": "auto", "key": "f2"},
        "Y":       {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        "L":       {"action": "window_switch"},
        "ZL":      {
            "action": "macro",
            "if_window": "code.exe",
            "steps": [
                {"type": "combination", "keys": ["ctrl", "shift", "p"]},
                {"type": "delay", "ms": 100},
                {"type": "type", "text": "Claude Code: Focus input"},
                {"type": "delay", "ms": 100},
                {"type": "tap", "key": "enter"},
            ],
        },
        "Minus":   {"action": "combination", "keys": ["shift", "tab"]},
        "Capture": {"action": "tap", "key": "print_screen"},
        "LStick":  {"action": "tap", "key": "tab"},
        "SL":      {"action": "hold", "key": "alt"},
        "SR":      {"action": "window_switch"},
    },
    "stick_directions": {
        "up":    {"action": "auto", "key": "down", "repeat": 100},
        "down":  {"action": "auto", "key": "up", "repeat": 100},
        "left":  {"action": "auto", "key": "left", "repeat": 100},
        "right": {"action": "auto", "key": "right", "repeat": 100},
    },
}

DEFAULT_MAPPINGS_DUAL: dict = {
    "buttons": {
        # Left Joy-Con face (split from old A/B/X/Y)
        "L_A":     {"action": "tap", "key": "enter"},
        "L_B":     {"action": "sequence", "keys": ["shift", "tab"]},
        "L_X":     {"action": "auto", "key": "f2"},
        "L_Y":     {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        # Right Joy-Con face
        "R_A":     {"action": "tap", "key": "enter"},
        "R_B":     {"action": "sequence", "keys": ["shift", "tab"]},
        "R_X":     {"action": "auto", "key": "f2"},
        "R_Y":     {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        # Shoulder / trigger / system
        "R":       {"action": "window_switch"},
        "ZR":      {
            "action": "macro",
            "if_window": "code.exe",
            "steps": [
                {"type": "combination", "keys": ["ctrl", "shift", "p"]},
                {"type": "delay", "ms": 100},
                {"type": "type", "text": "Claude Code: Focus input"},
                {"type": "delay", "ms": 100},
                {"type": "tap", "key": "enter"},
            ],
        },
        "L":       {"action": "hold", "key": "ctrl"},
        "ZL":      {"action": "hold", "key": "shift"},
        "Plus":    {"action": "combination", "keys": ["ctrl", "s"]},
        "Minus":   {"action": "tap", "key": "escape"},
        "Home":    {"action": "tap", "key": "windows"},
        "Capture": {"action": "tap", "key": "print_screen"},
        "RStick":  {"action": "tap", "key": "tab"},
        "LStick":  {"action": "tap", "key": "enter"},
        "SL_L":    {"action": "hold", "key": "alt"},
        "SR_L":    {"action": "window_switch"},
        "SL_R":    {"action": "hold", "key": "alt"},
        "SR_R":    {"action": "window_switch"},
    },
    "stick_directions": {
        "up":    {"action": "tap", "key": "up"},
        "down":  {"action": "tap", "key": "down"},
        "left":  {"action": "tap", "key": "left"},
        "right": {"action": "tap", "key": "right"},
    },
    # Which physical stick drives the direction mappings: "left" or "right".
    "stick_source": "right",
}

DEFAULT_CONFIG: dict = {
    "version": "1.0",
    "description": "Default Joy-Con R to keyboard mapping",
    "deadzone": DEFAULT_DEADZONE,
    "poll_interval": POLL_INTERVAL,
    "stick_mode": "4dir",
    "stick_enabled": True,
    "keep_alive_enabled": True,
    "mappings": DEFAULT_MAPPINGS,
}

DEFAULT_CONFIG_LEFT: dict = {
    "version": "1.0",
    "description": "Default Joy-Con L to keyboard mapping",
    "deadzone": DEFAULT_DEADZONE,
    "poll_interval": POLL_INTERVAL,
    "stick_mode": "4dir",
    "stick_enabled": True,
    "keep_alive_enabled": True,
    "mappings": DEFAULT_MAPPINGS_LEFT,
}

DEFAULT_CONFIG_DUAL: dict = {
    "version": "1.0",
    "description": "Default Joy-Con L+R to keyboard mapping",
    "deadzone": DEFAULT_DEADZONE,
    "poll_interval": POLL_INTERVAL,
    "stick_mode": "4dir",
    "stick_enabled": True,
    "keep_alive_enabled": True,
    "mappings": DEFAULT_MAPPINGS_DUAL,
}

DEFAULT_CONFIGS: dict[str, dict] = {
    "single_right": DEFAULT_CONFIG,
    "single_left": DEFAULT_CONFIG_LEFT,
    "dual": DEFAULT_CONFIG_DUAL,
}

VALID_ACTIONS = ("tap", "hold", "auto", "combination", "sequence", "window_switch", "macro", "exec")

__version__ = "1.2.0"
