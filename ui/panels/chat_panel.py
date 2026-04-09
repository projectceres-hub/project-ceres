"""
ui/panels/chat_panel.py — Project Ceres
========================================
Conversational GM Assistant — the primary UI surface.

Users type plain English; the ChatAgent (GPT-4o) interprets intent,
gives a friendly reply, and optionally dispatches a Pantheon command.
Command output is fed back to the agent so it can summarise results.

Power users can still run raw commands by prefixing with  /  or  >:
    > search goblin king
    /spotify-play tavern music

Layout::

    ┌────────────────────────────────────────────────────┐
    │  ⚔  Ceres                  What are we doing?     │  ← header
    ├────────────────────────────────────────────────────┤
    │                                                    │
    │   ┌─────────────────────────────────────────────┐  │
    │   │ ⚔  Vault loaded: "The Shattered Realms"...  │  │  ← assistant bubble
    │   └─────────────────────────────────────────────┘  │
    │                                                    │
    │                   ┌────────────────────────────┐   │
    │                   │  play some battle music     │   │  ← user bubble
    │                   └────────────────────────────┘   │
    │                                                    │
    │   ┌─────────────────────────────────────────────┐  │
    │   │ ⚔  On it! Searching Spotify for battle...   │  │
    │   └─────────────────────────────────────────────┘  │
    │        ── dispatched: spotify-play battle music ──  │  ← action note
    │                                                    │
    ├────────────────────────────────────────────────────┤
    │  Ask Ceres anything…                    [ Send ⟶ ] │  ← input bar
    └────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import io
import contextlib
import random
from typing import Callable, Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QScrollArea, QFrame, QLineEdit, QPushButton,
        QSizePolicy,
    )
    from PyQt5.QtCore import Qt, QThread, QObject, pyqtSignal as Signal, pyqtSlot as Slot, QTimer
    from PyQt5.QtGui import QFont
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QScrollArea, QFrame, QLineEdit, QPushButton,
        QSizePolicy,
    )
    from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot, QTimer  # type: ignore
    from PySide6.QtGui import QFont  # type: ignore

from ui.theme import ACCENT, BG, PANEL, SURFACE, TEXT, MUTED, BORDER, SUCCESS
from pantheon.convector.chat_agent import ChatAgent, ChatResponse


# ─────────────────────────────────────────────────────────────────────────────
# Background worker — runs ChatAgent.process() off the Qt main thread
# ─────────────────────────────────────────────────────────────────────────────

class _ChatWorker(QObject):
    """Runs ChatAgent.process() in a QThread so the UI stays responsive."""

    response_ready = Signal(object)   # emits ChatResponse
    finished       = Signal()

    def __init__(self, agent: ChatAgent, message: str, extra: str) -> None:
        super().__init__()
        self._agent   = agent
        self._message = message
        self._extra   = extra

    @Slot()
    def run(self) -> None:
        try:
            resp = self._agent.process(self._message, self._extra)
        except Exception as exc:  # safety net — agent already catches most things
            resp = ChatResponse(
                reply="Something went wrong. Check variables.env for your API key.",
                error=str(exc),
            )
        self.response_ready.emit(resp)
        self.finished.emit()


# ─────────────────────────────────────────────────────────────────────────────
# Message bubble widget
# ─────────────────────────────────────────────────────────────────────────────

class _Bubble(QFrame):
    """
    A single message bubble.

    role:
        'user'      — right-aligned, surface background
        'assistant' — left-aligned, panel background with accent left-border
        'action'    — centred, small italic note (command dispatch / result)
    """

    def __init__(self, role: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(f"Bubble_{role}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(0)

        if role == 'action':
            self._full_text = text
            self._expanded  = False

            # Short content: just show it. Long content: collapse + toggle.
            _PREVIEW = 200
            is_long  = len(text) > _PREVIEW

            self._lbl = QLabel(text[:_PREVIEW] + ("…" if is_long else ""))
            self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._lbl.setWordWrap(True)
            self._lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._lbl.setStyleSheet(
                f"color: {MUTED}; font-size: 9px; font-style: italic;"
                f"padding: 1px 16px; background: transparent; border: none;"
            )
            layout.addWidget(self._lbl)

            if is_long:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 2)
                row.addStretch()

                self._toggle_btn = QPushButton("▼  show more")
                self._toggle_btn.setFlat(True)
                self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self._toggle_btn.setStyleSheet(
                    f"QPushButton {{ color: {ACCENT}; font-size: 9px; background: transparent;"
                    f"  border: none; padding: 0 16px; }}"
                    f"QPushButton:hover {{ color: white; }}"
                )
                self._toggle_btn.clicked.connect(self._toggle_expand)
                row.addWidget(self._toggle_btn)
                row.addStretch()
                layout.addLayout(row)
            return

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        if role == 'user':
            row.addStretch()
            row.addWidget(self._make_bubble(text, is_user=True))
        else:
            avatar = QLabel("⚔")
            avatar.setFixedSize(26, 26)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setStyleSheet(
                f"color: {ACCENT}; font-size: 12px;"
                f"background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 13px;"
                f"padding: 0;"
            )
            row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(self._make_bubble(text, is_user=False))
            row.addStretch()

        layout.addLayout(row)

    def _toggle_expand(self) -> None:
        """Toggle between collapsed preview and full action text."""
        _PREVIEW = 200
        self._expanded = not self._expanded
        if self._expanded:
            self._lbl.setText(self._full_text)
            self._toggle_btn.setText("▲  show less")
        else:
            self._lbl.setText(self._full_text[:_PREVIEW] + "…")
            self._toggle_btn.setText("▼  show more")

    @staticmethod
    def _make_bubble(text: str, is_user: bool) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setMaximumWidth(620)
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        if is_user:
            lbl.setStyleSheet(
                f"background: {SURFACE}; color: {TEXT};"
                f"border: 1px solid {BORDER}; border-radius: 8px 8px 2px 8px;"
                f"padding: 8px 14px; font-size: 11px; font-family: sans-serif;"
            )
        else:
            lbl.setStyleSheet(
                f"background: {PANEL}; color: {TEXT};"
                f"border: 1px solid {BORDER}; border-left: 2px solid {ACCENT};"
                f"border-radius: 8px 8px 8px 2px;"
                f"padding: 8px 14px; font-size: 11px; font-family: sans-serif;"
            )
        return lbl


# ─────────────────────────────────────────────────────────────────────────────
# Animated typing indicator
# ─────────────────────────────────────────────────────────────────────────────

class _TypingDots(QLabel):
    """Animated '⚔ Ceres is thinking…' shown while the agent processes."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dots = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setStyleSheet(
            f"color: {MUTED}; font-size: 10px; font-style: italic;"
            f"padding: 4px 40px; background: transparent;"
        )
        self.hide()

    def start(self) -> None:
        self._dots = 0
        self.show()
        self._timer.start(450)

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        dots = "." * (self._dots % 4)
        self.setText(f"⚔  Ceres is thinking{dots}")
        self._dots += 1


