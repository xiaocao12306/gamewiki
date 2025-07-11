"""
Example of integrating the new UI system into the main application.
This shows how to replace the old overlay system with the new unified UI.
"""

import sys
import asyncio
import pathlib
import tkinter as tk
from tkinter import messagebox
import time
import win32gui
import win32con
import logging
import queue

# Import from src
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from src.game_wiki_tooltip.config import SettingsManager, GameConfigManager
from src.game_wiki_tooltip.hotkey import HotkeyManager
from src.game_wiki_tooltip.tray_icon import TrayIcon
from src.game_wiki_tooltip.utils import run_tk_event_loop, APPDATA_DIR, get_foreground_title, _tk_call_queue
from src.game_wiki_tooltip.hotkey_setup import configure_hotkey
from src.game_wiki_tooltip.assistant_integration import IntegratedAssistantController

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s - %(levelname)s - %(message)s')

SETTINGS_PATH = APPDATA_DIR / "settings.json"
GAMES_CONFIG_PATH = APPDATA_DIR / "games.json"


def main():
    """Main entry point with new UI system"""
    if tk._default_root is None:
        root = tk.Tk()
        root.withdraw()

    settings_mgr = SettingsManager(SETTINGS_PATH)
    game_cfg_mgr = GameConfigManager(GAMES_CONFIG_PATH)

    # Initialize the new assistant controller instead of overlay manager
    assistant_ctrl = IntegratedAssistantController(settings_mgr)
    
    # Tray icon now uses the assistant controller
    tray = TrayIcon(settings_mgr, assistant_ctrl)
    
    # Hotkey manager triggers the assistant
    hk_mgr = HotkeyManager(
        settings_mgr, 
        on_trigger=lambda: assistant_ctrl.expand_to_chat()
    )

    # First-time setup: configure hotkey
    def after_apply():
        try:
            # Re-register hotkey
            hk_mgr.register()
            # Show tray icon
            tray.show_trayicon()
            
            # Show mini assistant
            assistant_ctrl.show_mini()
            
            # Show notification
            tray.show_notification(
                "GameWiki Assistant", 
                f"Press {hk_mgr.get_hotkey_string()} to open assistant"
            )
        except Exception as e:
            logging.error(f"Failed to register hotkey: {e}")
            messagebox.showerror(
                "Error",
                f"Failed to register hotkey: {e}\n\n"
                "Please check if the hotkey is already in use by another application."
            )
            sys.exit(1)

    def on_close():
        # User closed settings without saving
        sys.exit(0)

    # Show settings window
    configure_hotkey(settings_mgr, on_close=on_close, on_apply=after_apply)

    # Event loop
    async def main_loop():
        """Main event loop combining Windows messages, Tkinter, and asyncio"""
        loop = asyncio.get_event_loop()
        
        def check_messages():
            # Process Windows messages
            try:
                msg = win32gui.PeekMessage(None, 0, 0, win32con.PM_REMOVE)
                if msg[0]:
                    win32gui.TranslateMessage(msg[1])
                    win32gui.DispatchMessage(msg[1])
            except Exception as e:
                logging.error(f"Error processing Windows message: {e}")
            
            # Schedule next check
            loop.call_later(0.01, check_messages)
        
        # Start message checking
        check_messages()
        
        # Process Tkinter events
        while True:
            try:
                # Process queued Tkinter calls
                while not _tk_call_queue.empty():
                    try:
                        func, args, kwargs = _tk_call_queue.get_nowait()
                        func(*args, **kwargs)
                    except queue.Empty:
                        break
                    except Exception as e:
                        logging.error(f"Error in Tkinter call: {e}")
                
                # Update Tkinter
                if tk._default_root:
                    tk._default_root.update()
                
                # Yield control
                await asyncio.sleep(0.01)
                
            except tk.TclError:
                # Tkinter has been destroyed
                break
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                await asyncio.sleep(0.1)

    # Run the async event loop
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("Application interrupted by user")
    finally:
        # Cleanup
        try:
            hk_mgr.unregister()
            tray.destroy()
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    main()