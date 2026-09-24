"""
Project configuration dialog for AutoDeploy.
Allows adding or editing projects with presets, Git connection verification,
step sequencing, webhook helper, and restart command templates.
"""

import secrets
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import RESTART_PRESETS, create_default_project
from gui.workers import GitTestWorker

class ProjectEditDialog(QDialog):
    def __init__(self, project_data: Optional[Dict[str, Any]] = None, engine_port: int = 9876, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine_port = engine_port
        self.is_new = project_data is None
        self.project_data = dict(project_data) if project_data else create_default_project()
        
        self.setWindowTitle("Edit Project" if not self.is_new else "Add New Project")
        self.setMinimumSize(680, 620)
        self._init_ui()
        self._load_data()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.tab_widget = QTabWidget(self)

        # Tab 1: General & Git
        tab_general = QWidget()
        layout_general = QVBoxLayout(tab_general)
        layout_general.setSpacing(10)

        # Basic Info Group
        grp_basic = QGroupBox("Basic Information")
        form_basic = QFormLayout(grp_basic)
        form_basic.setSpacing(8)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. Backend API")
        self.txt_name.textChanged.connect(self._on_name_changed)

        self.txt_id = QLineEdit()
        self.txt_id.setPlaceholderText("e.g. backend-api (used in webhook URL)")
        if not self.is_new:
            self.txt_id.setReadOnly(True)  # Don't change existing ID to avoid breaking webhook URL

        self.chk_enabled = QCheckBox("Project Enabled")
        self.chk_enabled.setChecked(True)

        form_basic.addRow("Project Name:", self.txt_name)
        form_basic.addRow("Project ID:", self.txt_id)
        form_basic.addRow("", self.chk_enabled)
        layout_general.addWidget(grp_basic)

        # Git Repository Group
        grp_git = QGroupBox("Git Repository Configuration")
        form_git = QFormLayout(grp_git)
        form_git.setSpacing(8)

        # Path picker
        path_box = QHBoxLayout()
        self.txt_path = QLineEdit()
        self.txt_path.setPlaceholderText(r"C:\apps\my-project")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_repo_path)
        path_box.addWidget(self.txt_path)
        path_box.addWidget(btn_browse)

        self.txt_remote = QLineEdit("origin")
        self.txt_branch = QLineEdit("main")

        # Test Git Connection button & status
        test_box = QHBoxLayout()
        self.btn_test_git = QPushButton("Test Git Connection")
        self.btn_test_git.clicked.connect(self._test_git_connection)
        self.lbl_git_status = QLabel("Ready to test")
        self.lbl_git_status.setStyleSheet("color: #94a3b8;")
        test_box.addWidget(self.btn_test_git)
        test_box.addWidget(self.lbl_git_status)
        test_box.addStretch()

        form_git.addRow("Repo Path (VPS):", path_box)
        form_git.addRow("Git Remote:", self.txt_remote)
        form_git.addRow("Git Branch:", self.txt_branch)
        form_git.addRow("", test_box)
        layout_general.addWidget(grp_git)

        # Execution Environment Group
        grp_env = QGroupBox("Execution Environment")
        form_env = QFormLayout(grp_env)
        form_env.setSpacing(8)

        self.cmb_shell = QComboBox()
        self.cmb_shell.addItems(["cmd", "powershell"])

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(10, 3600)
        self.spin_timeout.setValue(300)
        self.spin_timeout.setSuffix(" seconds")

        self.chk_rollback = QCheckBox("Rollback to previous commit and re-run restart command on failure")
        self.chk_rollback.setChecked(True)

        form_env.addRow("Shell Engine:", self.cmb_shell)
        form_env.addRow("Step Timeout:", self.spin_timeout)
        form_env.addRow("", self.chk_rollback)
        layout_general.addWidget(grp_env)
        layout_general.addStretch()

        self.tab_widget.addTab(tab_general, "General & Git")

        # Tab 2: Triggers (Webhook & Polling)
        tab_triggers = QWidget()
        layout_triggers = QVBoxLayout(tab_triggers)
        layout_triggers.setSpacing(10)

        grp_trig_mode = QGroupBox("Trigger Mode")
        form_trig = QFormLayout(grp_trig_mode)
        
        self.cmb_trigger_mode = QComboBox()
        self.cmb_trigger_mode.addItem("Both Webhook & Polling", "both")
        self.cmb_trigger_mode.addItem("Webhook Only", "webhook")
        self.cmb_trigger_mode.addItem("Polling Only", "polling")
        self.cmb_trigger_mode.currentIndexChanged.connect(self._on_trigger_mode_changed)
        form_trig.addRow("Trigger Type:", self.cmb_trigger_mode)
        layout_triggers.addWidget(grp_trig_mode)

        # Webhook Settings
        self.grp_webhook = QGroupBox("GitHub Webhook Configuration")
        form_wh = QFormLayout(self.grp_webhook)
        form_wh.setSpacing(8)

        # Webhook URL display & copy
        wh_url_box = QHBoxLayout()
        self.lbl_webhook_url = QLineEdit()
        self.lbl_webhook_url.setReadOnly(True)
        btn_copy_wh = QPushButton("Copy URL")
        btn_copy_wh.clicked.connect(self._copy_webhook_url)
        wh_url_box.addWidget(self.lbl_webhook_url)
        wh_url_box.addWidget(btn_copy_wh)

        # Secret & generate button
        secret_box = QHBoxLayout()
        self.txt_secret = QLineEdit()
        self.txt_secret.setPlaceholderText("Webhook HMAC Secret")
        btn_gen_secret = QPushButton("Generate")
        btn_gen_secret.clicked.connect(self._generate_secret)
        secret_box.addWidget(self.txt_secret)
        secret_box.addWidget(btn_gen_secret)

        form_wh.addRow("Webhook URL:", wh_url_box)
        form_wh.addRow("Webhook Secret:", secret_box)

        lbl_wh_tip = QLabel("In GitHub Repo Settings -> Webhooks: Set Payload URL to the URL above, Content type: application/json, and paste the Secret.")
        lbl_wh_tip.setWordWrap(True)
        lbl_wh_tip.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_wh.addRow("", lbl_wh_tip)
        layout_triggers.addWidget(self.grp_webhook)

        # Polling Settings
        self.grp_polling = QGroupBox("Git Polling Configuration")
        form_poll = QFormLayout(self.grp_polling)
        self.spin_poll_interval = QSpinBox()
        self.spin_poll_interval.setRange(5, 86400)
        self.spin_poll_interval.setValue(60)
        self.spin_poll_interval.setSuffix(" seconds")
        form_poll.addRow("Check Interval:", self.spin_poll_interval)

        lbl_poll_tip = QLabel("Checks remote repository for new commits using 'git ls-remote' without needing an open webhook port.")
        lbl_poll_tip.setWordWrap(True)
        lbl_poll_tip.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_poll.addRow("", lbl_poll_tip)
        layout_triggers.addWidget(self.grp_polling)
        layout_triggers.addStretch()

        self.tab_widget.addTab(tab_triggers, "Triggers")

        # Tab 3: Build Steps & Restart Command
        tab_steps = QWidget()
        layout_steps = QVBoxLayout(tab_steps)
        layout_steps.setSpacing(10)

        # Steps list
        grp_steps = QGroupBox("Deployment Steps (Executed Sequentially in Repo Directory)")
        layout_step_grp = QVBoxLayout(grp_steps)

        self.step_list = QListWidget()
        layout_step_grp.addWidget(self.step_list)

        step_btn_box = QHBoxLayout()
        btn_add_step = QPushButton("+ Add Step")
        btn_add_step.clicked.connect(self._add_step)
        btn_edit_step = QPushButton("Edit")
        btn_edit_step.clicked.connect(self._edit_selected_step)
        btn_del_step = QPushButton("Remove")
        btn_del_step.clicked.connect(self._remove_step)
        btn_up_step = QPushButton("Up")
        btn_up_step.clicked.connect(self._move_step_up)
        btn_down_step = QPushButton("Down")
        btn_down_step.clicked.connect(self._move_step_down)

        step_btn_box.addWidget(btn_add_step)
        step_btn_box.addWidget(btn_edit_step)
        step_btn_box.addWidget(btn_del_step)
        step_btn_box.addWidget(btn_up_step)
        step_btn_box.addWidget(btn_down_step)
        step_btn_box.addStretch()

        # Step Template shortcuts
        template_box = QHBoxLayout()
        lbl_templates = QLabel("Templates:")
        btn_tpl_git = QPushButton("Git Fetch/Reset")
        btn_tpl_git.clicked.connect(self._apply_git_steps)
        btn_tpl_py = QPushButton("Python/Pip")
        btn_tpl_py.clicked.connect(self._apply_py_steps)
        btn_tpl_node = QPushButton("Node/NPM")
        btn_tpl_node.clicked.connect(self._apply_node_steps)

        template_box.addWidget(lbl_templates)
        template_box.addWidget(btn_tpl_git)
        template_box.addWidget(btn_tpl_py)
        template_box.addWidget(btn_tpl_node)
        template_box.addStretch()

        layout_step_grp.addLayout(step_btn_box)
        layout_step_grp.addLayout(template_box)
        layout_steps.addWidget(grp_steps)

        # Restart Command Group
        grp_restart = QGroupBox("Application Restart Command")
        layout_restart = QVBoxLayout(grp_restart)
        layout_restart.setSpacing(8)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self.cmb_restart_preset = QComboBox()
        for key, p_data in RESTART_PRESETS.items():
            self.cmb_restart_preset.addItem(p_data["label"], key)
        self.cmb_restart_preset.currentIndexChanged.connect(self._on_restart_preset_changed)
        preset_row.addWidget(self.cmb_restart_preset)
        preset_row.addStretch()
        layout_restart.addLayout(preset_row)

        self.txt_restart_cmd = QLineEdit()
        self.txt_restart_cmd.setPlaceholderText('e.g. net stop "MyService" & net start "MyService"')
        layout_restart.addWidget(self.txt_restart_cmd)

        lbl_restart_tip = QLabel("Executed after all build steps succeed (and re-executed after rollback if enabled).")
        lbl_restart_tip.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_restart.addWidget(lbl_restart_tip)
        layout_steps.addWidget(grp_restart)

        self.tab_widget.addTab(tab_steps, "Steps & Restart")

        main_layout.addWidget(self.tab_widget)

        # Dialog Buttons
        bottom_box = QHBoxLayout()
        bottom_box.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Project")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save_and_close)
        bottom_box.addWidget(btn_cancel)
        bottom_box.addWidget(btn_save)
        main_layout.addLayout(bottom_box)

    def _load_data(self) -> None:
        p = self.project_data
        self.txt_name.setText(p.get("name", ""))
        self.txt_id.setText(p.get("id", ""))
        self.chk_enabled.setChecked(p.get("enabled", True))
        self.txt_path.setText(p.get("path", ""))
        self.txt_remote.setText(p.get("remote", "origin"))
        self.txt_branch.setText(p.get("branch", "main"))
        self.cmb_shell.setCurrentText(p.get("shell", "cmd"))
        self.spin_timeout.setValue(int(p.get("timeout", 300)))
        self.chk_rollback.setChecked(bool(p.get("rollback_on_failure", True)))

        mode = p.get("trigger_mode", "both")
        idx = self.cmb_trigger_mode.findData(mode)
        if idx >= 0:
            self.cmb_trigger_mode.setCurrentIndex(idx)
        self._on_trigger_mode_changed()

        self.txt_secret.setText(p.get("secret", ""))
        self.spin_poll_interval.setValue(int(p.get("polling_interval", 60)))
        self._update_webhook_url()

        # Steps
        self.step_list.clear()
        for step in p.get("steps", []):
            self.step_list.addItem(step)

        # Restart command
        self.txt_restart_cmd.setText(p.get("restart_command", ""))

    def _on_name_changed(self, text: str) -> None:
        if self.is_new:
            # Auto slug ID if user hasn't explicitly edited ID
            slug = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in text.lower()).strip("-")
            self.txt_id.setText(slug)
            self._update_webhook_url()

    def _update_webhook_url(self) -> None:
        proj_id = self.txt_id.text().strip() or "<project_id>"
        url = f"http://<your-vps-ip>:{self.engine_port}/hook/{proj_id}"
        self.lbl_webhook_url.setText(url)

    def _browse_repo_path(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Git Repository Directory", self.txt_path.text())
        if chosen:
            self.txt_path.setText(chosen)

    def _on_trigger_mode_changed(self) -> None:
        mode = self.cmb_trigger_mode.currentData()
        self.grp_webhook.setEnabled(mode in ("webhook", "both"))
        self.grp_polling.setEnabled(mode in ("polling", "both"))

    def _generate_secret(self) -> None:
        self.txt_secret.setText(secrets.token_hex(16))

    def _copy_webhook_url(self) -> None:
        QApplication.clipboard().setText(self.lbl_webhook_url.text())
        QMessageBox.information(self, "Copied", "Webhook URL copied to clipboard.")

    def _test_git_connection(self) -> None:
        repo_path = self.txt_path.text().strip()
        remote = self.txt_remote.text().strip()
        branch = self.txt_branch.text().strip()
        if not repo_path:
            QMessageBox.warning(self, "Missing Path", "Please specify a repository path first.")
            return

        self.lbl_git_status.setText("Checking remote...")
        self.lbl_git_status.setStyleSheet("color: #38bdf8;")
        self.btn_test_git.setEnabled(False)

        worker = GitTestWorker(repo_path, remote, branch)
        worker.signals.finished.connect(self._on_git_test_finished)
        QThreadPool.globalInstance().start(worker)

    def _on_git_test_finished(self, success: bool, local_sha: str, result_msg: str) -> None:
        self.btn_test_git.setEnabled(True)
        if success:
            short_loc = local_sha[:7] if local_sha else "none"
            short_rem = result_msg[:7] if result_msg else "none"
            self.lbl_git_status.setText(f"Connected! Local: {short_loc} | Remote: {short_rem}")
            self.lbl_git_status.setStyleSheet("color: #34d399;")
        else:
            self.lbl_git_status.setText(f"Error: {result_msg[:60]}")
            self.lbl_git_status.setStyleSheet("color: #f87171;")

    def _add_step(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Add Step", "Command to execute:")
        if ok and text.strip():
            self.step_list.addItem(text.strip())

    def _edit_selected_step(self) -> None:
        item = self.step_list.currentItem()
        if not item:
            return
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Edit Step", "Command to execute:", text=item.text())
        if ok and text.strip():
            item.setText(text.strip())

    def _remove_step(self) -> None:
        row = self.step_list.currentRow()
        if row >= 0:
            self.step_list.takeItem(row)

    def _move_step_up(self) -> None:
        row = self.step_list.currentRow()
        if row > 0:
            item = self.step_list.takeItem(row)
            self.step_list.insertItem(row - 1, item)
            self.step_list.setCurrentRow(row - 1)

    def _move_step_down(self) -> None:
        row = self.step_list.currentRow()
        if row < self.step_list.count() - 1:
            item = self.step_list.takeItem(row)
            self.step_list.insertItem(row + 1, item)
            self.step_list.setCurrentRow(row + 1)

    def _apply_git_steps(self) -> None:
        branch = self.txt_branch.text().strip() or "main"
        remote = self.txt_remote.text().strip() or "origin"
        self.step_list.clear()
        self.step_list.addItem(f"git fetch {remote} {branch}")
        self.step_list.addItem(f"git reset --hard {remote}/{branch}")

    def _apply_py_steps(self) -> None:
        self._apply_git_steps()
        self.step_list.addItem("pip install -r requirements.txt")

    def _apply_node_steps(self) -> None:
        self._apply_git_steps()
        self.step_list.addItem("npm ci")
        self.step_list.addItem("npm run build")

    def _on_restart_preset_changed(self) -> None:
        key = self.cmb_restart_preset.currentData()
        if key in RESTART_PRESETS and RESTART_PRESETS[key]["command"]:
            self.txt_restart_cmd.setText(RESTART_PRESETS[key]["command"])

    def _save_and_close(self) -> None:
        proj_id = self.txt_id.text().strip()
        name = self.txt_name.text().strip()
        path = self.txt_path.text().strip()

        if not proj_id or not name or not path:
            QMessageBox.warning(self, "Validation Error", "Name, ID, and Repo Path are required.")
            return

        steps = [self.step_list.item(i).text() for i in range(self.step_list.count())]

        self.project_data = {
            "id": proj_id,
            "name": name,
            "enabled": self.chk_enabled.isChecked(),
            "path": path,
            "remote": self.txt_remote.text().strip() or "origin",
            "branch": self.txt_branch.text().strip() or "main",
            "trigger_mode": self.cmb_trigger_mode.currentData(),
            "secret": self.txt_secret.text().strip(),
            "polling_interval": self.spin_poll_interval.value(),
            "steps": steps,
            "restart_command": self.txt_restart_cmd.text().strip(),
            "timeout": self.spin_timeout.value(),
            "rollback_on_failure": self.chk_rollback.isChecked(),
            "shell": self.cmb_shell.currentText()
        }
        self.accept()

    def get_project_data(self) -> Dict[str, Any]:
        return self.project_data
