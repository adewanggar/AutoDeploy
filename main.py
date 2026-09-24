"""
AutoDeploy - Unified Entry Point for Windows Server CI/CD.

Usage:
  python main.py           Launch PySide6 GUI interface
  python main.py --engine  Run headless background deploy engine
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

def main() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        print("Arguments:")
        print("  --engine     Run headless background deploy engine (webhook server & git poller)")
        print("  (no args)    Launch PySide6 configuration and monitoring GUI")
        sys.exit(0)

    if "--engine" in sys.argv:
        from core.engine import run_engine
        run_engine()
    else:
        from PySide6.QtWidgets import QApplication
        from gui.main_window import MainWindow

        # Enable High DPI scaling
        app = QApplication(sys.argv)
        app.setApplicationName("AutoDeploy")
        app.setOrganizationName("AutoDeploy")

        window = MainWindow()
        window.show()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()
