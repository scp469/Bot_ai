"""
Main entry point wrapper for Chaos Zero Nightmare Bot.
Delegates to apps.cli or apps.gui based on CLI arguments.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
APPS_DIR = os.path.join(BASE_DIR, "apps")

for path in (SRC_DIR, BASE_DIR, APPS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)


def main():
    if "--cli" in sys.argv or "--simulate" in sys.argv:
        from apps.cli import main as run_cli_app
        run_cli_app()
    else:
        from apps.gui import main as run_gui_app
        run_gui_app()


if __name__ == "__main__":
    main()
