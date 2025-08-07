# Build Guide

This guide covers how to build GameWikiTooltip from source into a standalone Windows executable.

## 📋 Prerequisites

### Required Software
- **Python 3.8-3.11** (3.12+ may have compatibility issues)
- **Git** for version control
- **Visual C++ Build Tools** (for some Python packages)
- **Windows 10/11** development environment

### Python Dependencies
```bash
pip install -r requirements.txt
```

## 🔨 Build Process

### 1. Clone the Repository
```bash
git clone https://github.com/rimulu030/gamewiki.git
cd gamewiki
```

### 2. Set Up Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate  # Windows
```

### 3. Install Dependencies
```bash
# Upgrade pip
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt
```

### 4. Download Voice Models (Optional)
```bash
# For voice recognition support
python download_vosk_models.py
```

### 5. Build the Executable

#### Option A: Using Build Script (Recommended)
```bash
python build_exe.py
```

#### Option C: Manual PyInstaller Command
```bash
pyinstaller --name GameWikiAssistant \
            --windowed \
            --icon src/game_wiki_tooltip/assets/app.ico \
            --add-data "src/game_wiki_tooltip/assets;src/game_wiki_tooltip/assets" \
            --add-data "data;data" \
            --hidden-import PyQt6 \
            --hidden-import google.generativeai \
            src/game_wiki_tooltip/qt_app.py
```

### 6. Output Location
The built executable will be in:
```
GameWikiAssistant_Portable_onedir/
├── GameWikiAssistant/        # OneDir build (recommended)
│   ├── GameWikiAssistant.exe
│   ├── _internal/
│   └── data/
└── GameWikiAssistant.exe     # OneFile build (if configured)
```

## 📦 Creating a Portable Package

### 1. Prepare Directory Structure
```
GameWikiAssistant_Portable/
├── GameWikiAssistant.exe
├── _internal/              # From dist folder
├── data/                   # Knowledge bases
├── runtime/                # WebView2 installer
│   └── MicrosoftEdgeWebView2Setup.exe
└── README.txt
```

### 2. Create ZIP Package
```bash
# Using PowerShell
Compress-Archive -Path GameWikiAssistant_Portable/* -DestinationPath GameWikiAssistant_Portable.zip

# Using 7-Zip
7z a -tzip GameWikiAssistant_Portable.zip GameWikiAssistant_Portable/*
```

## 🎯 Build Optimizations

### Reduce File Size
1. **Use UPX Compression** (optional, may trigger antivirus):
   ```bash
   pip install pyinstaller[upx]
   # Add --upx-dir=path/to/upx in build command
   ```

2. **Exclude Unnecessary Modules**:
   Edit `game_wiki_tooltip.spec`:
   ```python
   excludes = ['tkinter', 'matplotlib', 'scipy']
   ```

3. **OneDIr vs OneFile**:
   - OneDir: Faster startup, easier debugging
   - OneFile: Single executable, slower extraction

### Improve Startup Speed
1. Use OneDir mode (default in spec file)
2. Lazy load heavy modules
3. Optimize imports in source code

## 🐛 Troubleshooting Build Issues

### Common Problems

#### 1. "Module not found" Errors
```python
# Add to spec file hiddenimports
hiddenimports = ['missing_module_name']
```

#### 2. DLL Loading Issues
```python
# Add to spec file binaries
binaries = [
    ('path/to/dll', '.'),
]
```

#### 3. Data Files Not Included
```python
# Add to spec file datas
datas = [
    ('src/game_wiki_tooltip/assets', 'src/game_wiki_tooltip/assets'),
]
```

#### 4. Antivirus False Positives
- Sign the executable with a code certificate
- Submit to antivirus vendors for whitelisting
- Avoid UPX compression
- Use OneDir instead of OneFile

#### 5. WebView2 Not Working
Ensure WebView2 loader is included:
```python
datas = [
    ('src/game_wiki_tooltip/webview2/lib', 'src/game_wiki_tooltip/webview2/lib'),
]
```

## 🔧 Advanced Configuration

### Custom Spec File Options

```python
# game_wiki_tooltip.spec

# Add version information
exe = EXE(
    ...
    version_file='version_info.txt',
    ...
)

# Custom manifest for Windows
manifest = '''
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo>
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>
'''
```

### Building for Different Architectures

#### 32-bit Build
```bash
# Use 32-bit Python installation
C:\Python38-32\python.exe -m PyInstaller game_wiki_tooltip.spec
```

#### ARM64 Build (Experimental)
```bash
# Requires ARM64 Windows and Python
pyinstaller --target-arch=arm64 game_wiki_tooltip.spec
```

## 🚀 CI/CD Build Automation

### GitHub Actions Workflow
See `.github/workflows/build-release.yml` for automated builds.

### Local Build Script
```python
# build_all.py
import subprocess
import shutil
import os

def build():
    # Clean previous builds
    shutil.rmtree('dist', ignore_errors=True)
    shutil.rmtree('build', ignore_errors=True)
    
    # Run PyInstaller
    subprocess.run(['pyinstaller', 'game_wiki_tooltip.spec'])
    
    # Create portable package
    os.makedirs('GameWikiAssistant_Portable', exist_ok=True)
    shutil.copytree('dist/GameWikiAssistant', 'GameWikiAssistant_Portable/GameWikiAssistant')
    
    # Create ZIP
    shutil.make_archive('GameWikiAssistant_Portable', 'zip', 'GameWikiAssistant_Portable')
    
    print("Build complete!")

if __name__ == '__main__':
    build()
```

## 📝 Build Checklist

Before releasing:

- [ ] Update version number in code
- [ ] Run all tests
- [ ] Build executable
- [ ] Test on clean Windows installation
- [ ] Scan with antivirus
- [ ] Generate checksums
- [ ] Create release notes
- [ ] Tag Git repository
- [ ] Upload to GitHub Releases

## 🆘 Getting Help

- **Build Issues**: [GitHub Issues](https://github.com/rimulu030/gamewiki/issues)
- **PyInstaller Docs**: [pyinstaller.org](https://pyinstaller.org)
- **Community Support**: [Discord](https://discord.gg/gamewiki)

---

For automated builds, see [GitHub Actions workflow](.github/workflows/build-release.yml).