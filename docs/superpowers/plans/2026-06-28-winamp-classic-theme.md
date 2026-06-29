# Winamp Classic Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework Project Ceres' existing Qt theme into a much more literal Winamp classic skin.

**Architecture:** Keep the styling centralized in `ui/theme.py` and only touch panel-specific inline styles where they override the global look. Add a narrow regression test for palette and stylesheet markers, then verify with Python compile checks and the existing GUI constructor smoke.

**Tech Stack:** Python, PyQt5/PySide6-compatible QSS, unittest, existing Project Ceres GUI smoke script.

---

## File Structure

- Modify `ui/theme.py`: replace the current dark game palette and global QSS with Winamp-classic colors, bevels, sliders, menus, tabs, scrollbars, lists, and controls.
- Modify `ui/panels/chat_panel.py`: remove the old rounded crimson chat look from the highest-visibility chat header/input/bubble controls.
- Modify `ui/panels/mixer_panel.py`: make mixer rows, sliders, and mute buttons match the metal/LCD theme.
- Modify `ui/panels/equalizer_panel.py`: make the EQ frame and labels closer to the reference equalizer.
- Create `tests/test_winamp_theme.py`: regression tests for palette constants and QSS markers.

### Task 1: Theme Regression Test

**Files:**
- Create: `tests/test_winamp_theme.py`

- [ ] **Step 1: Write the failing test**

```python
from ui import theme


def test_winamp_palette_exports_reference_colors():
    assert theme.BG == "#050608"
    assert theme.PANEL == "#11131b"
    assert theme.SURFACE == "#2f3548"
    assert theme.ACCENT == "#00ff3c"
    assert theme.ACCENT2 == "#f3d94e"
    assert theme.TEXT == "#00ff3c"
    assert theme.MUTED == "#a8b0c2"
    assert theme.BORDER == "#697084"


def test_stylesheet_contains_winamp_chrome_markers():
    qss = theme.STYLESHEET
    assert "Winamp classic base" in qss
    assert "qlineargradient" in qss
    assert "QSlider::handle:horizontal" in qss
    assert "QDockWidget::title" in qss
    assert "border-radius: 1px" in qss
    assert "#f3d94e" in qss
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m unittest tests.test_winamp_theme`

Expected: fail because `tests.test_winamp_theme` is new and the current palette still uses `#1a1a2e`, `#e94560`, and rounded modern QSS markers.

### Task 2: Global Theme Implementation

**Files:**
- Modify: `ui/theme.py`
- Test: `tests/test_winamp_theme.py`

- [ ] **Step 1: Replace palette constants**

Set:

```python
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
```

- [ ] **Step 2: Replace global QSS**

Use a Winamp-classic stylesheet with:

- `/* Winamp classic base */` comment marker
- beveled `QDockWidget`, `QMenuBar`, `QPushButton`, input, and list borders
- `qlineargradient(...)` title/menu/button chrome
- green LCD text on dark wells
- yellow slider/progress chunks
- `border-radius: 1px` as the common shape

- [ ] **Step 3: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m unittest tests.test_winamp_theme`

Expected: `OK`.

### Task 3: Panel Override Pass

**Files:**
- Modify: `ui/panels/chat_panel.py`
- Modify: `ui/panels/mixer_panel.py`
- Modify: `ui/panels/equalizer_panel.py`

- [ ] **Step 1: Chat panel**

Change local styles so the header and bar use steel gradients, chat wells are black, bubbles use square beveled borders, assistant/action accents are green/yellow, and the send button uses gold chrome.

- [ ] **Step 2: Mixer panel**

Change row frames to beveled metal/black surfaces, horizontal slider handles to gold rectangular thumbs, and mute buttons to metal chrome with red only for muted state.

- [ ] **Step 3: Equalizer panel**

Change the EQ band frame to a black/metal framed well, make dB labels gold or green, and make the note/list text green-muted rather than old purple/crimson.

### Task 4: Verification

**Files:**
- Verify touched UI modules and GUI constructor.

- [ ] **Step 1: Compile touched UI files**

Run: `.venv\Scripts\python.exe -m py_compile ui\theme.py ui\panels\chat_panel.py ui\panels\mixer_panel.py ui\panels\equalizer_panel.py`

Expected: exit code 0.

- [ ] **Step 2: Run focused test**

Run: `.venv\Scripts\python.exe -m unittest tests.test_winamp_theme`

Expected: `OK`.

- [ ] **Step 3: Run GUI constructor smoke**

Run: `.venv\Scripts\python.exe tools\scripts\smoke_gui_constructor.py`

Expected: output includes `GUI constructor smoke OK.`
