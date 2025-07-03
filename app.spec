# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\game_wiki_tooltip\\app.py'],
    pathex=[],
    binaries=[],
    datas=[('src/game_wiki_tooltip/assets', 'game_wiki_tooltip/assets')],
    hiddenimports=['game_wiki_tooltip.assets'],
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
    a.binaries,
    a.datas,
    [],
    name='app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src\\game_wiki_tooltip\\assets\\app.ico'],
)
