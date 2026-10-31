"""
GUI Entry point forwarder for Chaos Zero Nightmare Bot.
Delegates to apps.gui.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
APPS_DIR = os.path.join(BASE_DIR, "apps")

for path in (SRC_DIR, BASE_DIR, APPS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from apps.gui import main, BotGUI

if __name__ == "__main__":
    main()
