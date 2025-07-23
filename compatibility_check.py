#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GameWiki Assistant Compatibility Check Tool
===========================================

Used to diagnose compatibility issues on Win10/Win11 systems, especially dependencies related to PyQt6.
"""

import sys
import os
import subprocess
from pathlib import Path
import platform

def print_header(title):
    """Print title"""
    print(f"\n{'=' * 50}")
    print(f"🔍 {title}")
    print(f"{'=' * 50}")

def print_check(name, result, details=""):
    """Print check result"""
    status = "✅" if result else "❌"
    print(f"{status} {name}")
    if details:
        print(f"   {details}")

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    is_compatible = version >= (3, 8)
    details = f"Current version: {version.major}.{version.minor}.{version.micro}"
    if not is_compatible:
        details += " (Python 3.8+ is required)"
    return is_compatible, details

def check_windows_version():
    """Check Windows version"""
    try:
        version = sys.getwindowsversion()
        is_win10_plus = version.major >= 10
        details = f"Windows {version.major}.{version.minor} Build {version.build}"
        
        if not is_win10_plus:
            details += " (Windows 10+ is required)"
        elif version.build < 17763:  # Windows 10 1809
            details += " (It is recommended to update to 1809 or higher)"
            
        return is_win10_plus, details
    except:
        return False, "Failed to detect Windows version"

def check_architecture():
    """Check system architecture"""
    arch = platform.machine().lower()
    is_x64 = arch in ['amd64', 'x86_64']
    details = f"System architecture: {arch}"
    if not is_x64:
        details += " (64-bit system is required)"
    return is_x64, details

def check_vcredist():
    """Check VC++ Redistributables"""
    system32 = Path(os.environ.get('SYSTEMROOT', 'C:\\Windows')) / 'System32'
    
    required_dlls = {
        'msvcp140.dll': 'Visual C++ 2015-2022 runtime',
        'vcruntime140.dll': 'Visual C++ 2015-2022 runtime',
        'vcruntime140_1.dll': 'Visual C++ 2015-2022 runtime (x64)',
    }
    
    missing = []
    found = []
    
    for dll, desc in required_dlls.items():
        dll_path = system32 / dll
        if dll_path.exists():
            try:
                # Try to get file version information
                size = dll_path.stat().st_size
                found.append(f"{dll} ({size} bytes)")
            except:
                found.append(dll)
        else:
            missing.append(f"{dll} ({desc})")
    
    is_complete = len(missing) == 0
    
    if is_complete:
        details = f"Installed: {', '.join(found)}"
    else:
        details = f"Missing: {', '.join(missing)}"
        if found:
            details += f"; Installed: {', '.join(found)}"
    
    return is_complete, details

def check_pyqt6_dependencies():
    """Check PyQt6 related system dependencies"""
    system32 = Path(os.environ.get('SYSTEMROOT', 'C:\\Windows')) / 'System32'
    
    # Common system DLLs for PyQt6
    pyqt_dlls = {
        'shcore.dll': 'Shell Core (DPI支持)',
        'dwmapi.dll': 'Desktop Window Manager',
        'uxtheme.dll': 'Visual Styles',
        'comctl32.dll': 'Common Controls',
        'gdi32.dll': 'Graphics Device Interface',
        'user32.dll': 'User Interface',
        'opengl32.dll': 'OpenGL',
    }
    
    missing = []
    found = []
    
    for dll, desc in pyqt_dlls.items():
        dll_path = system32 / dll
        if dll_path.exists():
            found.append(dll)
        else:
            missing.append(f"{dll} ({desc})")
    
    is_complete = len(missing) == 0
    
    if is_complete:
        details = f"System DLLs complete ({len(found)}/{len(pyqt_dlls)})"
    else:
        details = f"Missing system DLLs: {', '.join(missing)}"
    
    return is_complete, details

def check_installed_vcredist_packages():
    """Check installed VC++ Redistributable packages"""
    try:
        # Use wmic to query installed VC++ packages
        cmd = ['wmic', 'product', 'where', "name like '%Visual C++%'", 'get', 'name,version', '/format:csv']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            packages = []
            for line in lines[1:]:  # Skip header line
                if line.strip() and ',' in line:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        name = parts[1].strip()
                        version = parts[2].strip()
                        if name and version:
                            packages.append(f"{name} v{version}")
            
            if packages:
                return True, f"Installed: {'; '.join(packages)}"
            else:
                return False, "No installed VC++ Redistributable packages found"
        else:
            return False, "Failed to query installed VC++ packages"
    except:
        return False, "Error querying VC++ packages"

def check_pyinstaller_environment():
    """Check PyInstaller packaging environment"""
    checks = []
    
    # Check if in PyInstaller environment
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        checks.append("✅ Running in PyInstaller packaging environment")
        checks.append(f"   Temporary directory: {sys._MEIPASS}")
        
        # Check if key DLLs exist
        temp_dir = Path(sys._MEIPASS)
        key_dlls = ['msvcp140.dll', 'vcruntime140.dll', 'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll']
        
        found_dlls = []
        missing_dlls = []
        
        for dll in key_dlls:
            if (temp_dir / dll).exists():
                found_dlls.append(dll)
            else:
                missing_dlls.append(dll)
        
        if found_dlls:
            checks.append(f"   Packaged DLLs: {', '.join(found_dlls)}")
        if missing_dlls:
            checks.append(f"   Missing DLLs: {', '.join(missing_dlls)}")
            
        return len(missing_dlls) == 0, '\n'.join(checks)
    else:
        return True, "Running in development environment (non-packaged version)"

def run_comprehensive_check():
    """Run comprehensive compatibility check"""
    print_header("GameWiki Assistant compatibility check")
    print("This tool will check if the system meets the running requirements")
    
    # Basic system check
    print_header("Basic system check")
    
    checks = [
        ("Python version", check_python_version),
        ("Windows version", check_windows_version),
        ("System architecture", check_architecture),
    ]
    
    basic_passed = 0
    for name, check_func in checks:
        try:
            result, details = check_func()
            print_check(name, result, details)
            if result:
                basic_passed += 1
        except Exception as e:
            print_check(name, False, f"Check failed: {e}")
    
    # Runtime dependency check
    print_header("Runtime dependency check")
    
    runtime_checks = [
        ("Visual C++ Runtime DLL", check_vcredist),
        ("PyQt6 system dependencies", check_pyqt6_dependencies),
        ("Installed VC++ packages", check_installed_vcredist_packages),
    ]
    
    runtime_passed = 0
    for name, check_func in runtime_checks:
        try:
            result, details = check_func()
            print_check(name, result, details)
            if result:
                runtime_passed += 1
        except Exception as e:
            print_check(name, False, f"Check failed: {e}")
    
    # Packaging environment check
    print_header("Application environment check")
    
    try:
        result, details = check_pyinstaller_environment()
        print_check("PyInstaller environment", result, details)
    except Exception as e:
        print_check("PyInstaller environment", False, f"Check failed: {e}")
    
    # Summary
    print_header("Check summary")
    
    total_basic = len(checks)
    total_runtime = len(runtime_checks)
    
    print(f"Basic system check: {basic_passed}/{total_basic} passed")
    print(f"Runtime dependency check: {runtime_passed}/{total_runtime} passed")
    
    if basic_passed == total_basic and runtime_passed == total_runtime:
        print("\n🎉 All system compatibility checks passed!")
        print("The application should be able to run normally.")
    else:
        print("\n⚠️  Compatibility issues found, recommended solutions:")
        
        if basic_passed < total_basic:
            print("\n📋 Basic system issues:")
            print("  - Upgrade to Windows 10 1809 or higher")
            print("  - Ensure 64-bit system")
            print("  - Upgrade Python to 3.8 or higher")
        
        if runtime_passed < total_runtime:
            print("\n📋 Runtime dependency issues:")
            print("  - Download and install: https://aka.ms/vs/17/release/vc_redist.x64.exe")
            print("  - Run deploy_with_vcredist.py to create a compatibility deployment package")
            print("  - Re-package using improved PyInstaller configuration")
    
    return basic_passed == total_basic and runtime_passed == total_runtime

def main():
    """Main function"""
    try:
        success = run_comprehensive_check()
        
        print_header("Recommended actions")
        if success:
            print("✅ No additional actions are required, system compatibility is good")
        else:
            print("📝 Recommended to solve the problem in the following order:")
            print("  1. Run the compatibility deployment script: python deploy_with_vcredist.py")
            print("  2. Or re-package the application: pyinstaller game_wiki_tooltip.spec --clean")
            print("  3. Or manually install VC++ Redistributable")
            print("  4. View detailed guide: deploy_instructions.md")
        
        print(f"\nCheck completed - exit code: {0 if success else 1}")
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nUser interrupted the check process")
        return 1
    except Exception as e:
        print(f"\nError occurred during check: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code) 