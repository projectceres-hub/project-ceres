# GUI Launch Notes

Project Ceres is intended to launch from the repository root with:

```powershell
python ui_main.py
```

`ui_main.py` checks for `.venv\Scripts\python.exe` before importing the GUI
stack. If the shell `python` points at another interpreter, the launcher
prints a short handoff message and restarts itself inside the project virtual
environment. This keeps the documented command working even when Windows has a
different global Python earlier on `PATH`.

Expected terminal output is brief:

```text
GM Assistant switching to project venv: C:\Project Ceres\.venv\Scripts\python.exe
GM Assistant starting - logs at C:\Project Ceres\logs\ui.log
GM Assistant window shown - logs at C:\Project Ceres\logs\ui.log
```

The first line only appears when a handoff is needed.

## Diagnostics

The GUI still redirects stdout and stderr to `logs/ui.log` after startup so
Qt, Chromium, pygame, and panel output do not flood the terminal. The launcher
also writes ordered startup checkpoints to that log:

- Qt binding selection
- `QApplication` creation and available screens
- backend initialization
- command registration
- `MainWindow` construction
- window visibility, geometry, and event-loop entry

If startup fails before the window appears, the full traceback is written to
`logs/ui.log` and mirrored to the real terminal stderr.

## Window Visibility

The main window restores saved Qt geometry from `QSettings`. If the saved
geometry is empty, minimized, or no longer intersects an available screen, the
window falls back to a centered default size. This protects against monitor
layout changes making the app look like it launched without a window.

## Verification

For launcher changes, run:

```powershell
.venv\Scripts\python.exe -m compileall -q assistant.py ui_main.py core pantheon automation pdf_tools ui
.venv\Scripts\python.exe tools\scripts\smoke_gui_constructor.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
python ui_main.py
```

For the final manual launch, confirm `logs/ui.log` reaches `window shown` and
`event loop entered`.
