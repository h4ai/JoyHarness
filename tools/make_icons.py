"""Generate the JoyVoice app icon and menu-bar status icons.

If assets/icons/source/app_source.png exists it is used as the master.
If assets/icons/source/menubar_source.png exists it is used as the
"connected" template (others are derived from it programmatically).
Otherwise a procedural icon is generated.

Run:  python tools/make_icons.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "assets" / "icons"
ICONSET_DIR = ICONS_DIR / "AppIcon.iconset"
SOURCE_DIR = ICONS_DIR / "source"
APP_SOURCE = SOURCE_DIR / "app_source.png"
MENUBAR_SOURCE = SOURCE_DIR / "menubar_source.png"

JOYCON_RED = (255, 60, 40)
JOYCON_RED_DEEP = (190, 30, 20)
BLACK = (20, 20, 26)


def make_app_icon(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Vertical gradient red → deep red
    grad = Image.new("RGBA", (size, size), JOYCON_RED + (255,))
    g_draw = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        r = int(JOYCON_RED[0] * (1 - t) + JOYCON_RED_DEEP[0] * t)
        g = int(JOYCON_RED[1] * (1 - t) + JOYCON_RED_DEEP[1] * t)
        b = int(JOYCON_RED[2] * (1 - t) + JOYCON_RED_DEEP[2] * t)
        g_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # macOS-style squircle mask
    radius = int(size * 0.225)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size, size], radius=radius, fill=255,
    )
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg.paste(grad, (0, 0), mask)

    # Subtle highlight on top
    hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse(
        [-size * 0.4, -size * 0.6, size * 1.4, size * 0.5],
        fill=(255, 255, 255, 38),
    )
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(hl, (0, 0), mask)
    bg = Image.alpha_composite(bg, out)

    img = Image.alpha_composite(img, bg)
    draw = ImageDraw.Draw(img, "RGBA")

    cx, cy = size / 2, size / 2

    # Drop shadow under face
    face_r = size * 0.30
    face_box = [cx - face_r, cy - face_r, cx + face_r, cy + face_r]
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [face_box[0] + size * 0.01, face_box[1] + size * 0.04,
         face_box[2] + size * 0.01, face_box[3] + size * 0.04],
        fill=(0, 0, 0, 130),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.025))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img, "RGBA")

    # White face circle
    draw.ellipse(face_box, fill=(248, 248, 252, 255))
    inner_r = face_r * 0.88
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        outline=(0, 0, 0, 30), width=max(2, int(size * 0.004)),
    )

    # Four directional dots (cluster)
    dot_r = face_r * 0.16
    offset = face_r * 0.46
    for dx, dy, color in [
        (0, -offset, JOYCON_RED),
        (offset, 0, (60, 60, 70)),
        (0, offset, (60, 60, 70)),
        (-offset, 0, (60, 60, 70)),
    ]:
        draw.ellipse(
            [cx + dx - dot_r, cy + dy - dot_r, cx + dx + dot_r, cy + dy + dot_r],
            fill=color + (255,),
        )

    # Center microphone pill
    mic_w = face_r * 0.22
    mic_h = face_r * 0.42
    draw.rounded_rectangle(
        [cx - mic_w / 2, cy - mic_h / 2, cx + mic_w / 2, cy + mic_h / 2],
        radius=mic_w / 2, fill=BLACK + (255,),
    )
    stand_w = mic_w * 0.18
    stand_top = cy + mic_h / 2 + size * 0.005
    stand_bot = stand_top + size * 0.025
    draw.rounded_rectangle(
        [cx - stand_w / 2, stand_top, cx + stand_w / 2, stand_bot],
        radius=stand_w / 2, fill=BLACK + (255,),
    )

    return img


def make_menubar_icon(state: str, px: int = 44, source: Image.Image | None = None) -> Image.Image:
    """Pure-black template image (system tints for light/dark mode).

    If `source` is given it is treated as the master "connected" template;
    other states are derived from it (low_battery/charging overlay glyph,
    disconnected = source thinned to outline-ish via dilate-difference).
    """
    if source is not None:
        return _menubar_from_source(state, source, px)

    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    cx, cy = px / 2, px / 2
    r_outer = px * 0.42
    stroke = max(2, int(px * 0.09))

    if state == "disconnected":
        draw.ellipse(
            [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
            outline=(0, 0, 0, 255), width=stroke,
        )
    elif state == "connected":
        draw.ellipse(
            [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
            fill=(0, 0, 0, 255),
        )
    elif state == "low_battery":
        body_w, body_h = px * 0.62, px * 0.36
        x0, y0 = cx - body_w / 2, cy - body_h / 2
        draw.rounded_rectangle(
            [x0, y0, x0 + body_w, y0 + body_h],
            radius=px * 0.05, outline=(0, 0, 0, 255), width=stroke,
        )
        cap_w, cap_h = px * 0.06, body_h * 0.5
        draw.rounded_rectangle(
            [x0 + body_w, cy - cap_h / 2,
             x0 + body_w + cap_w, cy + cap_h / 2],
            radius=cap_w / 2, fill=(0, 0, 0, 255),
        )
        sliver_w = max(2, body_w * 0.18)
        pad = max(1, stroke * 0.6)
        sx0 = x0 + stroke + pad
        sy0 = y0 + stroke + pad
        sx1 = sx0 + sliver_w
        sy1 = y0 + body_h - stroke - pad
        if sy1 > sy0 and sx1 > sx0:
            draw.rectangle([sx0, sy0, sx1, sy1], fill=(0, 0, 0, 255))
    elif state == "charging":
        draw.ellipse(
            [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
            fill=(0, 0, 0, 255),
        )
        bolt = [
            (cx + px * 0.04, cy - px * 0.22),
            (cx - px * 0.10, cy + px * 0.02),
            (cx - px * 0.01, cy + px * 0.02),
            (cx - px * 0.04, cy + px * 0.22),
            (cx + px * 0.10, cy - px * 0.02),
            (cx + px * 0.01, cy - px * 0.02),
        ]
        draw.polygon(bolt, fill=(0, 0, 0, 0))

    return img


def _menubar_from_source(state: str, source: Image.Image, px: int) -> Image.Image:
    """Derive a 4-state colored menu-bar icon from the user's silhouette.

    Each state is rendered in a distinctive flat color so the user can
    tell connection state at a glance (the macOS template-tinting is
    intentionally bypassed by the caller — see macos_status_bar._set_icon).

    State → color:
      disconnected → white     (RGB 240,240,240)
      connected    → blue      (RGB  0,195,255)
      low_battery  → yellow    (RGB 255,200, 50)
      charging     → green     (RGB  60,200,120)
    """
    state_color = {
        "disconnected": (240, 240, 240),
        "connected":    (0, 195, 255),
        "low_battery":  (255, 200, 50),
        "charging":     (60, 200, 120),
    }
    color = state_color.get(state, (255, 255, 255))

    base = source.convert("RGBA")
    # Replace the silhouette color with the state color, keep the alpha.
    r, g, b, a = base.split()
    cr = Image.new("L", base.size, color[0])
    cg = Image.new("L", base.size, color[1])
    cb = Image.new("L", base.size, color[2])
    base = Image.merge("RGBA", (cr, cg, cb, a))
    base = base.resize((px, px), Image.LANCZOS)
    return base


ICONSET_SIZES = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
]


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    ICONSET_DIR.mkdir(parents=True, exist_ok=True)

    if APP_SOURCE.exists():
        print(f"Using user app source: {APP_SOURCE}")
        master = Image.open(APP_SOURCE).convert("RGBA")
        if master.size != (1024, 1024):
            print(f"  resizing {master.size} → 1024x1024")
            master = master.resize((1024, 1024), Image.LANCZOS)
    else:
        print("Rendering procedural 1024px master…")
        master = make_app_icon(1024)

    master.save(ICONS_DIR / "AppIcon-1024.png")

    print("Rendering iconset variants…")
    for base, scale in ICONSET_SIZES:
        size = base * scale
        scaled = master.resize((size, size), Image.LANCZOS)
        suffix = f"{base}x{base}" + ("@2x" if scale == 2 else "")
        scaled.save(ICONSET_DIR / f"icon_{suffix}.png")

    print("Compiling AppIcon.icns…")
    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET_DIR),
         "-o", str(ICONS_DIR / "AppIcon.icns")],
        check=True,
    )

    print("Rendering menu-bar template images (22pt @1x/@2x/@3x)…")
    # If the user supplied a clean black-on-transparent menubar source,
    # use it as the master template for all four states. Otherwise fall
    # back to the procedural glyph (kept simple for legibility at ~22 px).
    menubar_src: Image.Image | None = None
    if MENUBAR_SOURCE.exists():
        print(f"Using user menu-bar source: {MENUBAR_SOURCE}")
        menubar_src = Image.open(MENUBAR_SOURCE).convert("RGBA")

    for state in ["connected", "disconnected", "low_battery", "charging"]:
        for scale, px in [(1, 22), (2, 44), (3, 66)]:
            img = make_menubar_icon(state, px=px, source=menubar_src)
            suffix = "" if scale == 1 else f"@{scale}x"
            img.save(ICONS_DIR / f"menubar_{state}{suffix}.png")

    print("Done. Icons in:", ICONS_DIR)


if __name__ == "__main__":
    main()
