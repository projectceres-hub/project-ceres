"""
Dark game theme for Project Ceres — GM Assistant UI.

Color palette:
    BG         #1a1a2e  — deep navy background
    PANEL      #16213e  — slightly lighter panel surfaces
    SURFACE    #0f3460  — raised element / header surfaces
    ACCENT     #e94560  — primary accent (crimson-red)
    ACCENT2    #533483  — secondary accent (purple)
    TEXT       #eaeaea  — primary text
    MUTED      #8892a4  — secondary/muted text
    BORDER     #2a2a4a  — panel borders
    SUCCESS    #2ecc71  — positive states
    WARNING    #f39c12  — warning states
    ERROR      #e74c3c  — error states

Font stack: "Consolas", "Fira Code", "Courier New", monospace
"""

# ── Palette constants ──────────────────────────────────────────────────────────
BG        = "#1a1a2e"
PANEL     = "#16213e"
SURFACE   = "#0f3460"
ACCENT    = "#e94560"
ACCENT2   = "#533483"
TEXT      = "#eaeaea"
MUTED     = "#8892a4"
BORDER    = "#2a2a4a"
SUCCESS   = "#2ecc71"
WARNING   = "#f39c12"
ERROR     = "#e74c3c"

FONT_MONO = "Consolas, 'Fira Code', 'Courier New', monospace"
FONT_SIZE  = 11  # px

# ── Global QSS stylesheet ──────────────────────────────────────────────────────
STYLESHEET = f"""
/* ── Base ── */
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: Consolas, "Fira Code", "Courier New", monospace;
    font-size: {FONT_SIZE}px;
}}

/* ── Dock panels ── */
QDockWidget {{
    color: {TEXT};
    font-weight: bold;
    font-size: 12px;
    border: 1px solid {BORDER};
}}
QDockWidget::title {{
    background: {SURFACE};
    padding: 6px 10px;
    border-bottom: 2px solid {ACCENT};
    text-align: left;
}}
QDockWidget::close-button, QDockWidget::float-button {{
    border: none;
    background: transparent;
    padding: 2px;
}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background: {BORDER};
    width: 2px;
    height: 2px;
}}

/* ── Labels ── */
QLabel {{
    color: {TEXT};
    padding: 1px;
}}
QLabel[class="section-header"] {{
    color: {ACCENT};
    font-weight: bold;
    font-size: 13px;
    padding: 4px 0px;
    border-bottom: 1px solid {ACCENT2};
}}
QLabel[class="muted"] {{
    color: {MUTED};
    font-size: 10px;
}}

/* ── Buttons ── */
QPushButton {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 12px;
    font-family: Consolas, "Fira Code", monospace;
}}
QPushButton:hover {{
    background: {ACCENT2};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: {ACCENT};
    color: white;
}}
QPushButton[class="accent"] {{
    background: {ACCENT};
    color: white;
    border-color: {ACCENT};
    font-weight: bold;
}}
QPushButton[class="accent"]:hover {{
    background: #ff6b7a;
    border-color: #ff6b7a;
}}
QPushButton:disabled {{
    background: {BORDER};
    color: {MUTED};
    border-color: {BORDER};
}}

/* ── Input fields ── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: {ACCENT};
    selection-color: white;
    font-family: Consolas, "Fira Code", monospace;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
    background: {SURFACE};
}}
QLineEdit:read-only, QTextEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {{
    color: {MUTED};
    background: {BG};
}}

/* ── Combo box ── */
QComboBox {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 4px 8px;
    min-width: 120px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    background: {SURFACE};
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {TEXT};
    width: 0;
    height: 0;
}}
QComboBox QAbstractItemView {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {ACCENT};
    selection-background-color: {ACCENT};
    selection-color: white;
    outline: none;
}}

/* ── Tree / List views ── */
QTreeWidget, QListWidget, QTreeView, QListView {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    alternate-background-color: {BG};
    show-decoration-selected: 1;
    outline: none;
}}
QTreeWidget::item, QListWidget::item {{
    padding: 3px 4px;
    border: none;
}}
QTreeWidget::item:hover, QListWidget::item:hover {{
    background: {SURFACE};
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {ACCENT};
    color: white;
}}
QTreeWidget::branch {{
    background: {PANEL};
}}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {{
    border-image: none;
    color: {ACCENT};
}}
QHeaderView::section {{
    background: {SURFACE};
    color: {ACCENT};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT};
    padding: 4px 8px;
    font-weight: bold;
}}

/* ── Scroll bars ── */
QScrollBar:vertical {{
    background: {BG};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {SURFACE};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT2};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}
QScrollBar:horizontal {{
    background: {BG};
    height: 10px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {SURFACE};
    border-radius: 5px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT2};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    background: none;
}}

/* ── Tab bar ── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {PANEL};
}}
QTabBar {{
    icon-size: 20px;
}}
QTabBar::tab {{
    background: {BG};
    color: {MUTED};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 5px 14px;
    margin-right: 2px;
    border-radius: 3px 3px 0 0;
}}
QTabBar::tab:selected {{
    background: {PANEL};
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {SURFACE};
    color: {TEXT};
}}

/* ── Menu bar ── */
QMenuBar {{
    background: {SURFACE};
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
    padding: 2px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 3px;
}}
QMenuBar::item:selected {{
    background: {ACCENT2};
}}
QMenuBar::item:pressed {{
    background: {ACCENT};
}}
QMenu {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {ACCENT};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 20px 5px 20px;
}}
QMenu::item:selected {{
    background: {ACCENT};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 3px 0;
}}

/* ── Status bar ── */
QStatusBar {{
    background: {SURFACE};
    color: {MUTED};
    border-top: 1px solid {BORDER};
    font-size: 10px;
    padding: 2px 8px;
}}
QStatusBar::item {{
    border: none;
}}

/* ── Tool tips ── */
QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {ACCENT};
    padding: 4px 8px;
    border-radius: 3px;
}}

/* ── Progress bar ── */
QProgressBar {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* ── Check / Radio ── */
QCheckBox, QRadioButton {{
    color: {TEXT};
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    background: {PANEL};
    border-radius: 2px;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QRadioButton::indicator {{
    border-radius: 7px;
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Group box ── */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 5px;
    margin-top: 1.5em;
    padding: 8px 6px 6px 6px;
    color: {ACCENT};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
}}

/* ── Spin box ── */
QSpinBox, QDoubleSpinBox {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 6px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}
"""
