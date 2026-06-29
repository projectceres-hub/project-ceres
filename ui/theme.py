"""
Winamp-classic theme for Project Ceres.

The app keeps its dockable GM-assistant layout, but the skin now borrows from
the original Winamp visual language: black LCD wells, green text, gold meters,
and beveled steel-blue chrome.
"""

# Palette constants
BG        = "#050608"
PANEL     = "#11131b"
SURFACE   = "#2f3548"
ACCENT    = "#00ff3c"
ACCENT2   = "#f3d94e"
TEXT      = "#00ff3c"
MUTED     = "#a8b0c2"
BORDER    = "#697084"
SUCCESS   = "#00ff3c"
WARNING   = "#f3d94e"
ERROR     = "#ff4c4c"

CHROME_DARK = "#151824"
CHROME_MID = "#3e465b"
CHROME_LITE = "#8d96aa"
BLACK_WELL = "#020302"
SHADOW = "#05060a"
HILITE = "#d6dfef"

FONT_MONO = "Consolas, 'Fira Code', 'Courier New', monospace"
FONT_SIZE = 11  # px

STYLESHEET = f"""
/* Winamp classic base */
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: Consolas, "Fira Code", "Courier New", monospace;
    font-size: {FONT_SIZE}px;
    selection-background-color: {ACCENT2};
    selection-color: #050608;
}}

QWidget:disabled {{
    color: #5c6576;
}}

/* Dock panels */
QDockWidget {{
    color: #f4f1c8;
    font-weight: bold;
    font-size: 11px;
    border: 1px solid {SHADOW};
    border-top-color: {CHROME_LITE};
    border-left-color: {CHROME_LITE};
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #161b33, stop:0.45 #4b5f95, stop:1 #111522);
    color: #f5f2c8;
    padding: 4px 8px;
    border: 1px solid {SHADOW};
    border-bottom: 2px solid {ACCENT2};
    text-align: center;
    text-transform: uppercase;
}}
QDockWidget::close-button, QDockWidget::float-button {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {HILITE}, stop:0.45 #7e889a, stop:1 #d7e0ee);
    border: 1px solid {SHADOW};
    width: 12px;
    height: 12px;
    margin: 2px;
}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background: {ACCENT2};
}}

/* Splitter */
QSplitter::handle {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {CHROME_LITE}, stop:0.5 {CHROME_MID}, stop:1 {SHADOW});
    width: 4px;
    height: 4px;
}}

/* Reusable Winamp panel body frame */
QFrame[class="winamp-panel-frame"] {{
    background: {PANEL};
    border: 1px solid {SHADOW};
    border-top-color: {CHROME_LITE};
    border-left-color: {CHROME_LITE};
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    border-radius: 1px;
}}

/* Labels */
QLabel {{
    color: {TEXT};
    background: transparent;
    padding: 1px;
}}
QLabel[class="section-header"] {{
    color: {ACCENT2};
    font-weight: bold;
    font-size: 12px;
    padding: 3px 0;
    border-bottom: 1px solid {BORDER};
}}
QLabel[class="muted"] {{
    color: {MUTED};
    font-size: 10px;
}}

/* Buttons */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #dce6f2, stop:0.42 #747f92, stop:0.58 #566174, stop:1 #c8d2df);
    color: #10131b;
    border: 1px solid {SHADOW};
    border-top-color: {HILITE};
    border-left-color: {HILITE};
    border-right-color: {SHADOW};
    border-bottom-color: {SHADOW};
    border-radius: 1px;
    padding: 4px 10px;
    font-family: Arial, Helvetica, sans-serif;
    font-weight: bold;
}}
QPushButton:hover {{
    color: #000000;
    border-top-color: {ACCENT2};
    border-left-color: {ACCENT2};
}}
QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #4f586a, stop:1 #222838);
    color: {ACCENT2};
    border-top-color: {SHADOW};
    border-left-color: {SHADOW};
    border-right-color: {HILITE};
    border-bottom-color: {HILITE};
}}
QPushButton[class="accent"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #fff4a8, stop:0.48 {ACCENT2}, stop:1 #8d7515);
    color: #050608;
    border-color: {SHADOW};
}}
QPushButton[class="accent"]:hover {{
    background: #fff172;
    border-color: {ACCENT};
}}
QPushButton:disabled {{
    background: #2a2f3d;
    color: #6f7786;
    border-color: #1b1f2a;
}}

/* Input fields */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {BLACK_WELL};
    color: {TEXT};
    border: 1px solid {SHADOW};
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    border-radius: 1px;
    padding: 4px 6px;
    selection-background-color: {ACCENT2};
    selection-color: #050608;
    font-family: Consolas, "Fira Code", monospace;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT2};
    background: #000000;
}}
QLineEdit:read-only, QTextEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {{
    color: {MUTED};
    background: #050608;
}}

/* Combo box */
QComboBox {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #dce6f2, stop:0.5 #687486, stop:1 #c8d2df);
    color: #10131b;
    border: 1px solid {SHADOW};
    border-top-color: {HILITE};
    border-left-color: {HILITE};
    border-radius: 1px;
    padding: 3px 8px;
    min-width: 120px;
    font-weight: bold;
}}
QComboBox:hover {{
    border-color: {ACCENT2};
}}
QComboBox::drop-down {{
    border-left: 1px solid {SHADOW};
    background: #4a5366;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {ACCENT};
    width: 0;
    height: 0;
}}
QComboBox QAbstractItemView {{
    background: {BLACK_WELL};
    color: {TEXT};
    border: 1px solid {ACCENT2};
    selection-background-color: {ACCENT2};
    selection-color: #050608;
    outline: none;
}}

/* Tree / List views */
QTreeWidget, QListWidget, QTreeView, QListView {{
    background: {BLACK_WELL};
    color: {TEXT};
    border: 1px solid {SHADOW};
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    border-radius: 1px;
    alternate-background-color: #071007;
    show-decoration-selected: 1;
    outline: none;
}}
QTreeWidget::item, QListWidget::item {{
    padding: 2px 4px;
    border: none;
}}
QTreeWidget::item:hover, QListWidget::item:hover {{
    background: #172214;
    color: #9dff9d;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {ACCENT2};
    color: #050608;
}}
QTreeWidget::branch {{
    background: {BLACK_WELL};
}}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {{
    border-image: none;
    color: {ACCENT2};
}}
QHeaderView::section {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #dce6f2, stop:0.42 #747f92, stop:1 #303747);
    color: #050608;
    border: 1px solid {SHADOW};
    border-top-color: {HILITE};
    border-left-color: {HILITE};
    padding: 3px 8px;
    font-weight: bold;
}}

/* Scroll bars */
QScrollBar:vertical {{
    background: {PANEL};
    width: 11px;
    border: 1px solid {SHADOW};
}}
QScrollBar::handle:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #dce6f2, stop:0.5 #6a7486, stop:1 #252b38);
    border: 1px solid {SHADOW};
    min-height: 18px;
    border-radius: 1px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT2};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}
QScrollBar:horizontal {{
    background: {PANEL};
    height: 11px;
    border: 1px solid {SHADOW};
}}
QScrollBar::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #dce6f2, stop:0.5 #6a7486, stop:1 #252b38);
    border: 1px solid {SHADOW};
    min-width: 18px;
    border-radius: 1px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT2};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    background: none;
}}

/* Tab bar */
QTabWidget::pane {{
    border: 1px solid {SHADOW};
    border-top-color: {BORDER};
    border-left-color: {BORDER};
    background: {PANEL};
}}
QTabBar {{
    icon-size: 18px;
}}
QTabBar::tab {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #4a5368, stop:1 #171b28);
    color: {MUTED};
    border: 1px solid {SHADOW};
    border-top-color: {BORDER};
    border-left-color: {BORDER};
    padding: 4px 12px;
    margin-right: 1px;
    border-radius: 1px;
}}
QTabBar::tab:selected {{
    background: {BLACK_WELL};
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT2};
}}
QTabBar::tab:hover:!selected {{
    color: {ACCENT2};
}}

/* Menu bar */
QMenuBar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #151b33, stop:0.5 #4b5f95, stop:1 #111522);
    color: #f5f2c8;
    border-bottom: 2px solid {ACCENT2};
    padding: 1px;
}}
QMenuBar::item {{
    padding: 3px 9px;
    border-radius: 1px;
}}
QMenuBar::item:selected {{
    background: {BLACK_WELL};
    color: {ACCENT};
}}
QMenuBar::item:pressed {{
    background: {ACCENT2};
    color: #050608;
}}
QMenu {{
    background: {BLACK_WELL};
    color: {TEXT};
    border: 1px solid {ACCENT2};
    padding: 3px 0;
}}
QMenu::item {{
    padding: 4px 20px;
}}
QMenu::item:selected {{
    background: {ACCENT2};
    color: #050608;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 3px 0;
}}

/* Status bar */
QStatusBar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #111522, stop:0.5 #313a54, stop:1 #111522);
    color: {MUTED};
    border-top: 1px solid {BORDER};
    font-size: 10px;
    padding: 2px 8px;
}}
QStatusBar::item {{
    border: none;
}}

/* Tool tips */
QToolTip {{
    background: {BLACK_WELL};
    color: {ACCENT};
    border: 1px solid {ACCENT2};
    padding: 4px 8px;
    border-radius: 1px;
}}

/* Progress bar */
QProgressBar {{
    background: {BLACK_WELL};
    border: 1px solid {SHADOW};
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    border-radius: 1px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:0.55 {ACCENT2}, stop:1 #b88e13);
    border-radius: 1px;
}}

/* Sliders */
QSlider::groove:horizontal {{
    background: {BLACK_WELL};
    border: 1px solid {SHADOW};
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    height: 5px;
    border-radius: 1px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT2};
    border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #fff3a3, stop:0.45 {ACCENT2}, stop:1 #806713);
    border: 1px solid {SHADOW};
    width: 12px;
    margin: -5px 0;
    border-radius: 1px;
}}
QSlider::groove:vertical {{
    background: {BLACK_WELL};
    border: 1px solid {SHADOW};
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    width: 5px;
    border-radius: 1px;
}}
QSlider::sub-page:vertical {{
    background: {ACCENT2};
    border-radius: 1px;
}}
QSlider::handle:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #fff3a3, stop:0.45 {ACCENT2}, stop:1 #806713);
    border: 1px solid {SHADOW};
    height: 10px;
    margin: 0 -5px;
    border-radius: 1px;
}}

/* Check / Radio */
QCheckBox, QRadioButton {{
    color: {TEXT};
    spacing: 5px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 12px;
    height: 12px;
    border: 1px solid {SHADOW};
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    background: {BLACK_WELL};
    border-radius: 1px;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT2};
}}
QRadioButton::indicator {{
    border-radius: 6px;
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT2};
}}

/* Group box */
QGroupBox {{
    border: 1px solid {SHADOW};
    border-top-color: {BORDER};
    border-left-color: {BORDER};
    border-radius: 1px;
    margin-top: 1.4em;
    padding: 8px 6px 6px 6px;
    color: {ACCENT2};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 8px;
    background: {PANEL};
}}

/* Spin box */
QSpinBox, QDoubleSpinBox {{
    background: {BLACK_WELL};
    color: {TEXT};
    border: 1px solid {SHADOW};
    border-top-color: #000000;
    border-left-color: #000000;
    border-right-color: {BORDER};
    border-bottom-color: {BORDER};
    border-radius: 1px;
    padding: 3px 6px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT2};
}}
"""
