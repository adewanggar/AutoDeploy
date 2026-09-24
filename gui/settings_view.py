"""
Global settings panel for AutoDeploy.
Configures webhook server bind/port, Telegram bot notifications,
and provides Windows Task Scheduler installation instructions for RDP persistence.
"""

import os
import subprocess
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import load_config, save_config
from core.paths import DATA_DIR
from core.service_ctl import get_task_scheduler_cmd
from gui.workers import TelegramTestWorker

class SettingsView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()
        self.load_settings()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 1. HTTP Server Settings
        grp_server = QGroupBox("HTTP Webhook Server Settings")
        form_server = QFormLayout(grp_server)
        form_server.setSpacing(10)

        self.cmb_host = QComboBox()
        self.cmb_host.addItem("0.0.0.0 (All network interfaces / Public VPS)", "0.0.0.0")
        self.cmb_host.addItem("127.0.0.1 (Localhost only / Tunneling / Reverse Proxy)", "127.0.0.1")

        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(9876)

        lbl_port_hint = QLabel("Note: Changing the HTTP port requires an Engine restart to bind to the new socket.")
        lbl_port_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")

        form_server.addRow("Bind Interface:", self.cmb_host)
        form_server.addRow("Webhook Port:", self.spin_port)
        form_server.addRow("", lbl_port_hint)
        layout.addWidget(grp_server)

        # 2. Telegram Notifications
        grp_tg = QGroupBox("Telegram Deployment Notifications (Optional)")
        form_tg = QFormLayout(grp_tg)
        form_tg.setSpacing(10)

        self.chk_tg_enabled = QCheckBox("Enable Telegram Notifications on Deploy Success/Failure")
        self.chk_tg_enabled.toggled.connect(self._toggle_tg_fields)

        self.txt_tg_token = QLineEdit()
        self.txt_tg_token.setPlaceholderText("e.g. 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")

        self.txt_tg_chat_id = QLineEdit()
        self.txt_tg_chat_id.setPlaceholderText("e.g. -100123456789 or 987654321")

        tg_test_row = QHBoxLayout()
        self.btn_test_tg = QPushButton("Send Test Message")
        self.btn_test_tg.clicked.connect(self._test_telegram)
        self.lbl_tg_status = QLabel("")
        self.lbl_tg_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        tg_test_row.addWidget(self.btn_test_tg)
        tg_test_row.addWidget(self.lbl_tg_status)
        tg_test_row.addStretch()

        form_tg.addRow("", self.chk_tg_enabled)
        form_tg.addRow("Bot Token:", self.txt_tg_token)
        form_tg.addRow("Chat ID:", self.txt_tg_chat_id)
        form_tg.addRow("", tg_test_row)
        layout.addWidget(grp_tg)

        # 3. Windows Server RDP Persistence & Task Scheduler Helper
        grp_task = QGroupBox("Windows Server Background Persistence (Survives RDP Sign-out)")
        layout_task = QVBoxLayout(grp_task)
        layout_task.setSpacing(8)

        lbl_task_info = QLabel(
            "AutoDeploy's headless Engine runs as a Windows background task that starts automatically on system boot "
            "and continues running even after you disconnect or sign out of your RDP session."
        )
        lbl_task_info.setWordWrap(True)
        lbl_task_info.setStyleSheet("color: #cbd5e1;")
        layout_task.addWidget(lbl_task_info)

        sch_box = QHBoxLayout()
        self.txt_sch_cmd = QLineEdit(get_task_scheduler_cmd())
        self.txt_sch_cmd.setReadOnly(True)
        btn_copy_sch = QPushButton("Copy schtasks Command")
        btn_copy_sch.clicked.connect(self._copy_schtasks)
        sch_box.addWidget(self.txt_sch_cmd)
        sch_box.addWidget(btn_copy_sch)
        layout_task.addLayout(sch_box)

        lbl_admin_hint = QLabel("Run the copied command in an Administrator Command Prompt or PowerShell to register the auto-start task.")
        lbl_admin_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_task.addWidget(lbl_admin_hint)

        # Data directory button
        dir_box = QHBoxLayout()
        lbl_data_dir = QLabel(f"Data Directory: {DATA_DIR}")
        lbl_data_dir.setStyleSheet("color: #94a3b8; font-size: 12px;")
        btn_open_dir = QPushButton("Open Folder in Explorer")
        btn_open_dir.clicked.connect(self._open_data_dir)
        dir_box.addWidget(lbl_data_dir)
        dir_box.addStretch()
        dir_box.addWidget(btn_open_dir)
        layout_task.addLayout(dir_box)

        layout.addWidget(grp_task)

        layout.addStretch()

        # Save Button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_save = QPushButton("Save Settings")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self.save_settings)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def load_settings(self) -> None:
        cfg = load_config()
        server_cfg = cfg.get("server", {})
        host = server_cfg.get("host", "0.0.0.0")
        idx = self.cmb_host.findData(host)
        if idx >= 0:
            self.cmb_host.setCurrentIndex(idx)
        self.spin_port.setValue(int(server_cfg.get("port", 9876)))

        tg_cfg = cfg.get("telegram", {})
        self.chk_tg_enabled.setChecked(bool(tg_cfg.get("enabled", False)))
        self.txt_tg_token.setText(tg_cfg.get("bot_token", ""))
        self.txt_tg_chat_id.setText(tg_cfg.get("chat_id", ""))
        self._toggle_tg_fields(self.chk_tg_enabled.isChecked())

    def _toggle_tg_fields(self, enabled: bool) -> None:
        self.txt_tg_token.setEnabled(enabled)
        self.txt_tg_chat_id.setEnabled(enabled)
        self.btn_test_tg.setEnabled(enabled)

    def _test_telegram(self) -> None:
        token = self.txt_tg_token.text().strip()
        chat_id = self.txt_tg_chat_id.text().strip()
        if not token or not chat_id:
            QMessageBox.warning(self, "Missing Credentials", "Please enter both Bot Token and Chat ID.")
            return

        self.lbl_tg_status.setText("Sending test message...")
        self.lbl_tg_status.setStyleSheet("color: #38bdf8;")
        self.btn_test_tg.setEnabled(False)

        worker = TelegramTestWorker(token, chat_id)
        worker.signals.finished.connect(self._on_tg_test_finished)
        QThreadPool.globalInstance().start(worker)

    def _on_tg_test_finished(self, success: bool, msg: str) -> None:
        self.btn_test_tg.setEnabled(True)
        if success:
            self.lbl_tg_status.setText("Success: Telegram message delivered!")
            self.lbl_tg_status.setStyleSheet("color: #34d399;")
        else:
            self.lbl_tg_status.setText(f"Error: {msg[:60]}")
            self.lbl_tg_status.setStyleSheet("color: #f87171;")

    def _copy_schtasks(self) -> None:
        cmd = self.txt_sch_cmd.text()
        QApplication.clipboard().setText(cmd)
        QMessageBox.information(
            self,
            "Command Copied",
            "Command copied to clipboard!\n\nOpen an elevated (Run as Administrator) CMD/PowerShell and paste to install."
        )

    def _open_data_dir(self) -> None:
        try:
            os.startfile(str(DATA_DIR))
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Failed to open directory: {exc}")

    def save_settings(self) -> None:
        cfg = load_config()
        cfg["server"]["host"] = self.cmb_host.currentData()
        cfg["server"]["port"] = self.spin_port.value()
        cfg["telegram"] = {
            "enabled": self.chk_tg_enabled.isChecked(),
            "bot_token": self.txt_tg_token.text().strip(),
            "chat_id": self.txt_tg_chat_id.text().strip()
        }
        save_config(cfg)
        QMessageBox.information(self, "Saved", "Settings saved successfully! Configuration has been updated.")
