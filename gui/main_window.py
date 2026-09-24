"""
Main PySide6 GUI window for AutoDeploy.
Provides project management, manual deployment triggers, real-time engine status monitoring,
and history inspection while strictly adhering to /antislop-ui.
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import load_config, save_config
from core.history import load_history
from core.paths import DATA_DIR
from core.service_ctl import (
    get_engine_status,
    restart_engine_process,
    start_engine_process,
    stop_engine_process,
)
from gui.history_view import HistoryView
from gui.project_dialog import ProjectEditDialog
from gui.settings_view import SettingsView
from gui.styles import DARK_THEME_QSS
from gui.workers import ManualDeployWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoDeploy - Windows Server CI/CD Engine")
        self.setMinimumSize(980, 680)
        self.setStyleSheet(DARK_THEME_QSS)

        self.config: Dict[str, Any] = load_config()
        self.thread_pool = QThreadPool.globalInstance()

        self._init_ui()
        self.reload_projects_table()

        # Polling timer for engine status and history sync (every 3 seconds)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(3000)
        self._update_engine_status_ui()

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Panel
        header = QFrame()
        header.setObjectName("headerPanel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_app_name = QLabel("AutoDeploy")
        lbl_app_name.setStyleSheet("font-size: 17px; font-weight: 700; color: #f8fafc;")
        lbl_subtitle = QLabel("Windows Server Deployment Engine")
        lbl_subtitle.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_box.addWidget(lbl_app_name)
        title_box.addWidget(lbl_subtitle)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Engine Status Badge & Buttons
        engine_box = QHBoxLayout()
        engine_box.setSpacing(8)

        self.lbl_engine_badge = QLabel("Engine: Checking...")
        self.lbl_engine_badge.setObjectName("badgeStopped")
        engine_box.addWidget(self.lbl_engine_badge)

        self.btn_start_engine = QPushButton("Start Engine")
        self.btn_start_engine.setObjectName("successBtn")
        self.btn_start_engine.clicked.connect(self._start_engine)
        engine_box.addWidget(self.btn_start_engine)

        self.btn_stop_engine = QPushButton("Stop Engine")
        self.btn_stop_engine.setObjectName("dangerBtn")
        self.btn_stop_engine.clicked.connect(self._stop_engine)
        engine_box.addWidget(self.btn_stop_engine)

        self.btn_restart_engine = QPushButton("Restart")
        self.btn_restart_engine.clicked.connect(self._restart_engine)
        engine_box.addWidget(self.btn_restart_engine)

        header_layout.addLayout(engine_box)
        main_layout.addWidget(header)

        # 2. Main Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setContentsMargins(12, 12, 12, 12)

        # Tab: Projects
        self.tab_projects = QWidget()
        self._init_projects_tab()
        self.tab_widget.addTab(self.tab_projects, "Projects")

        # Tab: Deploy History
        self.history_view = HistoryView()
        self.tab_widget.addTab(self.history_view, "Deploy History")

        # Tab: Global Settings
        self.settings_view = SettingsView()
        self.tab_widget.addTab(self.settings_view, "Global Settings")

        main_layout.addWidget(self.tab_widget)

        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Config path: {DATA_DIR} | Closing GUI will NOT stop background Engine.")

    def _init_projects_tab(self) -> None:
        p_layout = QVBoxLayout(self.tab_projects)
        p_layout.setContentsMargins(16, 16, 16, 16)
        p_layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_add = QPushButton("+ Add Project")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_project)
        toolbar.addWidget(btn_add)

        self.btn_deploy_now = QPushButton("Deploy Selected Now")
        self.btn_deploy_now.clicked.connect(self._deploy_selected)
        toolbar.addWidget(self.btn_deploy_now)

        self.btn_edit_project = QPushButton("Edit")
        self.btn_edit_project.clicked.connect(self._edit_selected_project)
        toolbar.addWidget(self.btn_edit_project)

        self.btn_toggle_project = QPushButton("Toggle Active")
        self.btn_toggle_project.clicked.connect(self._toggle_selected_project)
        toolbar.addWidget(self.btn_toggle_project)

        self.btn_delete_project = QPushButton("Delete")
        self.btn_delete_project.setObjectName("dangerBtn")
        self.btn_delete_project.clicked.connect(self._delete_selected_project)
        toolbar.addWidget(self.btn_delete_project)

        toolbar.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.reload_projects_table)
        toolbar.addWidget(btn_refresh)

        p_layout.addLayout(toolbar)

        # Projects Table
        self.table_projects = QTableWidget()
        self.table_projects.setColumnCount(7)
        self.table_projects.setHorizontalHeaderLabels([
            "State", "Project Name", "Branch", "Trigger", "Last Status", "Last Deploy", "Local Path"
        ])
        self.table_projects.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_projects.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_projects.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_projects.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_projects.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_projects.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_projects.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table_projects.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_projects.setSelectionMode(QTableWidget.SingleSelection)
        self.table_projects.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_projects.doubleClicked.connect(self._edit_selected_project)

        p_layout.addWidget(self.table_projects)

    def _on_tick(self) -> None:
        self._update_engine_status_ui()

    def _update_engine_status_ui(self) -> None:
        is_running, pid = get_engine_status()
        port = self.config.get("server", {}).get("port", 9876)

        if is_running and pid:
            self.lbl_engine_badge.setText(f"Engine: Running (PID: {pid}, Port: {port})")
            self.lbl_engine_badge.setObjectName("badgeRunning")
            self.btn_start_engine.setEnabled(False)
            self.btn_stop_engine.setEnabled(True)
            self.btn_restart_engine.setEnabled(True)
        else:
            self.lbl_engine_badge.setText("Engine: Stopped")
            self.lbl_engine_badge.setObjectName("badgeStopped")
            self.btn_start_engine.setEnabled(True)
            self.btn_stop_engine.setEnabled(False)
            self.btn_restart_engine.setEnabled(False)

        # Force style re-polish
        self.lbl_engine_badge.style().unpolish(self.lbl_engine_badge)
        self.lbl_engine_badge.style().polish(self.lbl_engine_badge)

    def _start_engine(self) -> None:
        self.status_bar.showMessage("Starting Engine process...")
        success, msg = start_engine_process()
        self._update_engine_status_ui()
        self.status_bar.showMessage(msg)

    def _stop_engine(self) -> None:
        self.status_bar.showMessage("Stopping Engine process...")
        success, msg = stop_engine_process()
        self._update_engine_status_ui()
        self.status_bar.showMessage(msg)

    def _restart_engine(self) -> None:
        self.status_bar.showMessage("Restarting Engine process...")
        success, msg = restart_engine_process()
        self._update_engine_status_ui()
        self.status_bar.showMessage(msg)

    def reload_projects_table(self) -> None:
        self.config = load_config()
        projects = self.config.get("projects", [])
        history_entries = load_history(100)

        # Build last status lookup by project_id
        last_status_map = {}
        for h in history_entries:
            p_id = h.get("project_id")
            if p_id and p_id not in last_status_map:
                last_status_map[p_id] = h

        self.table_projects.setRowCount(len(projects))
        for row, p in enumerate(projects):
            p_id = p.get("id", "")
            enabled = p.get("enabled", True)

            # State indicator
            state_lbl = QLabel("ENABLED" if enabled else "DISABLED")
            state_lbl.setObjectName("badgeSuccess" if enabled else "badgeStopped")
            state_lbl.setAlignment(Qt.AlignCenter)
            state_cont = QWidget()
            s_layout = QHBoxLayout(state_cont)
            s_layout.setContentsMargins(4, 2, 4, 2)
            s_layout.addWidget(state_lbl)
            self.table_projects.setCellWidget(row, 0, state_cont)

            # Name
            self.table_projects.setItem(row, 1, QTableWidgetItem(p.get("name", "")))

            # Branch
            self.table_projects.setItem(row, 2, QTableWidgetItem(f"{p.get('remote', 'origin')}/{p.get('branch', 'main')}"))

            # Trigger Mode
            self.table_projects.setItem(row, 3, QTableWidgetItem(p.get("trigger_mode", "both").upper()))

            # Last Status
            last_run = last_status_map.get(p_id)
            if last_run:
                status_txt = last_run.get("status", "unknown").upper()
                last_time = last_run.get("timestamp", "").replace("T", " ")[:19]
            else:
                status_txt = "NONE"
                last_time = "-"

            badge = QLabel(status_txt)
            badge.setAlignment(Qt.AlignCenter)
            if status_txt == "SUCCESS":
                badge.setObjectName("badgeSuccess")
            elif status_txt == "ROLLED_BACK":
                badge.setObjectName("badgeRolledBack")
            elif status_txt == "FAILED":
                badge.setObjectName("badgeFailed")
            else:
                badge.setObjectName("badgeStopped")

            badge_cont = QWidget()
            b_layout = QHBoxLayout(badge_cont)
            b_layout.setContentsMargins(4, 2, 4, 2)
            b_layout.addWidget(badge)
            self.table_projects.setCellWidget(row, 4, badge_cont)

            # Last Deploy Time
            self.table_projects.setItem(row, 5, QTableWidgetItem(last_time))

            # Local Path
            self.table_projects.setItem(row, 6, QTableWidgetItem(p.get("path", "")))

        # Update HistoryView project filter list
        self.history_view.update_project_filter_options(projects)
        self.status_bar.showMessage(f"Loaded {len(projects)} projects.")

    def _get_selected_project(self) -> Optional[Dict[str, Any]]:
        row = self.table_projects.currentRow()
        projects = self.config.get("projects", [])
        if 0 <= row < len(projects):
            return projects[row]
        return None

    def _add_project(self) -> None:
        port = self.config.get("server", {}).get("port", 9876)
        dialog = ProjectEditDialog(project_data=None, engine_port=port, parent=self)
        if dialog.exec() == ProjectEditDialog.Accepted:
            new_project = dialog.get_project_data()
            self.config.setdefault("projects", []).append(new_project)
            save_config(self.config)
            self.reload_projects_table()
            self.status_bar.showMessage(f"Project '{new_project.get('name')}' created.")

    def _edit_selected_project(self) -> None:
        project = self._get_selected_project()
        if not project:
            QMessageBox.information(self, "Select Project", "Please select a project from the table to edit.")
            return

        port = self.config.get("server", {}).get("port", 9876)
        dialog = ProjectEditDialog(project_data=project, engine_port=port, parent=self)
        if dialog.exec() == ProjectEditDialog.Accepted:
            updated = dialog.get_project_data()
            # Replace in list
            for i, p in enumerate(self.config.get("projects", [])):
                if p.get("id") == updated.get("id"):
                    self.config["projects"][i] = updated
                    break
            save_config(self.config)
            self.reload_projects_table()
            self.status_bar.showMessage(f"Project '{updated.get('name')}' updated.")

    def _toggle_selected_project(self) -> None:
        project = self._get_selected_project()
        if not project:
            return
        
        project["enabled"] = not project.get("enabled", True)
        save_config(self.config)
        self.reload_projects_table()
        state_str = "enabled" if project["enabled"] else "disabled"
        self.status_bar.showMessage(f"Project '{project.get('name')}' is now {state_str}.")

    def _delete_selected_project(self) -> None:
        project = self._get_selected_project()
        if not project:
            QMessageBox.information(self, "Select Project", "Please select a project to delete.")
            return

        name = project.get("name", "this project")
        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to remove project '{name}' from AutoDeploy?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.config["projects"] = [p for p in self.config.get("projects", []) if p.get("id") != project.get("id")]
            save_config(self.config)
            self.reload_projects_table()
            self.status_bar.showMessage(f"Deleted project '{name}'.")

    def _deploy_selected(self) -> None:
        project = self._get_selected_project()
        if not project:
            QMessageBox.information(self, "Select Project", "Please select a project to deploy.")
            return

        name = project.get("name")
        self.status_bar.showMessage(f"Triggering manual deploy for '{name}'...")
        self.btn_deploy_now.setEnabled(False)

        port = self.config.get("server", {}).get("port", 9876)
        tg_cfg = self.config.get("telegram")
        worker = ManualDeployWorker(project, tg_cfg, engine_port=port)
        worker.signals.finished.connect(self._on_deploy_finished)
        self.thread_pool.start(worker)

    def _on_deploy_finished(self, success: bool, msg: str) -> None:
        self.btn_deploy_now.setEnabled(True)
        self.status_bar.showMessage(f"Deploy result: {msg}")
        self.reload_projects_table()
        self.history_view.refresh_history()

    def closeEvent(self, event) -> None:
        # User specified: Closing GUI does NOT stop the engine.
        event.accept()
