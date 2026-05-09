"""Settings window for button mapping customization.

Uses a tabbed layout (Notebook) to separate button mappings
from the window switch app list.

Cross-platform: Windows and macOS.
"""

import sys
import logging
import ttkbootstrap as ttk
from ttkbootstrap.constants import (
    DANGER, DISABLED, INFO, LEFT, NORMAL, RIGHT, SECONDARY, SUCCESS,
    WARNING, X, W, BOTH,
)
from ttkbootstrap.dialogs import Messagebox

from .key_mapper import KeyMapper
from .resizable import ResizableMixin
from .window_switcher import WindowCycler, KNOWN_APPS, set_known_apps

logger = logging.getLogger(__name__)

EDITABLE_ACTIONS = ("tap", "hold", "auto", "combination", "sequence", "window_switch")
MAPPABLE_BUTTONS = ("A", "B", "X", "Y", "R", "ZR", "Plus", "Home", "RStick", "SL", "SR")

_UI_FONT = "Helvetica" if sys.platform == "darwin" else "Microsoft YaHei UI"

# Hover-tooltip text per action type. Looked up by current action_var value
# in _add_button_row's ⓘ tooltip. Keep each line short — tooltip width is ~36 chars.
ACTION_TOOLTIPS: dict[str, str] = {
    "tap": "按下立即点一次按键\n例：A → enter",
    "hold": "按住时持续按住按键，松开释放\n例：ZR → alt_r（语音输入）",
    "auto": "短按 = 点一次「短按键」\n长按 = 触发「长按键」\n两个框都填即可双映射\n长按填单键 = 持续按住（push-to-talk）\n长按填组合键 = 触发一次组合键",
    "combination": "按下立即触发组合键\n例：Y → cmd+tab",
    "sequence": "按住第一个键 + 依次点其他键\n例：alt+tab+tab（窗口循环）",
    "window_switch": "在已选应用之间循环切换窗口\n应用列表见「切换应用」tab",
}

# Common key names the user is most likely to need. Surfaced in the help banner
# and in the friendly error dialog when validation rejects an unknown key.
COMMON_KEYS_HELP = (
    "cmd / ctrl / alt(=option) / shift\n"
    "cmd_r / alt_r / ctrl_r / shift_r（右侧修饰键）\n"
    "enter / esc / space / tab / backspace\n"
    "a-z / 0-9 / f1-f12\n"
    "组合键用 + 连接，如 ctrl+1 或 cmd+shift+s"
)


def _make_tooltip(widget, text_provider) -> None:
    """Attach a simple hover tooltip to a widget.

    text_provider: either a static str or a callable() -> str so tooltips
    can change based on current state (e.g. selected action).
    """
    tip_state: dict = {"win": None}

    def show(_evt=None):
        if tip_state["win"] is not None:
            return
        try:
            text = text_provider() if callable(text_provider) else text_provider
        except Exception:
            return
        if not text:
            return
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tw = ttk.Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        lbl = ttk.Label(
            tw, text=text, font=(_UI_FONT, 9),
            bootstyle="inverse-secondary", padding=(8, 6),
            justify=LEFT,
        )
        lbl.pack()
        tip_state["win"] = tw

    def hide(_evt=None):
        tw = tip_state["win"]
        if tw is not None:
            try:
                tw.destroy()
            except Exception:
                pass
            tip_state["win"] = None

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<Destroy>", hide, add="+")


def _add_placeholder(entry: ttk.Entry, var: ttk.StringVar, placeholder: str) -> None:
    """Show greyed placeholder text in an Entry while it's empty and unfocused.
    Tk has no native placeholder, so we use FocusIn/FocusOut + a sentinel value.
    """
    PLACEHOLDER_FG = "#888888"
    # Track whether the current var content is the placeholder (vs real text)
    state = {"is_placeholder": False}

    def show_if_empty():
        if not var.get().strip():
            var.set(placeholder)
            entry.configure(foreground=PLACEHOLDER_FG)
            state["is_placeholder"] = True

    def on_focus_in(_evt=None):
        if state["is_placeholder"]:
            var.set("")
            entry.configure(foreground="")
            state["is_placeholder"] = False

    def on_focus_out(_evt=None):
        show_if_empty()

    entry.bind("<FocusIn>", on_focus_in, add="+")
    entry.bind("<FocusOut>", on_focus_out, add="+")
    show_if_empty()
    # Caller can read var.get() and treat the placeholder string as empty;
    # provide a helper attribute so _apply knows what to ignore.
    entry._placeholder_text = placeholder  # type: ignore[attr-defined]


