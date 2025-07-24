#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GameWiki Assistant Packaging Script

This script is used to package GameWiki Assistant into a standalone exe file.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def print_status(message):
    """Print status information"""
    print(f"🔧 {message}")

def print_error(message):
    """Print error information"""
    print(f"❌ Error: {message}")

def print_success(message):
    """Print success information"""
    print(f"✅ {message}")

def run_command(command, cwd=None):
    """Execute command and return result"""
    import locale
    
    # Get system default encoding
    system_encoding = locale.getpreferredencoding()
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding=system_encoding,
            errors='replace'  # Handle encoding errors with replacement characters
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        # Ensure error information can also be decoded correctly
        error_msg = e.stderr if e.stderr else str(e)
        return False, error_msg
    except UnicodeDecodeError as e:
        print_error(f"Encoding error, trying UTF-8: {e}")
        # If system encoding fails, try UTF-8
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                check=True, 
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e2:
            error_msg = e2.stderr if e2.stderr else str(e2)
            return False, error_msg

def install_dependencies():
    """Install/update dependencies"""
    print_status("Installing/updating dependencies...")
    
    success, output = run_command("pip install --upgrade pip")
    if not success:
        print_error(f"Updating pip failed: {output}")
        return False
    
    success, output = run_command("pip install -r requirements.txt")
    if not success:
        print_error(f"Installing dependencies failed: {output}")
        return False
    
    print_success("Dependencies installed")
    return True

def clean_build():
    """Clean build directory"""
    print_status("Cleaning previous build files...")
    
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"  Deleted: {dir_name}")
            except Exception as e:
                print(f"  Cannot delete {dir_name}: {e}")
                # Continue, do not stop the entire process
    
    # Delete spec generated cache files
    try:
        for file in Path('.').glob('*.spec~'):
            file.unlink()
            print(f"  Deleted: {file}")
    except Exception as e:
        print(f"  Error cleaning spec cache files: {e}")
    
    print_success("Build directory cleaned")
    return True  # Ensure return True

