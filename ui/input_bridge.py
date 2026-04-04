"""
Input bridge — adapts Qt dialogs to the Config.input_provider interface.

The CLI uses input() via prompt_input().  In the UI we replace that callable
with qt_input_provider() so any command handler that calls
config.input_provider("prompt text") gets a proper QInputDialog instead of
blocking the event loop with a terminal prompt.

Usage (in ui_main.py, before register_all_commands()):
    from ui.input_bridge import qt_input_provider
    config.input_provider = qt_input_provider
"""

from __future__ import annotations

from typing import Optional

# Lazy Qt import — bridge module is imported before QApplication exists
try:
    from PyQt5.QtWidgets import QInputDialog, QLineEdit, QApplication
    _QT = "PyQt5"
except ImportError:
    try:
        from PySide6.QtWidgets import QInputDialog, QLineEdit, QApplication  # type: ignore
        _QT = "PySide6"
    except ImportError:
        _QT = None  # type: ignore


# Sentinel returned when the user cancels a dialog
CANCELLED = "\x00CANCELLED\x00"


def qt_input_provider(prompt: str, *, password: bool = False) -> str:
    """
    Show a QInputDialog and return the entered text.

    Signature matches Config.input_provider: (prompt: str) -> str

    Returns:
        The text the user entered, or CANCELLED if they pressed Cancel/Escape.
    """
    if _QT is None:
        # Graceful fallback — should never reach production, but keeps tests sane
        return input(prompt)

    parent = None
    if QApplication.instance():
        # Grab the active top-level window as parent for proper centering
        top = QApplication.activeWindow()
        parent = top if top is not None else None

    echo = QLineEdit.EchoMode.Password if password else QLineEdit.EchoMode.Normal  # type: ignore[attr-defined]

    text, ok = QInputDialog.getText(
        parent,
        "GM Assistant",  # dialog title
        prompt,
        echo,
    )

    if ok:
        return text
    return CANCELLED


def is_cancelled(value: str) -> bool:
    """Return True if the input_provider result signals a user cancellation."""
    return value == CANCELLED
