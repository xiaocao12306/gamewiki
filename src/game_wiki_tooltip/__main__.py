"""
Direct entry point for running as module: python -m game_wiki_tooltip
This ensures splash screen appears immediately.
"""

import sys
import os

# Minimal check
if sys.platform != "win32":
    print("This tool only works on Windows.")
    sys.exit(1)

from .qt_app import main

if __name__ == '__main__':
    main()