"""
GameWikiTooltip Uninstaller
Removes all application files and user data
"""

import os
import sys
import shutil
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import ctypes

def is_admin():
    """Check if the script is running with administrator privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with administrator privileges"""
    if is_admin():
        return True
    else:
        # Re-run the program with admin rights
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        return False

class GameWikiUninstaller:
    def __init__(self):
        self.app_name = "GuidorTooltip"
        self.display_name = "Guidor Assistant"
        self.appdata_dir = Path.home() / "AppData" / "Roaming" / self.app_name
        self.install_dir = None
        self.is_portable = False
        self.removed_items = []
        self.failed_items = []
        
    def detect_install_directory(self):
        """Try to detect the installation directory"""
        # First, check if we're running from the installation directory
        current_dir = Path(sys.executable).parent
        
        # For portable version - check if GuidorAssistant folder exists in parent directory
        if (current_dir / "GuidorAssistant").exists() and (current_dir / "GuidorAssistant" / "GuidorAssistant.exe").exists():
            # Portable onedir version
            self.install_dir = current_dir / "GuidorAssistant"
            self.is_portable = True
            return True
        elif (current_dir / "GuidorAssistant.exe").exists():
            # Same directory as uninstaller (onefile or installed version)
            self.install_dir = current_dir
            self.is_portable = True
            return True
            
        # Check common installation locations (for Inno Setup installed version)
        common_paths = [
            Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / "Guidor Assistant",
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')) / "Guidor Assistant",
            Path(os.environ.get('LOCALAPPDATA', '')) / "Programs" / "Guidor Assistant",
        ]
        
        for path in common_paths:
            if path.exists() and (path / "GuidorAssistant.exe").exists():
                self.install_dir = path
                self.is_portable = False
                return True
                
        return False
    
    def remove_directory(self, path: Path, description: str):
        """Remove a directory and its contents"""
        if not path.exists():
            return True
            
        try:
            shutil.rmtree(path, ignore_errors=False)
            self.removed_items.append(f"✓ {description}: {path}")
            return True
        except PermissionError:
            self.failed_items.append(f"✗ {description}: {path} (Permission denied)")
            return False
        except Exception as e:
            self.failed_items.append(f"✗ {description}: {path} ({str(e)})")
            return False
    
    def remove_file(self, path: Path, description: str):
        """Remove a single file"""
        if not path.exists():
            return True
            
        try:
            path.unlink()
            self.removed_items.append(f"✓ {description}: {path}")
            return True
        except Exception as e:
            self.failed_items.append(f"✗ {description}: {path} ({str(e)})")
            return False
    
    def remove_shortcuts(self):
        """Remove desktop and start menu shortcuts"""
        shortcuts_removed = []
        
        # Desktop shortcut
        desktop = Path.home() / "Desktop" / f"{self.display_name}.lnk"
        if desktop.exists():
            if self.remove_file(desktop, "Desktop shortcut"):
                shortcuts_removed.append("Desktop")
        
        # Start Menu shortcuts
        start_menu_paths = [
            Path(os.environ.get('APPDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / self.display_name,
            Path(os.environ.get('PROGRAMDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / self.display_name,
        ]
        
        for start_menu in start_menu_paths:
            if start_menu.exists():
                if self.remove_directory(start_menu, "Start Menu folder"):
                    shortcuts_removed.append("Start Menu")
        
        # Quick Launch shortcut
        quick_launch = Path(os.environ.get('APPDATA', '')) / "Microsoft" / "Internet Explorer" / "Quick Launch" / f"{self.display_name}.lnk"
        if quick_launch.exists():
            if self.remove_file(quick_launch, "Quick Launch shortcut"):
                shortcuts_removed.append("Quick Launch")
                
        return shortcuts_removed
    
    def remove_registry_entries(self):
        """Remove registry entries (for installed version)"""
        try:
            # Remove uninstall entry
            uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8F7A9E2C-4B3D-4E6A-9C1F-2A3B4C5D6E7F}_is1"
            
            try:
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, uninstall_key)
                self.removed_items.append(f"✓ Registry uninstall entry")
            except:
                # Try HKEY_CURRENT_USER if HKLM fails
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, uninstall_key)
                    self.removed_items.append(f"✓ Registry uninstall entry (user)")
                except:
                    pass
                    
        except Exception as e:
            # Registry entries might not exist for portable version
            pass
    
    def remove_temp_files(self):
        """Remove temporary files created by PyInstaller"""
        temp_dir = Path(os.environ.get('TEMP', ''))
        removed_count = 0
        
        # Remove _MEI* directories (PyInstaller temp)
        for item in temp_dir.glob("_MEI*"):
            if item.is_dir():
                try:
                    shutil.rmtree(item, ignore_errors=True)
                    removed_count += 1
                except:
                    pass
                    
        if removed_count > 0:
            self.removed_items.append(f"✓ Temporary files: {removed_count} PyInstaller temp folders")
            
        return removed_count > 0
    
    def uninstall(self, remove_install_dir=True):
        """Perform the uninstallation"""
        success = True
        
        # 1. Remove AppData folder
        if self.appdata_dir.exists():
            self.remove_directory(self.appdata_dir, "User data folder")
        
        # 2. Remove shortcuts
        self.remove_shortcuts()
        
        # 3. Remove registry entries (only for installed version)
        if not self.is_portable:
            self.remove_registry_entries()
        
        # 4. Remove temporary files
        self.remove_temp_files()
        
        # 5. Remove installation directory (if specified and detected)
        if remove_install_dir and self.install_dir:
            # For portable version, check if we're in the parent directory
            uninstaller_parent = Path(sys.executable).parent
            
            # Check if we need to clean up the entire portable directory
            if self.is_portable and uninstaller_parent.name.startswith("GuidorAssistant_Portable"):
                # We're in the portable directory, need to clean the whole thing
                self.removed_items.append(f"⚠ Portable folder will be removed after restart: {uninstaller_parent}")
                self.create_cleanup_batch(uninstaller_parent)
            elif Path(sys.executable).parent == self.install_dir:
                # We can't remove the directory we're running from
                self.removed_items.append(f"⚠ Installation folder will be removed after restart: {self.install_dir}")
                self.create_cleanup_batch(self.install_dir)
            else:
                self.remove_directory(self.install_dir, "Installation folder")
        
        return len(self.failed_items) == 0
    
    def create_cleanup_batch(self, target_dir=None):
        """Create a batch file to delete the installation folder after uninstaller exits"""
        if not target_dir:
            target_dir = self.install_dir
        if not target_dir:
            return
            
        batch_content = f"""@echo off
echo Waiting for uninstaller to close...
timeout /t 3 /nobreak > nul
echo Removing installation folder...
rmdir /s /q "{target_dir}"
echo Cleanup complete.
del "%~f0"
"""
        
        batch_file = Path(os.environ.get('TEMP', '')) / "guidor_cleanup.bat"
        try:
            batch_file.write_text(batch_content)
            # Start the batch file
            os.startfile(str(batch_file))
        except:
            pass

class UninstallerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Guidor Assistant Uninstaller")
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        
        # Set window icon if available
        try:
            if getattr(sys, 'frozen', False):
                # Running as compiled exe
                icon_path = Path(sys._MEIPASS) / "app.ico"
            else:
                # Running as script
                icon_path = Path(__file__).parent / "src" / "game_wiki_tooltip" / "assets" / "app.ico"
            
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass
        
        self.uninstaller = GameWikiUninstaller()
        self.create_widgets()
        
    def create_widgets(self):
        # Title
        title_frame = tk.Frame(self.root, bg="#2196F3", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="Guidor Assistant Uninstaller",
            font=("Arial", 16, "bold"),
            bg="#2196F3",
            fg="white"
        )
        title_label.pack(pady=15)
        
        # Info frame
        info_frame = tk.Frame(self.root, padx=20, pady=20)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        info_text = (
            "This will remove Guidor Assistant from your computer.\n\n"
            "The following will be deleted:\n"
            "• Application files\n"
            "• User settings and data\n"
            "• Desktop and Start Menu shortcuts\n"
            "• Temporary files\n"
        )
        
        info_label = tk.Label(info_frame, text=info_text, justify=tk.LEFT, font=("Arial", 10))
        info_label.pack(anchor=tk.W)
        
        # Options
        self.remove_userdata_var = tk.BooleanVar(value=True)
        userdata_check = tk.Checkbutton(
            info_frame,
            text="Remove user settings and data",
            variable=self.remove_userdata_var,
            font=("Arial", 10)
        )
        userdata_check.pack(anchor=tk.W, pady=(20, 5))
        
        # Detected installation
        if self.uninstaller.detect_install_directory():
            install_type = "Portable" if self.uninstaller.is_portable else "Installed"
            detected_label = tk.Label(
                info_frame,
                text=f"Installation found ({install_type}): {self.uninstaller.install_dir}",
                font=("Arial", 9),
                fg="green"
            )
            detected_label.pack(anchor=tk.W, pady=(10, 0))
        
        # Buttons
        button_frame = tk.Frame(self.root, padx=20, pady=20)
        button_frame.pack(fill=tk.X)
        
        uninstall_btn = tk.Button(
            button_frame,
            text="Uninstall",
            command=self.perform_uninstall,
            bg="#f44336",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        )
        uninstall_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        cancel_btn = tk.Button(
            button_frame,
            text="Cancel",
            command=self.root.quit,
            font=("Arial", 10),
            padx=20,
            pady=5
        )
        cancel_btn.pack(side=tk.RIGHT)
        
    def perform_uninstall(self):
        # Confirm
        if not messagebox.askyesno(
            "Confirm Uninstall",
            "Are you sure you want to uninstall Guidor Assistant?\n\nThis action cannot be undone.",
            icon='warning'
        ):
            return
        
        # Perform uninstallation
        success = self.uninstaller.uninstall(remove_install_dir=True)
        
        # Show results
        result_window = tk.Toplevel(self.root)
        result_window.title("Uninstall Complete")
        result_window.geometry("500x400")
        result_window.resizable(False, False)
        
        # Title
        title_frame = tk.Frame(result_window, bg="#4CAF50" if success else "#f44336", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="Uninstall Complete" if success else "Uninstall Completed with Errors",
            font=("Arial", 16, "bold"),
            bg="#4CAF50" if success else "#f44336",
            fg="white"
        )
        title_label.pack(pady=15)
        
        # Results
        results_frame = tk.Frame(result_window, padx=20, pady=20)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create text widget with scrollbar
        text_frame = tk.Frame(results_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        results_text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9),
            height=15
        )
        results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=results_text.yview)
        
        # Add results
        results_text.insert(tk.END, "Removed items:\n")
        results_text.insert(tk.END, "-" * 50 + "\n")
        for item in self.uninstaller.removed_items:
            results_text.insert(tk.END, item + "\n")
        
        if self.uninstaller.failed_items:
            results_text.insert(tk.END, "\nFailed items:\n")
            results_text.insert(tk.END, "-" * 50 + "\n")
            for item in self.uninstaller.failed_items:
                results_text.insert(tk.END, item + "\n")
        
        results_text.config(state=tk.DISABLED)
        
        # Close button
        close_btn = tk.Button(
            result_window,
            text="Close",
            command=self.root.quit,
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        )
        close_btn.pack(pady=10)
        
        # Hide main window
        self.root.withdraw()
        
    def run(self):
        self.root.mainloop()

def main():
    # Check for admin rights (optional, but recommended for complete removal)
    if not is_admin():
        response = messagebox.askyesno(
            "Administrator Rights",
            "Running without administrator rights may prevent complete removal.\n\n"
            "Do you want to restart with administrator rights?",
            icon='warning'
        )
        if response:
            if not run_as_admin():
                sys.exit(0)
    
    # Run GUI
    app = UninstallerGUI()
    app.run()

if __name__ == "__main__":
    main()