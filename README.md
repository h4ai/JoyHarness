# JoyHarness

JoyHarness 将 Nintendo Switch Joy-Con 通过蓝牙映射为键盘快捷键，支持 `single_right`、`single_left`、`dual` 三种连接模式，并根据当前连接状态自动切换配置。

支持 Windows 11 和 macOS 13+。

## 界面预览

| Windows | macOS |
|---------|-------|
| ![Windows](assets/screenshot.png) | ![macOS](assets/screenshot-mac.png) |

## 功能

- 自动识别单右、单左、双 Joy-Con，并热切换到对应 profile
- 支持 `tap`、`hold`、`auto`、`combination`、`sequence`、`macro`、`window_switch`、`exec`
- 支持摇杆方向映射、死区设置、4 向 / 8 向模式
- 支持 Joy-Con 断开后后台持续扫描并自动恢复
- 支持 HID 电量读取和保活防休眠
- Windows 使用系统托盘运行，macOS 使用菜单栏图标运行
- macOS 支持打包为 `JoyHarness.app`
- 启动时强制单实例，避免重复占用手柄和重复创建托盘 / 菜单栏图标

## 环境要求

- Windows 11 或 macOS 13+
- Python 3.10+
- Joy-Con 已完成蓝牙配对

## 安装

```bash
pip install -r requirements.txt
```

依赖按平台自动分流：

- Windows: `keyboard`
- macOS: `pynput`、PyObjC

## 运行

```bash
python -m src
```

也支持：

```bash
python src/main.py
```

平台行为：

- macOS: 默认以菜单栏应用运行，主窗口启动后会自动隐藏，需要从菜单栏图标打开
- Windows: 主窗口和系统托盘同时启动

辅助启动方式：

```bash
./start.command
```

Windows 也可以双击 `start.vbs`。

## 常用命令

```bash
python -m src --discover
python -m src --list-controls
python -m src --config config/my.json
python -m src --deadzone 0.2
python -m src --joystick 0
python -m src --verbose
python -m src --no-admin-warn
```

说明：

- `--discover`: 打印原始按钮 / 轴索引，用于校准 SDL2 映射
- `--list-controls`: 输出当前激活 profile 的按键映射
- `--config`: 指定配置文件
- `--deadzone`: 临时覆盖死区
- `--joystick`: 为 `--discover` 指定 SDL2 设备索引
- `--verbose`: 开启调试日志，并写入 `nsjc.log`
- `--no-admin-warn`: 跳过启动时权限 / 管理员提示

## 蓝牙配对

1. 打开系统蓝牙设置
2. 按住 Joy-Con 滑轨上的配对按钮约 3 秒
3. 等待指示灯快速闪烁
4. 在系统蓝牙列表中连接对应 Joy-Con
5. 首次使用建议运行 `python -m src --discover` 验证索引

## macOS 说明

首次运行需要授权：

- 辅助功能
- 输入监控

程序在缺少权限时会主动弹出说明，并可直接打开对应系统设置页面。

另外需要注意：

- 部分系统功能只响应真实 HID 事件，不响应 `pynput` 合成按键。此时应使用 `exec`，例如 `open -a "Mission Control"`
- `window_switch` 只能看到当前 Space 中的窗口
- `if_window` / `window_switch` 使用的进程名区分大小写，也受系统语言影响，例如 `微信` 不是 `WeChat`
- 在 macOS SDL2 下，左 Joy-Con 的 `SL` 和 `Minus` 可能无法稳定产生事件

## 配置文件

配置目录为 `config/`。

加载优先级：

1. `--config <file>`
2. `config/user.json`
3. `config/user-macos.json` 或 `config/user-windows.json`
4. 内置默认配置

常见顶层字段：

- `deadzone`
- `poll_interval`
- `stick_mode`
- `stick_enabled`
- `keep_alive_enabled`
- `switch_scroll_interval`
- `selected_apps`
- `known_apps`（应用显示名到进程名的映射）
- `profiles`

### 连接模式

| 模式 | 按钮命名 |
|------|----------|
| `single_right` | `A B X Y R ZR Plus Home RStick SL SR` |
| `single_left` | `A B X Y L ZL Minus Capture LStick SL SR` |
| `dual` | `L_A L_B L_X L_Y L ZL Minus Capture LStick SL_L SR_L R_A R_B R_X R_Y R ZR Plus Home RStick SL_R SR_R` |

`dual` 模式下，左右 Joy-Con 的 `A/B/X/Y` 被拆分为 `L_*` 和 `R_*`，避免命名冲突。

### 动作类型

| 动作 | 说明 |
|------|------|
| `tap` | 按下后立即释放 |
| `hold` | 按下保持，松开释放 |
| `auto` | 短按和长按执行不同逻辑，可选 `repeat` 实现连发 |
| `combination` | 一次发送组合键 |
| `sequence` | 先按修饰键再按目标键，可选重复 |
| `window_switch` | 交给窗口切换器处理 |
| `macro` | 多步骤动作，可加 `if_window` 条件 |
| `exec` | 执行外部命令 |

`auto` 额外支持：

- `key`: 短按默认键
- `short_keys`: 短按改为发送组合键
- `long_keys`: 长按时发送单键保持或一次性组合键
- `repeat`: 自动重复间隔，单位毫秒

### 配置示例

```json
{
  "deadzone": 0.2,
  "stick_mode": "4dir",
  "keep_alive_enabled": true,
  "profiles": {
    "single_right": {
      "mappings": {
        "buttons": {
          "R": { "action": "window_switch" },
          "ZR": { "action": "hold", "key": "alt_r" },
          "Plus": { "action": "hold", "key": "cmd_r" },
          "Home": { "action": "combination", "keys": ["cmd", "space"] }
        },
        "stick_directions": {
          "up": { "action": "auto", "key": "down", "repeat": 100 }
        }
      }
    }
  }
}
```

## 校准与排错

如果按钮不响应或映射错位，优先做这几件事：

1. 运行 `python -m src --discover`
2. 检查当前 SDL2 下按钮索引是否和 `src/constants.py` 一致
3. 确认 macOS 权限是否已授予
4. 确认没有第二个 JoyHarness 实例在后台运行

项目还提供独立校准脚本：

```bash
python calibrate.py
```

## 打包 macOS App

构建入口是 `pyinstaller_entry.py`，spec 文件是 `joyvoice.spec`：

```bash
pyinstaller joyvoice.spec
```

输出：

```bash
dist/JoyHarness.app
```

相关资源：

- `entitlements.plist`: macOS 签名 / 权限配置
- `assets/icons/`: 应用图标和菜单栏图标
- `tools/make_icons.py`: 批量生成 `.icns` 和菜单栏状态图标

## 项目结构

```text
src/
├── main.py              # CLI 入口、线程编排、菜单栏 / 托盘启动
├── joycon_reader.py     # 手柄扫描、轮询、重连、连接模式识别
├── key_mapper.py        # 核心映射引擎
├── config_loader.py     # 配置加载、合并、校验、保存
├── constants.py         # 按钮索引、默认配置、动作常量
├── keyboard_output.py   # 平台键盘输出
├── window_switcher.py   # 窗口切换
├── gui.py               # 主窗口
├── settings_window.py   # 设置窗口
├── macos_status_bar.py  # macOS 菜单栏集成
├── single_instance.py   # 单实例锁
├── battery_reader.py    # 电量读取
├── keep_alive.py        # 防休眠保活
└── tray_icon.py         # Windows 托盘
```

## 许可证

[MIT](LICENSE)
