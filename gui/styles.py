"""
Clean, human-centric Slate Dark Theme for AutoDeploy PySide6 UI.
Strictly adheres to /antislop-ui: no generic gradients, no excessive radius,
no glows, strong contrast, clear semantic hierarchy.
"""

DARK_THEME_QSS = """
/* Global Window & Fonts */
QWidget {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "Segoe UI";
    font-size: 13px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}

/* Headers & Panels */
QFrame#headerPanel {
    background-color: #1e293b;
    border-bottom: 1px solid #334155;
    padding: 12px;
}

QFrame#cardPanel {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 16px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #334155;
    background-color: #0f172a;
    top: -1px;
}

QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    border-bottom: none;
    padding: 9px 18px;
    margin-right: 4px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #0f172a;
    color: #f8fafc;
    border-bottom: 1px solid #0f172a;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: #273549;
    color: #cbd5e1;
}

/* Buttons */
QPushButton {
    background-color: #334155;
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #475569;
    border-color: #64748b;
}

QPushButton:pressed {
    background-color: #1e293b;
}

QPushButton:disabled {
    background-color: #1e293b;
    color: #64748b;
    border-color: #334155;
}

/* Primary Button Accent */
QPushButton#primaryBtn {
    background-color: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#primaryBtn:hover {
    background-color: #3b82f6;
    border-color: #2563eb;
}

QPushButton#primaryBtn:pressed {
    background-color: #1d4ed8;
}

/* Success Button */
QPushButton#successBtn {
    background-color: #059669;
    border-color: #047857;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#successBtn:hover {
    background-color: #10b981;
}

/* Danger Button */
QPushButton#dangerBtn {
    background-color: #dc2626;
    border-color: #b91c1c;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#dangerBtn:hover {
    background-color: #ef4444;
}

/* Input Fields */
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 6px 10px;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #3b82f6;
    background-color: #1a2436;
}

QLineEdit:read-only {
    background-color: #16202e;
    color: #94a3b8;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #1e293b;
    border: 1px solid #475569;
    selection-background-color: #3b82f6;
    color: #f8fafc;
}

/* CheckBox */
QCheckBox {
    spacing: 8px;
    color: #f8fafc;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #475569;
    border-radius: 3px;
    background-color: #1e293b;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #3b82f6;
}

/* Table View */
QTableWidget, QTableView {
    background-color: #1e293b;
    border: 1px solid #334155;
    gridline-color: #273549;
    color: #f8fafc;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #0f172a;
    color: #cbd5e1;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #334155;
    border-right: 1px solid #1e293b;
    font-weight: 600;
}

/* Status Badges */
QLabel#badgeSuccess {
    background-color: #064e3b;
    color: #34d399;
    border: 1px solid #059669;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    font-size: 11px;
}

QLabel#badgeFailed {
    background-color: #7f1d1d;
    color: #fca5a5;
    border: 1px solid #dc2626;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    font-size: 11px;
}

QLabel#badgeRolledBack {
    background-color: #78350f;
    color: #fcd34d;
    border: 1px solid #d97706;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    font-size: 11px;
}

QLabel#badgeRunning {
    background-color: #0c4a6e;
    color: #7dd3fc;
    border: 1px solid #0284c7;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    font-size: 11px;
}

QLabel#badgeStopped {
    background-color: #334155;
    color: #cbd5e1;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    font-size: 11px;
}

/* ScrollBars */
QScrollBar:vertical {
    border: none;
    background-color: #0f172a;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #334155;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #475569;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Splitter */
QSplitter::handle {
    background-color: #334155;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}
"""