class SettingsWindow(ResizableMixin):
    """Settings window for customizing button mappings and app list."""

    def __init__(
        self,
        parent,
        key_mapper: KeyMapper,
        config: dict,
        window_cycler: WindowCycler,
        main_window=None,
        mode: str = "single_right",
    ) -> None:
        self._key_mapper = key_mapper
        self._config = config
        self._window_cycler = window_cycler
        self._main_window = main_window
        self._mode = mode
        self._rows: dict[str, dict] = {}
        self._app_rows: list[dict] = []

        self._win = ttk.Toplevel(parent)
        self._win.title("键位设置")
        self._win.resizable(True, True)
        if sys.platform != "darwin":
            self._win.overrideredirect(True)
        self._win.minsize(420, 400)

        self._frameless = sys.platform != "darwin"
        self._build_ui()
        if self._frameless:
            self._setup_resize()
        self._center_on_parent(parent)

    def _build_ui(self) -> None:
        win = self._win

        # === Custom title bar ===
        titlebar = ttk.Frame(win, cursor="fleur")
        titlebar.pack(fill=X)

        ttk.Label(
            titlebar, text="  ⚙ 键位设置",
            font=(_UI_FONT, 12, "bold"), bootstyle=INFO,
        ).pack(side=LEFT, padx=(8, 0), pady=8)

        close_btn = ttk.Label(titlebar, text=" ✕ ", font=("", 11), bootstyle=DANGER, cursor="hand2")
        close_btn.pack(side=RIGHT, padx=(0, 4), pady=6)
        close_btn.bind("<Button-1>", lambda e: self._win.destroy())

        titlebar.bind("<ButtonPress-1>", self._start_drag)
        titlebar.bind("<B1-Motion>", self._do_drag)

        ttk.Separator(win).pack(fill=X)

        # === Tabs ===
        nb = ttk.Notebook(win)
        nb.pack(fill=BOTH, expand=True, padx=10, pady=(8, 0))

        tab_mapping = ttk.Frame(nb, padding=10)
        nb.add(tab_mapping, text=" 按键映射 ")

        tab_apps = ttk.Frame(nb, padding=10)
        nb.add(tab_apps, text=" 切换应用 ")

        self._build_mapping_tab(tab_mapping)
        self._build_apps_tab(tab_apps)

        # === Bottom buttons ===
        ttk.Separator(win).pack(fill=X, padx=16, pady=(8, 0))
        bottom = ttk.Frame(win, padding=(16, 10, 16, 12))
        bottom.pack(fill=X)

        ttk.Button(
            bottom, text="恢复默认",
            command=self._reset_defaults, bootstyle=WARNING, width=10,
        ).pack(side=LEFT)
        ttk.Button(
            bottom, text="取消",
            command=self._win.destroy, bootstyle=SECONDARY, width=8,
        ).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(
            bottom, text="应用",
            command=self._apply, bootstyle=SUCCESS, width=8,
        ).pack(side=RIGHT)

    # --- Tab 1: Button mappings ---

    def _build_mapping_tab(self, parent: ttk.Frame) -> None:
        from .constants import MAPPABLE_BUTTONS_BY_MODE, MODE_LABELS, DUAL_LEFT_BUTTONS

        # In dual mode, expose a stick_source picker (left-stick / right-stick
        # drives the direction mappings). Single modes only have one stick.
        self._stick_source_var = None
        if self._mode == "dual":
            ss_row = ttk.Frame(parent)
            ss_row.pack(fill=X, pady=(0, 8))
            ttk.Label(
                ss_row, text="方向数据来源：",
                font=(_UI_FONT, 10, "bold"),
            ).pack(side=LEFT)
            current = self._config.get("mappings", {}).get("stick_source", "right")
            self._stick_source_var = ttk.StringVar(value=current)
            ttk.Radiobutton(
                ss_row, text="右摇杆", variable=self._stick_source_var, value="right",
                bootstyle="info",
            ).pack(side=LEFT, padx=(8, 0))
            ttk.Radiobutton(
                ss_row, text="左摇杆", variable=self._stick_source_var, value="left",
                bootstyle="info",
            ).pack(side=LEFT, padx=(8, 0))
            ttk.Separator(parent).pack(fill=X, pady=(0, 6))

        # Header
        header = ttk.Frame(parent)
        header.pack(fill=X, pady=(0, 4))
        ttk.Label(header, text="按钮", font=(_UI_FONT, 9, "bold"), width=8).pack(side=LEFT)
        ttk.Label(
            header, text="动作类型",
            font=(_UI_FONT, 9, "bold"), width=14,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Label(
            header, text="按键",
            font=(_UI_FONT, 9, "bold"), width=14,
        ).pack(side=LEFT, padx=(8, 0))

        # Show which profile is being edited
        profile_label = MODE_LABELS.get(self._mode, self._mode)
        ttk.Label(
            header, text=f"[{profile_label}]",
            font=(_UI_FONT, 9), bootstyle="info",
        ).pack(side=RIGHT)

        ttk.Separator(parent).pack(fill=X, pady=(0, 4))

        # Layer 1: collapsible help banner — explains action types, key naming,
        # and the auto short/long-press semantics. Default collapsed so it
        # doesn't crowd the main UI for returning users.
        self._build_help_banner(parent)

        rows_frame = ttk.Frame(parent)
        rows_frame.pack(fill=BOTH, expand=True)

        # Column header
        header = ttk.Frame(rows_frame)
        header.pack(fill=X, pady=(0, 4))
        ttk.Label(header, text="", width=2).pack(side=LEFT, padx=(0, 4))  # badge col
        ttk.Label(header, text="按键", font=(_UI_FONT, 9, "bold"), width=8).pack(side=LEFT)
        ttk.Label(header, text="短按动作", font=(_UI_FONT, 9, "bold"), width=12).pack(side=LEFT, padx=(8, 0))
        ttk.Label(header, text="短按键", font=(_UI_FONT, 9, "bold"), width=14).pack(side=LEFT, padx=(8, 0))
        ttk.Label(header, text="长按键 (组合)", font=(_UI_FONT, 9, "bold"), width=18).pack(side=LEFT, padx=(8, 0))

        mappable_buttons = MAPPABLE_BUTTONS_BY_MODE.get(self._mode, ())
        mappings = self._config.get("mappings", {}).get("buttons", {})

        if self._mode == "dual":
            # Group by side. DUAL_LEFT_BUTTONS lists left-side names.
            left_btns = [b for b in mappable_buttons if b in DUAL_LEFT_BUTTONS]
            right_btns = [b for b in mappable_buttons if b not in DUAL_LEFT_BUTTONS]

            ttk.Label(
                rows_frame, text="左手柄",
                font=(_UI_FONT, 10, "bold"), bootstyle="secondary",
            ).pack(anchor=W, pady=(2, 2))
            for btn_name in left_btns:
                self._add_button_row(rows_frame, btn_name, mappings.get(btn_name, {}))

            ttk.Separator(rows_frame).pack(fill=X, pady=(8, 4))
            ttk.Label(
                rows_frame, text="右手柄",
                font=(_UI_FONT, 10, "bold"), bootstyle="secondary",
            ).pack(anchor=W, pady=(2, 2))
            for btn_name in right_btns:
                self._add_button_row(rows_frame, btn_name, mappings.get(btn_name, {}))
        else:
            for btn_name in mappable_buttons:
                self._add_button_row(rows_frame, btn_name, mappings.get(btn_name, {}))

    def _build_help_banner(self, parent: ttk.Frame) -> None:
        """Layer 1: collapsible help banner with concise usage tips.
        Default collapsed (▶); click toggles to expanded (▼) and shows help body.
        """
        banner = ttk.Frame(parent)
        banner.pack(fill=X, pady=(0, 4))

        expanded = {"v": False}
        toggle_btn = ttk.Button(banner, text="▶ 使用说明", bootstyle="link", cursor="hand2")
        toggle_btn.pack(anchor=W)

        body = ttk.Frame(banner, bootstyle="secondary")
        body_text = (
            "• 短按动作：\n"
            "    tap = 点一下 / hold = 按住 / auto = 短按+长按双映射\n"
            "    combination = 组合键 / sequence = 按住第一个+依次点其他\n"
            "• 短按键 / 长按键：单键如 enter；组合键用 + 连接，如 cmd+s\n"
            "• 常用键名：" + COMMON_KEYS_HELP.replace("\n", "\n              ") + "\n"
            "• auto 长按规则：\n"
            "    填单键(如 alt_r) = 持续按住直到松开（push-to-talk）\n"
            "    填组合键(如 cmd+backspace) = 触发一次组合键"
        )
        ttk.Label(
            body, text=body_text, font=(_UI_FONT, 9),
            justify=LEFT, padding=(8, 6),
        ).pack(anchor=W, fill=X)

        def toggle():
            if expanded["v"]:
                body.pack_forget()
                toggle_btn.configure(text="▶ 使用说明")
                expanded["v"] = False
            else:
                body.pack(fill=X, pady=(2, 0))
                toggle_btn.configure(text="▼ 使用说明（点击收起）")
                expanded["v"] = True

        toggle_btn.configure(command=toggle)

    def _add_button_row(self, parent: ttk.Frame, btn_name: str, mapping: dict) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=2)

        # Dual-mapping badge: shows "双" (dual) when an auto action has long_keys configured,
        # so users can see at a glance which buttons have both short+long press behavior.
        badge_var = ttk.StringVar(value="")
        badge = ttk.Label(row, textvariable=badge_var, font=(_UI_FONT, 9, "bold"),
                          width=2, bootstyle="success-inverse", anchor="center")
        badge.pack(side=LEFT, padx=(0, 4))

        ttk.Label(row, text=btn_name, font=(_UI_FONT, 10), width=8).pack(side=LEFT)

        current_action = mapping.get("action", "tap")
        action_var = ttk.StringVar(value=current_action)
        action_cb = ttk.Combobox(
            row, textvariable=action_var, values=EDITABLE_ACTIONS,
            state="readonly", width=12, bootstyle=INFO,
        )
        action_cb.pack(side=LEFT, padx=(8, 0))

        # Layer 2: ⓘ tooltip — hovering shows action-specific help.
        # Text is dynamic: changes whenever action_var changes.
        info_lbl = ttk.Label(row, text="ⓘ", font=(_UI_FONT, 10), bootstyle="info", cursor="hand2")
        info_lbl.pack(side=LEFT, padx=(2, 0))
        _make_tooltip(info_lbl, lambda: ACTION_TOOLTIPS.get(action_var.get(), ""))

        current_key = ""
        if current_action in ("tap", "hold"):
            current_key = mapping.get("key", "")
        elif current_action == "auto":
            # Prefer short_keys (combo) display; fall back to single key
            short_keys = mapping.get("short_keys")
            if short_keys:
                current_key = "+".join(short_keys)
            else:
                current_key = mapping.get("key", "")
        elif current_action in ("combination", "sequence"):
            current_key = "+".join(mapping.get("keys", []))

        key_var = ttk.StringVar(value=current_key)
        key_entry = ttk.Entry(row, textvariable=key_var, width=14, bootstyle=SECONDARY)

        # Long-press key entry — only meaningful for `auto` action.
        # Accepts a single key or a combination like "cmd+backspace".
        # Empty means "no special long-press behavior" (auto falls back to hold).
        long_keys = mapping.get("long_keys") or []
        long_var = ttk.StringVar(value="+".join(long_keys))
        long_entry = ttk.Entry(row, textvariable=long_var, width=16, bootstyle=SECONDARY)

        def update_badge(*_):
            # Show "双" badge when this row has both a short-press key AND a long-press combo.
            # Treat placeholder text as empty (placeholder strings live in _placeholder_text).
            long_raw = long_var.get().strip()
            ph = getattr(long_entry, "_placeholder_text", None)
            if ph and long_raw == ph:
                long_raw = ""
            if action_var.get() == "auto" and long_raw:
                badge_var.set("双")
            else:
                badge_var.set("")

        long_var.trace_add("write", update_badge)
        update_badge()

        def on_action_change(event=None):
            action = action_var.get()
            if action == "window_switch":
                key_entry.configure(state=DISABLED)
                key_var.set("")
            else:
                key_entry.configure(state=NORMAL)
                if action in ("combination", "sequence"):
                    key_entry.configure(bootstyle=INFO)
                else:
                    key_entry.configure(bootstyle=SECONDARY)
            # Long-press field only enabled for `auto`
            if action == "auto":
                long_entry.configure(state=NORMAL)
            else:
                long_entry.configure(state=DISABLED)
                long_var.set("")
            update_badge()

        action_cb.bind("<<ComboboxSelected>>", on_action_change)

        if current_action == "window_switch":
            key_entry.configure(state=DISABLED)
        elif current_action == "macro":
            action_var.set(current_action)
            action_cb.configure(state=DISABLED)
            key_entry.configure(state=DISABLED)

        key_entry.pack(side=LEFT, padx=(8, 0))
        long_entry.pack(side=LEFT, padx=(8, 0))
        if current_action != "auto":
            long_entry.configure(state=DISABLED)

        # Layer 3: placeholders. Hint at expected formats so users don't have
        # to guess. Only attached on rows where the entries are actually
        # editable (skip window_switch / macro which are disabled).
        if current_action != "window_switch" and current_action != "macro":
            _add_placeholder(key_entry, key_var, "如 enter / cmd+s")
        if current_action == "auto":
            _add_placeholder(long_entry, long_var, "如 alt_r 或 cmd+backspace")

        self._rows[btn_name] = {
            "action_var": action_var,
            "key_var": key_var,
            "action_cb": action_cb,
            "key_entry": key_entry,
            "long_var": long_var,
            "long_entry": long_entry,
        }

    # --- Tab 2: Window switch apps ---

    def _build_apps_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="设置 R 键可在哪些应用间切换窗口：",
            font=(_UI_FONT, 10),
        ).pack(anchor=W, pady=(0, 8))

        # Header
        header = ttk.Frame(parent)
        header.pack(fill=X, pady=(0, 4))
        ttk.Label(
            header, text="应用名称",
            font=(_UI_FONT, 9, "bold"), width=18,
        ).pack(side=LEFT)
        ttk.Label(
            header, text="EXE 名称",
            font=(_UI_FONT, 9, "bold"), width=20,
        ).pack(side=LEFT, padx=(8, 0))
        # placeholder for delete column
        ttk.Label(header, text="  ", width=4).pack(side=LEFT)

        ttk.Separator(parent).pack(fill=X, pady=(0, 4))

        self._app_list_frame = ttk.Frame(parent)
        self._app_list_frame.pack(fill=BOTH, expand=True)

        saved_apps = self._config.get("known_apps")
        source = saved_apps if saved_apps else KNOWN_APPS
        for display_name, exe_name in source.items():
            self._add_app_row(display_name, exe_name)

        ttk.Button(
            parent, text="＋ 添加应用", command=lambda: self._add_app_row(),
            bootstyle=SUCCESS, width=14,
        ).pack(anchor=W, pady=(8, 0))

    def _add_app_row(self, display_name: str = "", exe_name: str = "") -> None:
        row = ttk.Frame(self._app_list_frame)
        row.pack(fill=X, pady=2)

        name_var = ttk.StringVar(value=display_name)
        exe_var = ttk.StringVar(value=exe_name)

        name_entry = ttk.Entry(row, textvariable=name_var, width=18, bootstyle=SECONDARY)
        name_entry.pack(side=LEFT)

        ttk.Label(row, text="→", font=("", 10)).pack(side=LEFT, padx=4)

        exe_entry = ttk.Entry(row, textvariable=exe_var, width=18, bootstyle=SECONDARY)
        exe_entry.pack(side=LEFT)

        verify_btn = ttk.Button(row, text="验证", bootstyle=INFO, width=4)
        verify_btn.pack(side=LEFT, padx=(4, 0))
        verify_btn.configure(command=lambda n=name_var, e=exe_var: self._verify_app(n.get(), e.get()))

        del_btn = ttk.Label(row, text=" ✕ ", font=("", 10), bootstyle=DANGER, cursor="hand2")
        del_btn.pack(side=LEFT, padx=(4, 0))
        del_btn.bind("<Button-1>", lambda e, r=row: r.destroy())

        self._app_rows.append({"frame": row, "name_var": name_var, "exe_var": exe_var})

    def _verify_app(self, display_name: str, exe_name: str) -> None:
        """Check if the given app exists/is running."""
        display_name = display_name.strip()
        exe_name = exe_name.strip()

        if not display_name or not exe_name:
            Messagebox.show_warning("应用名称和 EXE 名称不能为空", title="验证失败", parent=self._win)
            return

        if sys.platform == "darwin":
            from AppKit import NSWorkspace
            apps = NSWorkspace.sharedWorkspace().runningApplications()
            found_app = None
            for app in apps:
                name = app.localizedName()
                if name and str(name) == exe_name:
                    found_app = app
                    break

            if found_app:
                Messagebox.show_info(
                    f"验证成功！\n\n找到了后台运行的应用进程。\n\n"
                    f"识别的进程名: {found_app.localizedName()}\n"
                    f"PID: {found_app.processIdentifier()}",
                    title="验证结果",
                    parent=self._win
                )
            else:
                Messagebox.show_warning(
                    f"验证失败。\n\n未找到任何与 '{exe_name}' 匹配的活动进程。\n\n"
                    f"请确保：\n1. 应用当前正在运行\n"
                    f"2. 检查活动监视器中显示的名称与 '{exe_name}' 是否完全一致\n"
                    f"注意：名称区分大小写，例如 Chrome 应配置为 'Google Chrome'",
                    title="验证结果",
                    parent=self._win
                )
        else:
            # Fallback for Windows using find_windows logic
            from .window_switcher import find_windows
            windows = find_windows([exe_name])

            if windows:
                Messagebox.show_info(
                    f"验证成功！\n\n找到了匹配的应用。\n\n"
                    f"当前识别的进程名: {windows[0].app_name}",
                    title="验证结果",
                    parent=self._win
                )
            else:
                Messagebox.show_warning(
                    f"验证失败。\n\n未找到与 '{exe_name}' 匹配的应用。\n\n"
                    f"请确保：\n1. 应用当前正在运行\n"
                    f"2. 任务管理器中的名称与配置一致",
                    title="验证结果",
                    parent=self._win
                )

    def _collect_apps(self) -> tuple[dict[str, str], list[str]]:
        apps = {}
        errors = []
        for widgets in self._app_rows:
            if not widgets["frame"].winfo_exists():
                continue
            name = widgets["name_var"].get().strip()
            exe = widgets["exe_var"].get().strip()
            if not name and not exe:
                continue
            if not name:
                errors.append("应用名称不能为空")
                continue
            if not exe:
                errors.append(f"{name} 的 EXE 名称不能为空")
                continue
            # Don't lowercase: macOS process names (kCGWindowOwnerName) are case-
            # sensitive — "Antigravity" and "antigravity" are different. On Windows,
            # exe-name comparison is already case-insensitive in find_windows.
            apps[name] = exe
        return apps, errors

    # --- Apply / Reset ---

    def _apply(self) -> None:
        errors = []
        new_mappings = {}

        for btn_name, widgets in self._rows.items():
            action = widgets["action_var"].get()
            # Read raw values, then strip placeholders. _add_placeholder writes
            # the placeholder string into the var when the entry is empty+unfocused;
            # if we don't filter it, "如 enter / cmd+s" would be saved as a key.
            def _real(entry_widget, var) -> str:
                raw = var.get().strip()
                placeholder = getattr(entry_widget, "_placeholder_text", None)
                if placeholder and raw == placeholder:
                    return ""
                return raw
            key = _real(widgets["key_entry"], widgets["key_var"])
            if action in ("tap", "hold", "auto"):
                if not key:
                    errors.append(f"{btn_name}: 按键不能为空")
                    continue
                # auto + short key contains "+" or "," → store as short_keys (combo);
                # otherwise store as single `key`. tap/hold always single key.
                if action == "auto" and ("+" in key or "," in key or "，" in key):
                    short_keys = [k.strip() for k in key.replace("+", ",").replace("，", ",").split(",") if k.strip()]
                    entry = {"action": action, "short_keys": short_keys}
                else:
                    entry = {"action": action, "key": key}
                if action == "auto":
                    # Preserve `repeat` field (controls re-tap interval on long press,
                    # e.g. backspace deleting many chars). The settings UI doesn't expose
                    # this field, so carry it forward from the existing config.
                    old = self._config["mappings"]["buttons"].get(btn_name, {})
                    if old.get("action") == "auto" and "repeat" in old:
                        entry["repeat"] = old["repeat"]
                    # Long-press combination from UI ("cmd+backspace" → ["cmd", "backspace"])
                    long_raw = _real(widgets.get("long_entry"), widgets.get("long_var")) if widgets.get("long_var") else ""
                    if long_raw:
                        long_keys = [k.strip() for k in long_raw.replace("+", ",").replace("，", ",").split(",") if k.strip()]
                        if long_keys:
                            entry["long_keys"] = long_keys
                new_mappings[btn_name] = entry
            elif action in ("combination", "sequence"):
                keys = [k.strip() for k in key.replace("+", ",").replace("，", ",").split(",") if k.strip()]
                if not keys:
                    errors.append(f"{btn_name}: {action} 至少需要一个按键")
                    continue
                entry = {"action": action, "keys": keys}
                if action == "sequence":
                    old = self._config["mappings"]["buttons"].get(btn_name, {})
                    if old.get("action") == "sequence" and "repeat" in old:
                        entry["repeat"] = old["repeat"]
                new_mappings[btn_name] = entry
            elif action == "window_switch":
                new_mappings[btn_name] = {"action": "window_switch"}
            else:
                new_mappings[btn_name] = self._config["mappings"]["buttons"].get(btn_name, {})

        apps, app_errors = self._collect_apps()
        errors.extend(app_errors)

        # Run the same validator the loader uses, so users see the exact problems
        # the engine would otherwise reject silently (unknown key names, malformed
        # short_keys/long_keys, etc.). Validate against a temp config that has only
        # the new mappings under the current mode.
        from .config_loader import _validate_mapping_entry
        for btn_name, entry in new_mappings.items():
            entry_errors = _validate_mapping_entry(btn_name, entry)
            errors.extend(entry_errors)

        if errors:
            # Friendly error: if any error mentions an invalid key name, append
            # the common-keys cheat sheet so the user can fix it without docs.
            msg = "\n".join(errors)
            if "invalid key" in msg or "key name" in msg:
                msg += "\n\n常用键名：\n" + COMMON_KEYS_HELP
            Messagebox.show_warning(msg, title="配置错误", parent=self._win)
            return

        # Apply button mappings to current profile
        self._config["mappings"]["buttons"].update(new_mappings)

        # Persist dual-mode stick_source choice
        if self._mode == "dual" and self._stick_source_var is not None:
            self._config["mappings"]["stick_source"] = self._stick_source_var.get()

        # Also update profiles dict for persistence
        profiles = self._config.get("profiles", {})
        if self._mode in profiles:
            profiles[self._mode]["mappings"]["buttons"].update(new_mappings)
            # Sync stick_directions as well
            stick_dirs = self._config["mappings"].get("stick_directions", {})
            if stick_dirs:
                profiles[self._mode]["mappings"]["stick_directions"] = stick_dirs
            # Sync stick_source for dual profile
            if self._mode == "dual" and self._stick_source_var is not None:
                profiles[self._mode]["mappings"]["stick_source"] = self._stick_source_var.get()

        # Rebuild key_mapper with switch_profile
        self._key_mapper.switch_profile(self._config, self._mode)

        # Apply app list
        set_known_apps(apps)
        self._window_cycler.app_names = list(apps.values())

        # Refresh main window app checkboxes
        if self._main_window:
            self._main_window.refresh_apps()

        # Save config to disk
        from .config_loader import save_config
        self._config["known_apps"] = apps
        save_config(self._config)

        logger.info("Settings applied. Apps: %s", apps)
        self._win.destroy()

    def _reset_defaults(self) -> None:
        from .constants import DEFAULT_CONFIGS, MAPPABLE_BUTTONS_BY_MODE

        default_cfg = DEFAULT_CONFIGS.get(self._mode, {})
        defaults = default_cfg.get("mappings", {}).get("buttons", {})
        mappable_buttons = MAPPABLE_BUTTONS_BY_MODE.get(self._mode, MAPPABLE_BUTTONS)
        for btn_name in mappable_buttons:
            mapping = defaults.get(btn_name, {})
            widgets = self._rows.get(btn_name)
            if not widgets:
                continue
            action = mapping.get("action", "tap")
            widgets["action_var"].set(action)
            # Restore long_keys for auto action; clear & disable otherwise
            long_var = widgets.get("long_var")
            long_entry = widgets.get("long_entry")
            if action == "auto":
                if long_var is not None:
                    long_var.set("+".join(mapping.get("long_keys", []) or []))
                if long_entry is not None:
                    long_entry.configure(state=NORMAL)
            else:
                if long_var is not None:
                    long_var.set("")
                if long_entry is not None:
                    long_entry.configure(state=DISABLED)
            if action in ("tap", "hold", "auto"):
                if action == "auto" and mapping.get("short_keys"):
                    widgets["key_var"].set("+".join(mapping["short_keys"]))
                else:
                    widgets["key_var"].set(mapping.get("key", ""))
                widgets["key_entry"].configure(state=NORMAL)
                widgets["action_cb"].configure(state="readonly")
            elif action in ("combination", "sequence"):
                widgets["key_var"].set("+".join(mapping.get("keys", [])))
                widgets["key_entry"].configure(state=NORMAL)
                widgets["action_cb"].configure(state="readonly")
            elif action == "window_switch":
                widgets["key_var"].set("")
                widgets["key_entry"].configure(state=DISABLED)
                widgets["action_cb"].configure(state="readonly")
            else:
                widgets["action_var"].set(action)
                widgets["action_cb"].configure(state=DISABLED)
                widgets["key_entry"].configure(state=DISABLED)

        # Reset dual stick_source to default ("right")
        if self._mode == "dual" and self._stick_source_var is not None:
            default_ss = default_cfg.get("mappings", {}).get("stick_source", "right")
            self._stick_source_var.set(default_ss)

        for widgets in self._app_rows:
            if widgets["frame"].winfo_exists():
                widgets["frame"].destroy()
        self._app_rows.clear()
        for name, exe in {"VS Code": "code.exe", "飞书": "feishu.exe"}.items():
            self._add_app_row(name, exe)

    # --- Window utilities ---

    def _center_on_parent(self, parent) -> None:
        self._win.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        w, h = self._win.winfo_width(), self._win.winfo_height()
        self._win.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _start_drag(self, event) -> None:
        self._drag_x, self._drag_y = event.x, event.y

    def _do_drag(self, event) -> None:
        x = self._win.winfo_x() + event.x - self._drag_x
        y = self._win.winfo_y() + event.y - self._drag_y
        self._win.geometry(f"+{x}+{y}")