def check_assets():
    """Check if necessary resource files exist"""
    print_status("Checking resource files...")
    
    required_files = [
        "src/game_wiki_tooltip/assets/app.ico",
        "src/game_wiki_tooltip/assets/games.json",
        "src/game_wiki_tooltip/assets/settings.json",
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print_error("Missing necessary resource files:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print_success("Resource files checked")
    return True

def check_webview2_requirements():
    """Check WebView2 requirements"""
    print_status("Checking WebView2 requirements...")
    
    # Check pythonnet
    try:
        import clr
        print("  ✓ pythonnet installed")
    except ImportError:
        print_error("pythonnet not installed, please run: pip install pythonnet")
        return False
    
    # Check WebView2 SDK files
    webview2_lib_path = Path("src/game_wiki_tooltip/webview2/lib")
    required_dlls = [
        "Microsoft.Web.WebView2.Core.dll",
        "Microsoft.Web.WebView2.WinForms.dll", 
        "WebView2Loader.dll"
    ]
    
    missing_dlls = []
    for dll in required_dlls:
        if not (webview2_lib_path / dll).exists():
            missing_dlls.append(dll)
    
    if missing_dlls:
        print_error(f"Missing WebView2 SDK files: {', '.join(missing_dlls)}")
        print("Please run: python src/game_wiki_tooltip/webview2_setup.py")
        return False
    
    print("  ✓ WebView2 SDK files exist")
    
    # Check WebView2 Runtime (optional check, because it may be installed on the target machine)
    try:
        import winreg
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        version = winreg.QueryValueEx(key, "pv")[0]
        winreg.CloseKey(key)
        print(f"  ✓ WebView2 Runtime installed: {version}")
    except:
        print("  ⚠️  WebView2 Runtime not detected, but user may need to install it on the target machine")
    
    print_success("WebView2 requirements checked")
    return True

def update_spec_for_webview2():
    """Update spec file to support WebView2"""
    print_status("Updating PyInstaller configuration to support WebView2...")
    
    spec_file = "game_wiki_tooltip.spec"
    if not os.path.exists(spec_file):
        print_error(f"Spec file not found: {spec_file}")
        return False
    
    # Read current spec file
    with open(spec_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if WebView2 configuration is already included
    if "pythonnet" in content and "webview2" in content.lower():
        print("  ✓ spec file includes WebView2 configuration")
        return True
    
    # Add WebView2 related hiddenimports
    webview2_imports = """
    # WebView2 related imports
    'pythonnet',
    'clr',
    'System',
    'System.Windows.Forms',
    'System.Threading',
    'Microsoft.Web.WebView2.Core',
    'Microsoft.Web.WebView2.WinForms',"""
    
    # Replace PyQt6-WebEngine with WebView2
    updated_content = content.replace(
        "'PyQt6.QtWebEngineWidgets',\n    'PyQt6.QtWebEngineCore',",
        "'pywebview[edgechromium]'," + webview2_imports
    )
    
    # Add WebView2 DLL files to datas
    webview2_datas = '''
    # WebView2 SDK files
    ("src/game_wiki_tooltip/webview2/lib", "webview2/lib"),'''
    
    # Add after datas section
    if "# Knowledge data" in updated_content:
        updated_content = updated_content.replace(
            '("data", "data"),',
            '("data", "data"),' + webview2_datas
        )
    
    # Write back to file
    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print_success("spec file updated to support WebView2")
    return True

def build_exe():
    """Build exe file using PyInstaller"""
    print_status("Building exe file...")
    print("This may take a few minutes, please wait...")
    
    # Use spec file to build
    success, output = run_command("pyinstaller game_wiki_tooltip.spec --clean --noconfirm")
    
    if not success:
        print_error(f"Build failed: {output}")
        return False
    
    # Check generated exe file
    exe_path = Path("dist/GameWikiAssistant.exe")
    if exe_path.exists():
        print_success(f"Build successful! exe file location: {exe_path.absolute()}")
        print(f"File size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        return True
    else:
        print_error("Build completed but exe file not found")
        return False

def create_portable_package():
    """Create portable package"""
    print_status("Creating portable package...")
    
    dist_dir = Path("dist")
    if not dist_dir.exists():
        print_error("dist directory not found")
        return False
    
    # Create portable directory
    portable_dir = Path("GameWikiAssistant_Portable")
    if portable_dir.exists():
        shutil.rmtree(portable_dir)
    
    portable_dir.mkdir()
    
    # Copy exe file
    exe_file = dist_dir / "GameWikiAssistant.exe"
    if exe_file.exists():
        shutil.copy2(exe_file, portable_dir)
    
    # Copy necessary documents
    readme_content = """# GameWiki Assistant 便携版

## Instructions

1. **Read Before First Use**: This application uses WebView2 technology and requires Microsoft Edge WebView2 Runtime.
2. Double-click GameWikiAssistant.exe to start the program.
3. Opening this exe can take a few seconds (normally in 10 seconds).
4. If the program fails to start or displays a white screen, please install the WebView2 Runtime.
5. API keys need to be configured on first run (optional).
6. Use the shortcut Ctrl+X or set a new shortcut to activate the game assistant feature.

## System Requirements

- Windows 10 or higher (recommended Windows 11)
- 64-bit system (64-bit system is recommended)
- Microsoft Edge WebView2 Runtime

## WebView2 Runtime Installation

### Windows 11 Users
✅ Your system is pre-installed with WebView2 Runtime, you can use it directly.

### Windows 10 Users  
⚠️ Need to install WebView2 Runtime:

**Method 1 (recommended)**: Run the automatic installation script
1. Enter the runtime folder
2. Double-click to run install_webview2.bat
3. Follow the prompts to complete the installation

**Method 2**: Manually download and install
1. Visit: https://go.microsoft.com/fwlink/p/?LinkId=2124703
2. Download and install WebView2 Runtime
3. Restart the application

## Notes

- This program is a standalone portable version, no installation required (except for WebView2 Runtime)
- Configuration files will be saved in the system's AppData directory
- For full AI functionality, please configure Gemini and Jina API keys
- The first installation of WebView2 Runtime requires downloading about 100MB, but only needs to be installed once

## Troubleshooting

### Problem: The program fails to start or displays a white screen
**Solution**: Install WebView2 Runtime (see installation instructions above)

### Problem: Video playback fails
**Solution**: Confirm that WebView2 Runtime is correctly installed and restart the program

### Problem: Temporary files accumulation
**Note**: When the program exits abnormally or crashes, temporary files may remain in the system temp directory:
- Location: %TEMP%\\_MEI****** (such as: AppData\\Local\\Temp\\_MEI260882\\)
- These folders are safe to delete and won't affect system operation
- PyInstaller automatically cleans up these folders on normal program exit
- You can manually delete these folders periodically to free up disk space

## Support

If you have any problems, please visit the project page for help.
"""
    
    with open(portable_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print_success(f"Portable package created: {portable_dir.absolute()}")
    return True

def create_webview2_runtime_installer():
    """Create WebView2 Runtime installer"""
    print_status("Creating WebView2 Runtime installer...")
    
    portable_dir = Path("GameWikiAssistant_Portable")
    if not portable_dir.exists():
        print_error("Portable directory not found")
        return False
    
    # Create runtime directory
    runtime_dir = portable_dir / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    
    # Download WebView2 Runtime Bootstrapper
    try:
        import urllib.request
        bootstrapper_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
        bootstrapper_path = runtime_dir / "MicrosoftEdgeWebView2Setup.exe"
        
        print("  Downloading WebView2 Runtime Bootstrapper...")
        urllib.request.urlretrieve(bootstrapper_url, bootstrapper_path)
        print(f"  ✓ Downloaded to: {bootstrapper_path}")
        
        # Create installation script
        install_script = runtime_dir / "install_webview2.bat"
        script_content = """@echo off
echo Checking WebView2 Runtime...
reg query "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" >nul 2>&1
if %errorlevel% equ 0 (
    echo WebView2 Runtime is already installed, no need to install.
    pause
    exit /b 0
)

echo WebView2 Runtime is not installed, installing...
echo This may take a few minutes, please wait...
MicrosoftEdgeWebView2Setup.exe /silent /install
if %errorlevel% equ 0 (
    echo WebView2 Runtime installation completed!
) else (
    echo Installation failed, please manually run MicrosoftEdgeWebView2Setup.exe
)
pause
"""
        with open(install_script, 'w', encoding='gbk') as f:
            f.write(script_content)
        
        print_success("WebView2 Runtime installer created")
        return True
        
    except Exception as e:
        print_error(f"Failed to create WebView2 Runtime installer: {e}")
        return False

def main():
    """Main function"""
    # Set console encoding to ensure Chinese characters are displayed correctly
    if sys.platform == "win32":
        import locale
        try:
            # Try to set console encoding to UTF-8
            os.system("chcp 65001 >nul 2>&1")
        except:
            pass
    
    print("🚀 GameWiki Assistant Packaging Tool")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print_error("Python 3.8 or higher is required")
        return 1
    
    # Check if in project root directory
    if not os.path.exists("src/game_wiki_tooltip/qt_app.py"):
        print_error("Please run this script in the project root directory")
        return 1
    
    try:
        # Execute build steps
        steps = [
            ("Install dependencies", install_dependencies),
            ("Clean build", clean_build),
            ("Check resources", check_assets),
            ("Check WebView2 requirements", check_webview2_requirements),
            ("Update spec file", update_spec_for_webview2),
            ("Build exe", build_exe),
            ("Create portable package", create_portable_package),
            ("Create WebView2 Runtime installer", create_webview2_runtime_installer),
        ]
        
        for step_name, step_func in steps:
            print(f"\n📋 Step: {step_name}")
            if not step_func():
                print_error(f"Step '{step_name}' failed")
                return 1
        
        print("\n" + "=" * 50)
        print_success("🎉 Packaging completed!")
        print("\n📦 Generated files:")
        print("  - dist/GameWikiAssistant.exe (standalone exe file)")
        print("  - GameWikiAssistant_Portable/ (portable directory)")
        print("\n💡 Tips:")
        print("  - You can compress the portable directory and distribute it to other users")
        print("  - If program crashes, temporary files may remain in %TEMP%\\\\_MEI****** folders")
        print("  - These temporary folders can be safely deleted to free up disk space")
        
        return 0
        
    except KeyboardInterrupt:
        print_error("User interrupted the build process")
        return 1
    except Exception as e:
        print_error(f"Unexpected error occurred during build: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code) 