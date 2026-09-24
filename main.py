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
        try:
            from PySide6.QtWidgets import QApplication
            from gui.main_window import MainWindow
        except ImportError:
            print("\n" + "=" * 65)
            print("[AutoDeploy] PySide6 belum terpasang di sistem Python VPS ini.")
            print("=" * 65)
            print("PILIHAN CARA MENJALANKAN:")
            print("")
            print("1. Jika ingin membuka GUI pengaturan (lewat RDP):")
            print("   Jalankan perintah ini terlebih dahulu:")
            print("     pip install PySide6")
            print("     atau")
            print("     pip install -r requirements.txt")
            print("   Lalu jalankan:")
            print("     python main.py")
            print("")
            print("2. Jika ingin menjalankan Engine background saja (tanpa GUI):")
            print("   Engine 100% menggunakan Python standard library (tanpa perlu install apa pun):")
            print("     python main.py --engine")
            print("=" * 65 + "\n")
            sys.exit(1)

        app = QApplication(sys.argv)
        app.setApplicationName("AutoDeploy")
        app.setOrganizationName("AutoDeploy")

        window = MainWindow()
        window.show()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()