# ─────────────────────────────────────────────────────────────────────────────
# Main ChatPanel widget
# ─────────────────────────────────────────────────────────────────────────────

class ChatPanel(QWidget):
    """
    Primary conversational interface for the GM Assistant.

    Accepts natural-language input and converts it to friendly replies
    and Pantheon command dispatches via GPT-4o.  Also accepts raw
    commands prefixed with  /  or  >  for power-user access.

    Args:
        config:      Fully-initialised Config dataclass.
        run_command: assistant.run_command(cmd, args, config) callable.
        parent:      Optional parent widget.

    Signals:
        status_message(str): Emitted to update the main window status bar.
    """

    status_message  = Signal(str)
    request_console = Signal(str)   # emitted with full text when output is very long

    _GREETINGS = [
        "What are we working on today?",
        "Ready when you are. What do you need?",
        "The session table is set. How can I help?",
        "Your assistant is standing by. What's the plan?",
        "Good to see you. What are we doing today?",
        "Roll for initiative — what do you need from me?",
    ]

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config      = config
        self._run_command = run_command
        self._agent       = ChatAgent(config)
        self._busy        = False
        self._thread: Optional[QThread]      = None
        self._worker: Optional[_ChatWorker]  = None

        self.setObjectName("ChatPanel")
        self._build_ui()
        self._post_welcome()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("ChatHeader")
        header.setFixedHeight(64)
        header.setStyleSheet(
            f"QFrame#ChatHeader {{"
            f"  background: {SURFACE};"
            f"  border-bottom: 2px solid {ACCENT};"
            f"}}"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(20, 10, 20, 10)
        hlay.setSpacing(14)

        icon = QLabel("⚔")
        icon.setStyleSheet(
            f"color: {ACCENT}; font-size: 22px; background: transparent; border: none;"
        )
        hlay.addWidget(icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("Ceres")
        title.setStyleSheet(
            f"color: {ACCENT}; font-size: 16px; font-weight: bold;"
            f"font-family: Georgia, 'Times New Roman', serif;"
            f"background: transparent; border: none;"
        )
        title_col.addWidget(title)

        self._subtitle = QLabel(random.choice(self._GREETINGS))
        self._subtitle.setStyleSheet(
            f"color: {MUTED}; font-size: 10px; background: transparent; border: none;"
        )
        title_col.addWidget(self._subtitle)

        hlay.addLayout(title_col)
        hlay.addStretch()

        # Clear history button
        clear_btn = QPushButton("↺  New session")
        clear_btn.setFixedHeight(28)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {MUTED};"
            f"  border: 1px solid {BORDER}; border-radius: 4px; font-size: 9px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ color: {TEXT}; border-color: {ACCENT}; }}"
        )
        clear_btn.setToolTip("Clear conversation history")
        clear_btn.clicked.connect(self._on_clear)
        hlay.addWidget(clear_btn)

        root.addWidget(header)

        # ── Message history (scrollable) ──────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {BG}; border: none; }}"
            f"QScrollBar:vertical {{ background: {BG}; width: 8px; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

        self._msg_widget = QWidget()
        self._msg_widget.setObjectName("MsgContainer")
        self._msg_widget.setStyleSheet(f"QWidget#MsgContainer {{ background: {BG}; }}")
        self._msg_layout = QVBoxLayout(self._msg_widget)
        self._msg_layout.setContentsMargins(16, 16, 16, 16)
        self._msg_layout.setSpacing(8)
        self._msg_layout.addStretch()   # push messages down from top initially

        self._scroll.setWidget(self._msg_widget)
        root.addWidget(self._scroll, 1)

        # ── Typing indicator ──────────────────────────────────────────────────
        self._typing = _TypingDots()
        root.addWidget(self._typing)

        # ── Input bar ─────────────────────────────────────────────────────────
        bar = QFrame()
        bar.setObjectName("ChatBar")
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            f"QFrame#ChatBar {{"
            f"  background: {PANEL};"
            f"  border-top: 1px solid {BORDER};"
            f"}}"
        )
        blay = QHBoxLayout(bar)
        blay.setContentsMargins(12, 10, 12, 10)
        blay.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Ask Ceres anything…  (prefix with / for raw commands, e.g. /search goblin king)"
        )
        self._input.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {SURFACE}; color: {TEXT};"
            f"  border: 1px solid {BORDER}; border-radius: 4px;"
            f"  padding: 6px 12px; font-size: 11px; font-family: sans-serif;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
            f"QLineEdit:disabled {{ background: {BG}; color: {MUTED}; }}"
        )
        self._input.returnPressed.connect(self._on_send)
        blay.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send ⟶")
        self._send_btn.setFixedSize(72, 36)
        self._send_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {ACCENT}; color: white;"
            f"  border: none; border-radius: 4px;"
            f"  font-size: 11px; font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{ background: #ff6b7a; }}"
            f"QPushButton:pressed {{ background: #c73050; }}"
            f"QPushButton:disabled {{ background: {BORDER}; color: {MUTED}; }}"
        )
        self._send_btn.clicked.connect(self._on_send)
        blay.addWidget(self._send_btn)

        root.addWidget(bar)

    # ── Message helpers ───────────────────────────────────────────────────────

    def _add_bubble(self, role: str, text: str) -> None:
        """Insert a message bubble before the trailing stretch."""
        bubble = _Bubble(role, text)
        count  = self._msg_layout.count()
        self._msg_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(40, self._scroll_bottom)

    def _scroll_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _post_welcome(self) -> None:
        """Add the initial greeting from Ceres when the panel loads."""
        vault = getattr(self._config, "current_vault", None) or "no vault selected"
        self._add_bubble(
            "assistant",
            f"Vault loaded: {vault}\n\n"
            "You can ask me anything in plain English — search your notes, play music, "
            "start recording, post to Discord, or just ask about your campaign. "
            "I'll handle the details.",
        )

    # ── Send / dispatch logic ─────────────────────────────────────────────────

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text or self._busy:
            return
        self._input.clear()

        self._add_bubble("user", text)

        # Raw command passthrough (/ or > prefix)
        if text.startswith("/") or text.startswith(">"):
            raw   = text.lstrip("/>").strip()
            parts = raw.split(None, 1)
            cmd   = parts[0] if parts else ""
            args  = parts[1] if len(parts) > 1 else ""
            if cmd:
                self._exec_raw(cmd, args)
            return

        # Natural-language → agent
        self._dispatch(text)

    def _dispatch(self, message: str, extra: str = "") -> None:
        """Send message to ChatAgent in a background thread."""
        self._set_busy(True)
        self._typing.start()
        self.status_message.emit("Ceres is thinking…")

        worker = _ChatWorker(self._agent, message, extra)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.response_ready.connect(self._on_response)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._set_busy(False))

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_response(self, resp: ChatResponse) -> None:
        """Handle ChatAgent reply — show bubble, optionally run command."""
        self._typing.stop()

        if resp.error and not resp.reply:
            self._add_bubble("action", f"⚠  {resp.error}")
            self.status_message.emit("Ceres: error")
            return

        self._add_bubble("assistant", resp.reply)

        if resp.command:
            label = resp.action_label or resp.command
            self._add_bubble("action", f"↳  {label}")
            self.status_message.emit(f"Ceres: running {resp.command}…")
            # Slight delay so the bubble renders before blocking on the command
            QTimer.singleShot(80, lambda: self._exec_command(resp))
        else:
            self.status_message.emit("Ceres: ready")

    def _exec_command(self, resp: ChatResponse) -> None:
        """
        Run the command the agent chose; feed output back for context.

        Many Pantheon commands return None and print results to stdout.
        We capture stdout so that output is never silently lost.

        Output display tiers:
            < 200 chars  → inline action note (shown in full)
            200–800 chars → expandable action note (▼ show more / ▲ show less)
            > 800 chars   → truncated action note + "view full output →" console link
        """
        stdout_buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buf):
                result = self._run_command(resp.command, resp.args or "", self._config)
        except Exception as exc:
            self._add_bubble("action", f"⚠  Command error: {exc}")
            self.status_message.emit(f"Ceres: {resp.command} failed")
            return

        # Prefer the return value; fall back to captured stdout
        if result is not None:
            result_str = str(result).strip()
        else:
            result_str = stdout_buf.getvalue().strip()

        if result_str:
            self._agent.inject_result(resp.command, result_str)

            if len(result_str) > 800:
                preview = result_str[:400] + "…"
                self._add_bubble("action", f"✓  {preview}")
                self._add_console_link(resp.command, result_str)
            else:
                self._add_bubble("action", f"✓  {result_str}")
        else:
            # Command ran but produced no output — let the agent know it succeeded
            self._agent.inject_result(resp.command, "Command completed successfully (no output).")
            self._add_bubble("action", f"✓  {resp.command} completed")

        self.status_message.emit("Ceres: done")

    def _exec_raw(self, cmd: str, args: str) -> None:
        """Bypass the agent — run a raw /command directly."""
        self.status_message.emit(f"Running: {cmd} {args}".strip())
        stdout_buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buf):
                result = self._run_command(cmd, args, self._config)
            if result is not None:
                out = str(result).strip()
            else:
                out = stdout_buf.getvalue().strip() or f"✓  {cmd} executed"
            self._add_bubble("action", out[:500])
        except Exception as exc:
            self._add_bubble("action", f"⚠  {exc}")
        self.status_message.emit("Ready")

    def _add_console_link(self, command: str, full_text: str) -> None:
        """
        Insert a centred action note with a clickable 'view full output →' button.

        When clicked the button emits request_console(full_text), which
        main_window wires to show the console panel and populate it.

        Args:
            command:   The command whose output is being displayed.
            full_text: The complete output string to hand to the console.
        """
        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 4)
        row.addStretch()

        lbl = QLabel(f"── {command} output truncated ──")
        lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 9px; font-style: italic; background: transparent; border: none;"
        )
        row.addWidget(lbl)

        btn = QPushButton("view full output →")
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color: {ACCENT}; font-size: 9px; background: transparent;"
            f"  border: none; padding: 0 6px; }}"
            f"QPushButton:hover {{ color: white; }}"
        )
        # Capture full_text in the closure
        btn.clicked.connect(lambda _checked=False, t=full_text: self.request_console.emit(t))
        row.addWidget(btn)
        row.addStretch()

        count = self._msg_layout.count()
        self._msg_layout.insertWidget(count - 1, container)
        QTimer.singleShot(40, self._scroll_bottom)

    # ── Helper slots ──────────────────────────────────────────────────────────

    def _on_clear(self) -> None:
        """Clear conversation history and reset the view."""
        self._agent.clear_history()
        # Remove all bubbles (leave the trailing stretch)
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._subtitle.setText(random.choice(self._GREETINGS))
        self._post_welcome()
        self.status_message.emit("Ceres: history cleared")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        if not busy:
            self._typing.stop()
            self._input.setFocus()

    # ── Public shims (backward compat with console_panel callers) ─────────────

    def print_output(self, text: str, color: str = TEXT) -> None:
        """Drop-in shim — lets other panels post status messages to chat."""
        self._add_bubble("action", text)

    def print_success(self, text: str) -> None:
        self._add_bubble("action", f"✓  {text}")

    def print_error(self, text: str) -> None:
        self._add_bubble("action", f"⚠  {text}")
