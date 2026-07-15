# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['pyinstaller_entry.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('assets', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='joyvoice',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity='JoyVoice Self',
    entitlements_file='entitlements.plist',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='joyvoice',
)
app = BUNDLE(
    coll,
    name='JoyHarness.app',
    icon='assets/icons/AppIcon.icns',
    bundle_identifier='com.hongfushi.joyvoice',
    info_plist={
        'CFBundleName': 'JoyHarness',
        'CFBundleDisplayName': 'JoyHarness',
        'CFBundleShortVersionString': '1.2.0',
        'CFBundleVersion': '1.2.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        # Run as a menu-bar accessory: no Dock icon, no app menu in the
        # menu bar. The Tk window is opened on demand from our NSStatusItem.
        'LSUIElement': True,
    },
)
