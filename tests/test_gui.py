"""
GUI smoke test for AutoDeploy.
Instantiates QApplication and MainWindow in headless offscreen mode to ensure zero syntax/runtime crashes.
"""

import os
import sys
from pathlib import Path

# Headless Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow

def test_gui_smoke():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    assert window.windowTitle().startswith("AutoDeploy")
    assert window.table_projects is not None
    assert window.history_view is not None
    assert window.settings_view is not None

    # Test tab navigation
    window.tab_widget.setCurrentIndex(1)
    window.tab_widget.setCurrentIndex(2)
    window.tab_widget.setCurrentIndex(0)

    # Test project dialog creation
    from gui.project_dialog import ProjectEditDialog
    dlg = ProjectEditDialog(parent=window)
    assert dlg.txt_name is not None
    assert dlg.step_list is not None

    print("[PASS] PySide6 GUI instantiated and validated successfully in offscreen mode!")

if __name__ == "__main__":
    test_gui_smoke()
