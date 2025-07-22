# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Get project root directory - use current working directory
project_root = Path.cwd()
src_path = project_root / "src"

# Add source code path to sys.path
sys.path.insert(0, str(src_path))

# Collect hidden imports
hiddenimports = [
    # PyQt6 related
    'PyQt6.QtCore',
    'PyQt6.QtGui', 
    'PyQt6.QtWidgets',
    'PyQt6.sip',
    
    # WebView2 related imports
    'pythonnet',
    'clr',
    'pywebview',
    
    # AI related libraries
    'google.generativeai',
    'sklearn',
    'sklearn.feature_extraction',
    'sklearn.feature_extraction.text',
    'sklearn.metrics.pairwise',
    'faiss',
    'numpy',
    'tqdm',
    'jieba',
    'bm25s',  # 替换rank_bm25为bm25s
    'qdrant_client',
    'langchain_community',
    'langchain_text_splitters',
    
    # Other dependencies
    'pywin32',
    'win32gui',
    'win32con',
    'win32api',
    'pystray',
    'PIL',
    'PIL.Image',
    'requests',
    'beautifulsoup4',
    'markdown',
    'brotli',
    'python_dotenv',
    
    # Graphics compatibility module (for Windows 10 PyQt6 fixes)
    'src.game_wiki_tooltip.graphics_compatibility',
]

# Collect data files
datas = [
    # Asset files
    (str(src_path / "game_wiki_tooltip" / "assets"), "assets"),
    # Vector database files
    (str(src_path / "game_wiki_tooltip" / "ai" / "vectorstore"), "ai/vectorstore"),
    # Knowledge data
    ("data", "data"),
    # WebView2 SDK files
    ("src/game_wiki_tooltip/webview2/lib", "webview2/lib"),
]

# Collect binary files
binaries = []

# Add comprehensive Windows runtime libraries for PyQt6 compatibility
try:
    print("[INFO] Adding Windows runtime libraries for PyQt6 compatibility...")
    
    # Common Windows DLL locations
    system32 = Path(os.environ.get('SYSTEMROOT', 'C:\\Windows')) / 'System32'
    
    # Essential DLLs for PyQt6 (verified existence before adding)
    essential_dlls = [
        # Core Windows APIs
        'shcore.dll',      # Shell scaling APIs
        'dwmapi.dll',      # Desktop Window Manager
        'uxtheme.dll',     # Visual styles
        'comctl32.dll',    # Common controls
        'comdlg32.dll',    # Common dialogs
        'ole32.dll',       # OLE support
        'oleaut32.dll',    # OLE automation
        'shell32.dll',     # Shell API
        'advapi32.dll',    # Advanced Windows API
        'setupapi.dll',    # Setup API
        'winspool.drv',    # Print spooler
        
        # Graphics and multimedia
        'gdi32.dll',       # Graphics Device Interface
        'gdiplus.dll',     # GDI+
        'opengl32.dll',    # OpenGL
        'd3d11.dll',       # Direct3D 11
        'dxgi.dll',        # DirectX Graphics Infrastructure
        
        # Network and security
        'wininet.dll',     # Internet API
        'winhttp.dll',     # HTTP API
        'crypt32.dll',     # Cryptographic API
        'bcrypt.dll',      # Cryptography API
        
        # System services
        'ntdll.dll',       # NT Layer DLL
        'msvcrt.dll',      # C runtime
        
        # Input method support
        'imm32.dll',       # Input Method Manager
    ]
    
    # Add DLLs that exist
    added_dlls = []
    for dll_name in essential_dlls:
        dll_path = system32 / dll_name
        if dll_path.exists():
            binaries.append((str(dll_path), "."))
            added_dlls.append(dll_name)
    
    print(f"[SUCCESS] Added {len(added_dlls)} essential Windows DLLs")
    
    # Try to add Visual C++ Redistributable libraries
    # These are critical for PyQt6 on different Windows versions
    vcredist_locations = [
        # Common VC++ runtime locations
        system32,
        Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / 'Microsoft Visual Studio' / 'Shared',
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')) / 'Microsoft Visual Studio' / 'Shared',
    ]
    
    vcredist_dlls = [
        'msvcp140.dll',    # Visual C++ 2015-2022 runtime
        'vcruntime140.dll', # Visual C++ 2015-2022 runtime
        'vcruntime140_1.dll', # Visual C++ 2015-2022 runtime (x64)
        'concrt140.dll',   # Concurrency runtime
        'vcomp140.dll',    # OpenMP runtime
    ]
    
    vcredist_added = []
    for location in vcredist_locations:
        if not location.exists():
            continue
        for dll_name in vcredist_dlls:
            dll_path = location / dll_name
            if dll_path.exists() and dll_name not in vcredist_added:
                binaries.append((str(dll_path), "."))
                vcredist_added.append(dll_name)
                break
    
    if vcredist_added:
        print(f"[SUCCESS] Added VC++ runtime libraries: {vcredist_added}")
    else:
        print("[WARNING] No VC++ runtime libraries found - target system may need to install VC++ Redistributables")
    
    print(f"[INFO] Total DLLs added: {len(added_dlls) + len(vcredist_added)}")
    
except Exception as e:
    print(f"[ERROR] Error adding runtime libraries: {e}")
    print("[INFO] Continuing with default configuration...")

# Exclude modules - only exclude modules that are truly not needed
excludes = [
    'tkinter',  # GUI toolkit (we use PyQt6)
    'unittest',  # Testing framework
    'pydoc',    # Documentation generation tool
    'doctest',  # Documentation testing tool
    'test',     # Python test modules
    'tests',    # Application test modules
]

a = Analysis(
    [str(src_path / "game_wiki_tooltip" / "qt_app.py")],
    pathex=[str(project_root), str(src_path)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name='GameWikiAssistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False to hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(src_path / "game_wiki_tooltip" / "assets" / "app.ico"),
    version_file=None,
    manifest='GameWikiAssistant.manifest',  # Add manifest for DPI awareness and compatibility
) 