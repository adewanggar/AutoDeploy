"""
Deployment history monitor for AutoDeploy.
Displays up to 500 historical deployments in a searchable, filterable table
with step-by-step stdout/stderr drilldown and diagnostics.
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.history import load_history

class HistoryView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.all_entries: List[Dict[str, Any]] = []
        self.filtered_entries: List[Dict[str, Any]] = []
        self._init_ui()
        self.refresh_history()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        filter_bar.addWidget(QLabel("Project:"))
        self.cmb_filter_project = QComboBox()
        self.cmb_filter_project.addItem("All Projects", "")
        self.cmb_filter_project.currentIndexChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.cmb_filter_project)

        filter_bar.addWidget(QLabel("Status:"))
        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("All Statuses", "")
        self.cmb_filter_status.addItem("Success", "success")
        self.cmb_filter_status.addItem("Failed", "failed")
        self.cmb_filter_status.addItem("Rolled Back", "rolled_back")
        self.cmb_filter_status.currentIndexChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.cmb_filter_status)

        filter_bar.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh_history)
        filter_bar.addWidget(btn_refresh)

        layout.addLayout(filter_bar)

        # Splitter between Table and Detail Inspector
        splitter = QSplitter(Qt.Vertical)

        # Top: Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Timestamp", "Project", "Trigger", "Status", "Commit Transition", "Duration"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        # Bottom: Detail View
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 8, 0, 0)
        detail_layout.setSpacing(6)

        detail_header = QHBoxLayout()
        self.lbl_detail_title = QLabel("Execution Details")
        self.lbl_detail_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        btn_copy_log = QPushButton("Copy Step Logs")
        btn_copy_log.clicked.connect(self._copy_log)
        detail_header.addWidget(self.lbl_detail_title)
        detail_header.addStretch()
        detail_header.addWidget(btn_copy_log)
        detail_layout.addLayout(detail_header)

        self.txt_meta = QLabel("Select a deployment above to inspect.")
        self.txt_meta.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.txt_meta.setWordWrap(True)
        detail_layout.addWidget(self.txt_meta)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet(
            "background-color: #0b1120; color: #f1f5f9; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;"
        )
        detail_layout.addWidget(self.txt_log)
        splitter.addWidget(detail_container)

        splitter.setSizes([320, 260])
        layout.addWidget(splitter)

    def update_project_filter_options(self, projects: List[Dict[str, Any]]) -> None:
        curr = self.cmb_filter_project.currentData()
        self.cmb_filter_project.blockSignals(True)
        self.cmb_filter_project.clear()
        self.cmb_filter_project.addItem("All Projects", "")
        for p in projects:
            self.cmb_filter_project.addItem(p.get("name", p.get("id")), p.get("id"))
        idx = self.cmb_filter_project.findData(curr)
        if idx >= 0:
            self.cmb_filter_project.setCurrentIndex(idx)
        self.cmb_filter_project.blockSignals(False)

    def refresh_history(self) -> None:
        self.all_entries = load_history(500)
        self._apply_filters()

    def _apply_filters(self) -> None:
        proj_filter = self.cmb_filter_project.currentData()
        status_filter = self.cmb_filter_status.currentData()

        self.filtered_entries = [
            e for e in self.all_entries
            if (not proj_filter or e.get("project_id") == proj_filter)
            and (not status_filter or e.get("status") == status_filter)
        ]

        self.table.setRowCount(len(self.filtered_entries))
        for row, entry in enumerate(self.filtered_entries):
            # Timestamp
            ts = entry.get("timestamp", "").replace("T", " ")[:19]
            self.table.setItem(row, 0, QTableWidgetItem(ts))

            # Project
            self.table.setItem(row, 1, QTableWidgetItem(entry.get("project_name", "Unknown")))

            # Trigger
            self.table.setItem(row, 2, QTableWidgetItem(entry.get("trigger", "manual").upper()))

            # Status Badge
            status = entry.get("status", "unknown")
            badge = QLabel(status.upper())
            badge.setAlignment(Qt.AlignCenter)
            if status == "success":
                badge.setObjectName("badgeSuccess")
            elif status == "rolled_back":
                badge.setObjectName("badgeRolledBack")
            elif status == "failed":
                badge.setObjectName("badgeFailed")
            else:
                badge.setObjectName("badgeStopped")
            
            badge_container = QWidget()
            b_layout = QHBoxLayout(badge_container)
            b_layout.setContentsMargins(4, 2, 4, 2)
            b_layout.addWidget(badge)
            self.table.setCellWidget(row, 3, badge_container)

            # Commit Transition
            old_c = (entry.get("old_commit") or "")[:7] or "initial"
            new_c = (entry.get("new_commit") or "")[:7] or "same"
            msg = entry.get("commit_message", "").strip().split("\n")[0]
            desc = f"{old_c} -> {new_c} ({msg})" if msg else f"{old_c} -> {new_c}"
            self.table.setItem(row, 4, QTableWidgetItem(desc))

            # Duration
            dur = f"{entry.get('duration_seconds', 0.0):.1f}s"
            self.table.setItem(row, 5, QTableWidgetItem(dur))

        if self.filtered_entries:
            self.table.selectRow(0)
        else:
            self.txt_meta.setText("No deployments found matching filter.")
            self.txt_log.clear()

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered_entries):
            return
        
        entry = self.filtered_entries[row]
        proj_name = entry.get("project_name", "Unknown")
        status = entry.get("status", "").upper()
        author = entry.get("author", "N/A")
        msg = entry.get("commit_message", "")
        ts = entry.get("timestamp", "").replace("T", " ")[:19]
        dur = entry.get("duration_seconds", 0.0)
        trigger = entry.get("trigger", "manual")

        self.lbl_detail_title.setText(f"Deployment Run: {proj_name} [{status}]")
        self.txt_meta.setText(
            f"Timestamp: {ts} | Trigger: {trigger} | Duration: {dur:.1f}s | Author: {author}\n"
            f"Commit Message: {msg}"
        )

        lines: List[str] = []
        steps = entry.get("steps_log", [])
        for idx, step in enumerate(steps, 1):
            cmd = step.get("command", "")
            code = step.get("exit_code", 0)
            output = step.get("output", "")
            duration = step.get("duration", 0.0)
            status_tag = "OK" if code == 0 else f"FAILED (Exit Code: {code})"

            lines.append(f"--- STEP {idx}: {cmd} [{status_tag}, {duration:.2f}s] ---")
            if output:
                lines.append(output)
            lines.append("")

        if entry.get("error_summary"):
            lines.insert(0, f"=== FAILURE SUMMARY ===\n{entry.get('error_summary')}\n")

        self.txt_log.setPlainText("\n".join(lines) if lines else "No step logs recorded.")

    def _copy_log(self) -> None:
        log_content = self.txt_log.toPlainText()
        if log_content:
            QApplication.clipboard().setText(log_content)
            QMessageBox.information(self, "Copied", "Deployment log copied to clipboard.")
