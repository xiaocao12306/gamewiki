# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for GameWikiTooltip Uninstaller
"""

a = Analysis(
    ['uninstaller.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include the app icon for the uninstaller
        ('src/game_wiki_tooltip/assets/app.ico', '.')
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GameWikiUninstaller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI application, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src\\game_wiki_tooltip\\assets\\app.ico',
    uac_admin=True,  # Request admin privileges
    uac_uiaccess=False,
)