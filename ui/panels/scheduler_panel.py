"""
Session Scheduler panel for Project Ceres — GM Assistant UI.

Lets the GM:
  1. Build a list of up to 4 candidate session dates with a calendar picker
  2. Post a role-gated emoji-reaction poll to a Discord text channel
  3. Watch live vote tallies as players react
  4. Confirm a winner and generate a Google Calendar link + .ics export
  5. Post the confirmed date back to Discord

Layout (3 tabs)
---------------
  📅 Setup  — title, campaign, duration, notes, date picker, candidate list
  📣 Poll   — channel selector, player role, preview, send, live vote bars
  ✅ Confirm — winner summary, Google Cal link, .ics export, Discord post

Signals / slots (wired by main_window.py to DiscordPanel)
---------------------------------------------------------
  Outbound:
    request_channels  Signal()           — ask Discord for its text-channel list
    send_poll_sig     Signal(int,list,str) — (channel_id, options, role_name)
    close_poll_sig    Signal()           — clear poll state in worker
  Inbound (slots):
    on_channels_available(list)          — [(ch_id_str, ch_name), ...]
    on_poll_sent(str)                    — message_id confirming post
    on_vote_updated(dict)               — {option_idx: vote_count}
    on_poll_error(str)                  — human-readable error
"""

from __future__ import annotations

import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QComboBox, QListWidget,
        QListWidgetItem, QSpinBox, QTextEdit, QTabWidget,
        QCalendarWidget, QTimeEdit, QProgressBar, QGroupBox,
        QSizePolicy, QMessageBox, QFileDialog,
    )
    from PyQt5.QtCore import Qt, QDate, QTime, QSettings, pyqtSignal as Signal
    from PyQt5.QtGui import QFont
except ImportError:
    from PySide6.QtWidgets import (   # type: ignore
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QComboBox, QListWidget,
        QListWidgetItem, QSpinBox, QTextEdit, QTabWidget,
        QCalendarWidget, QTimeEdit, QProgressBar, QGroupBox,
        QSizePolicy, QMessageBox, QFileDialog,
    )
    from PySide6.QtCore import Qt, QDate, QTime, QSettings, Signal  # type: ignore
    from PySide6.QtGui import QFont   # type: ignore

from ui.theme import (
    ACCENT, ACCENT2, MUTED, TEXT, PANEL, SURFACE, BORDER,
    SUCCESS, WARNING, ERROR,
)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_CANDIDATES   = 4
POLL_EMOJIS      = ("1️⃣", "2️⃣", "3️⃣", "4️⃣")
DEFAULT_DURATION = 4      # hours
GCAL_BASE        = "https://calendar.google.com/calendar/r/eventedit"

# ── Helpers ────────────────────────────────────────────────────────────────────


def _gcal_url(title: str, start: datetime, end: datetime, description: str = "") -> str:
    """Build a pre-filled Google Calendar event URL (no OAuth required)."""
    fmt = "%Y%m%dT%H%M%S"
    params = {
        "text":    title,
        "dates":   f"{start.strftime(fmt)}/{end.strftime(fmt)}",
        "details": description,
    }
    return GCAL_BASE + "?" + urllib.parse.urlencode(params)


def _strip_leading_zero(s: str) -> str:
    """Remove a leading zero from a day/hour string (cross-platform)."""
    return s.lstrip("0") or "0"


def _fmt_date(dt: datetime) -> str:
    """e.g. 'Sat, Apr 5'"""
    day = _strip_leading_zero(dt.strftime("%d"))
    return f"{dt.strftime('%a, %b')} {day}"


def _fmt_time(dt: datetime) -> str:
    """e.g. '7:00 PM'"""
    hour = _strip_leading_zero(dt.strftime("%I"))
    return f"{hour}{dt.strftime(':%M %p')}"


def _fmt_label(dt: datetime) -> str:
    """e.g. 'Sat Apr 5 · 7:00 PM'"""
    return f"{_fmt_date(dt)} · {_fmt_time(dt)}"


# ══════════════════════════════════════════════════════════════════════════════
#  SchedulerPanel
# ══════════════════════════════════════════════════════════════════════════════

class SchedulerPanel(QDockWidget):
    """
    Dockable Session Scheduler panel.

    Signals:
        status_message(msg)             — forwarded to main-window status bar
        request_channels()              — ask Discord panel for its text channels
        send_poll_sig(ch_id, opts, role)— instruct Discord panel to post a poll
        close_poll_sig()                — clear Discord panel's poll state
    """

    status_message:   Signal = Signal(str)
    request_channels: Signal = Signal()
    send_poll_sig:    Signal = Signal(int, list, str)
    close_poll_sig:   Signal = Signal()

    def __init__(
        self,
        config,
        run_command: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("📅  Scheduler", parent)
        self.setObjectName("SchedulerPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)   # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable    |      # type: ignore[attr-defined]
            QDockWidget.DockWidgetFeature.DockWidgetFloatable  |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._config = config
        self._run_command = run_command
        self._settings = QSettings("ProjectCeres", "GMAssistant")

        # State
        self._candidates: List[datetime] = []          # up to 4 datetimes
        self._text_channels: List[Tuple[str, str]] = []  # [(id, name), ...]
        self._votes: Dict[int, int] = {}               # {idx: count}
        self._winner: Optional[datetime] = None
        self._poll_active: bool = False

        self._build_ui()
        self._restore_state()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QWidget()
        root = QVBoxLayout(outer)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabBar::tab {{ color: {MUTED}; padding: 4px 10px; }}"
            f"QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}"
        )
        root.addWidget(self._tabs)

        self._tabs.addTab(self._build_setup_tab(),   "📅  Setup")
        self._tabs.addTab(self._build_poll_tab(),    "📣  Poll")
        self._tabs.addTab(self._build_confirm_tab(), "✅  Confirm")

        self.setWidget(outer)

    # ── Tab 0 — Setup ──────────────────────────────────────────────────────────

    def _build_setup_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # ── Session title ──
        lay.addWidget(self._section_label("Session Details"))
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("e.g. The Crimson Keep — Session 7")
        title_row.addWidget(self._title_edit)
        lay.addLayout(title_row)

        # ── Campaign ──
        camp_row = QHBoxLayout()
        camp_row.addWidget(QLabel("Campaign:"))
        self._campaign_combo = QComboBox()
        self._campaign_combo.setEditable(True)
        self._campaign_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._populate_campaigns()
        camp_row.addWidget(self._campaign_combo)
        lay.addLayout(camp_row)

        # ── Duration ──
        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Duration (hrs):"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 12)
        self._duration_spin.setValue(DEFAULT_DURATION)
        self._duration_spin.setFixedWidth(55)
        dur_row.addWidget(self._duration_spin)
        dur_row.addStretch()
        lay.addLayout(dur_row)

        # ── Notes ──
        lay.addWidget(self._section_label("Session Notes"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText(
            "Brief description, hooks, reminders for the invitation…"
        )
        self._notes_edit.setMaximumHeight(70)
        lay.addWidget(self._notes_edit)

        # ── Date picker ──
        lay.addWidget(self._section_label("Add Candidate Dates"))

        self._calendar = QCalendarWidget()
        self._calendar.setMinimumDate(QDate.currentDate())
        self._calendar.setMaximumHeight(200)
        self._calendar.setStyleSheet(
            f"QCalendarWidget {{ background: {PANEL}; color: {TEXT}; }}"
            f"QCalendarWidget QAbstractItemView {{ background: {PANEL}; color: {TEXT}; "
            f"  selection-background-color: {ACCENT}; selection-color: white; }}"
            f"QCalendarWidget QWidget#qt_calendar_navigationbar "
            f"  {{ background: {SURFACE}; }}"
        )
        lay.addWidget(self._calendar)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time:"))
        self._time_edit = QTimeEdit()
        self._time_edit.setTime(QTime(19, 0))   # default 7:00 PM
        self._time_edit.setDisplayFormat("hh:mm AP")
        time_row.addWidget(self._time_edit)
        time_row.addStretch()

        add_btn = QPushButton("➕ Add Date")
        add_btn.setProperty("class", "accent")
        add_btn.setToolTip("Add selected date/time as a candidate (max 4)")
        add_btn.clicked.connect(self._add_candidate)
        time_row.addWidget(add_btn)
        lay.addLayout(time_row)

        # ── Candidate list ──
        list_hdr = QHBoxLayout()
        list_hdr.addWidget(self._section_label("Candidates"))
        list_hdr.addStretch()
        remove_btn = QPushButton("🗑 Remove")
        remove_btn.setFixedWidth(80)
        remove_btn.setToolTip("Remove selected candidate")
        remove_btn.clicked.connect(self._remove_candidate)
        list_hdr.addWidget(remove_btn)
        lay.addLayout(list_hdr)

        self._candidate_list = QListWidget()
        self._candidate_list.setMaximumHeight(95)
        self._candidate_list.setStyleSheet(
            f"background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
        )
        lay.addWidget(self._candidate_list)

        next_btn = QPushButton("Next: Create Poll  →")
        next_btn.setProperty("class", "accent")
        next_btn.clicked.connect(lambda: self._goto_poll_tab())
        lay.addWidget(next_btn)

        return w

    # ── Tab 1 — Poll ───────────────────────────────────────────────────────────

    def _build_poll_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # ── Channel selector ──
        lay.addWidget(self._section_label("Discord Channel"))
        ch_row = QHBoxLayout()
        self._channel_combo = QComboBox()
        self._channel_combo.setPlaceholderText("— connect Discord first —")
        self._channel_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        ch_row.addWidget(self._channel_combo)
        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedWidth(30)
        refresh_btn.setToolTip("Refresh channel list from Discord")
        refresh_btn.clicked.connect(self._refresh_channels)
        ch_row.addWidget(refresh_btn)
        lay.addLayout(ch_row)

        # ── Role gate ──
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel("Player role:"))
        self._role_edit = QLineEdit()
        self._role_edit.setPlaceholderText("e.g. Player  (leave blank for anyone)")
        self._role_edit.setToolTip(
            "Only members with this Discord role may vote.\n"
            "Case-insensitive. Leave blank to allow all reactions."
        )
        role_row.addWidget(self._role_edit)
        lay.addLayout(role_row)

        # ── Poll preview ──
        lay.addWidget(self._section_label("Poll Preview"))
        self._poll_preview = QTextEdit()
        self._poll_preview.setReadOnly(True)
        self._poll_preview.setMaximumHeight(110)
        self._poll_preview.setStyleSheet(
            f"background: {PANEL}; color: {MUTED}; font-size: 10px;"
            f"border: 1px solid {BORDER};"
        )
        lay.addWidget(self._poll_preview)

        # ── Send button ──
        send_row = QHBoxLayout()
        self._send_btn = QPushButton("📣 Send Poll to Discord")
        self._send_btn.setProperty("class", "accent")
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._send_poll)
        send_row.addWidget(self._send_btn)

        self._cancel_poll_btn = QPushButton("✕ Cancel Poll")
        self._cancel_poll_btn.setEnabled(False)
        self._cancel_poll_btn.clicked.connect(self._cancel_poll)
        send_row.addWidget(self._cancel_poll_btn)
        lay.addLayout(send_row)

        # ── Poll status ──
        self._poll_status_lbl = QLabel("No poll active.")
        self._poll_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        lay.addWidget(self._poll_status_lbl)

        # ── Vote display ──
        lay.addWidget(self._section_label("Live Votes"))
        self._vote_group = QGroupBox()
        self._vote_group.setStyleSheet(
            f"QGroupBox {{ border: 1px solid {BORDER}; border-radius: 4px; "
            f"  padding: 4px; margin-top: 0; }}"
        )
        self._vote_layout = QVBoxLayout(self._vote_group)
        self._vote_layout.setSpacing(4)
        self._vote_rows: List[Dict] = []   # {label, bar, count_lbl, select_btn}
        self._build_vote_rows()
        lay.addWidget(self._vote_group)

        return w

    def _build_vote_rows(self) -> None:
        """Create the 4 (emoji + date label + progress bar + count + Select) rows."""
        for i in range(MAX_CANDIDATES):
            row = QHBoxLayout()
            row.setSpacing(4)

            emoji_lbl = QLabel(POLL_EMOJIS[i])
            emoji_lbl.setFixedWidth(22)
            row.addWidget(emoji_lbl)

            date_lbl = QLabel("—")
            date_lbl.setStyleSheet(f"color: {TEXT}; min-width: 120px;")
            row.addWidget(date_lbl)

            bar = QProgressBar()
            bar.setRange(0, 1)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(12)
            bar.setStyleSheet(
                f"QProgressBar {{ background: {PANEL}; border: 1px solid {BORDER}; "
                f"  border-radius: 2px; }}"
                f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}"
            )
            row.addWidget(bar, 1)

            count_lbl = QLabel("0")
            count_lbl.setStyleSheet(f"color: {MUTED}; min-width: 20px;")
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)  # type: ignore[attr-defined]
            row.addWidget(count_lbl)

            select_btn = QPushButton("Select")
            select_btn.setFixedWidth(54)
            select_btn.setEnabled(False)
            select_btn.clicked.connect(lambda checked, idx=i: self._select_winner(idx))
            row.addWidget(select_btn)

            container = QWidget()
            container.setLayout(row)
            container.setVisible(False)
            self._vote_layout.addWidget(container)

            self._vote_rows.append({
                "container": container,
                "date_lbl":  date_lbl,
                "bar":       bar,
                "count_lbl": count_lbl,
                "select_btn": select_btn,
            })

        no_cand_lbl = QLabel("Add candidate dates in the Setup tab.")
        no_cand_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        no_cand_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)   # type: ignore[attr-defined]
        self._vote_layout.addWidget(no_cand_lbl)
        self._no_candidates_lbl = no_cand_lbl

    # ── Tab 2 — Confirm ────────────────────────────────────────────────────────

    def _build_confirm_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # ── Winner summary ──
        lay.addWidget(self._section_label("Selected Date"))
        self._winner_lbl = QLabel("No date selected yet.")
        self._winner_lbl.setWordWrap(True)
        self._winner_lbl.setStyleSheet(
            f"color: {SUCCESS}; font-size: 13px; font-weight: bold; padding: 6px;"
            f"background: {PANEL}; border-radius: 4px; border: 1px solid {BORDER};"
        )
        lay.addWidget(self._winner_lbl)

        self._winner_detail_lbl = QLabel("")
        self._winner_detail_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        lay.addWidget(self._winner_detail_lbl)

        lay.addWidget(self._section_label("Google Calendar"))
        self._gcal_btn = QPushButton("🗓  Open in Google Calendar")
        self._gcal_btn.setProperty("class", "accent")
        self._gcal_btn.setEnabled(False)
        self._gcal_btn.setToolTip(
            "Opens a pre-filled Google Calendar event in your browser.\n"
            "No login required — just review and save."
        )
        self._gcal_btn.clicked.connect(self._open_gcal)
        lay.addWidget(self._gcal_btn)

        lay.addWidget(self._section_label("Export .ics File"))
        ics_row = QHBoxLayout()
        self._ics_btn = QPushButton("💾 Export .ics")
        self._ics_btn.setEnabled(False)
        self._ics_btn.setToolTip("Save a calendar invite file (.ics) for sharing")
        self._ics_btn.clicked.connect(self._export_ics)
        ics_row.addWidget(self._ics_btn)
        self._ics_status_lbl = QLabel("")
        self._ics_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        ics_row.addWidget(self._ics_status_lbl, 1)
        lay.addLayout(ics_row)

        lay.addWidget(self._section_label("Post to Discord"))
        self._discord_post_preview = QTextEdit()
        self._discord_post_preview.setMaximumHeight(80)
        self._discord_post_preview.setStyleSheet(
            f"background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            f"font-size: 10px;"
        )
        self._discord_post_preview.setPlaceholderText("Winning date announcement…")
        lay.addWidget(self._discord_post_preview)

        post_row = QHBoxLayout()
        self._post_ch_combo = QComboBox()
        self._post_ch_combo.setPlaceholderText("— channel —")
        self._post_ch_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        post_row.addWidget(self._post_ch_combo)

        self._post_btn = QPushButton("📨 Post to Discord")
        self._post_btn.setEnabled(False)
        self._post_btn.clicked.connect(self._post_to_discord)
        post_row.addWidget(self._post_btn)
        lay.addLayout(post_row)

        self._post_status_lbl = QLabel("")
        self._post_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        lay.addWidget(self._post_status_lbl)

        lay.addStretch()
        return w

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {ACCENT}; font-weight: bold; font-size: 11px;"
            f"border-bottom: 1px solid {BORDER}; padding-bottom: 2px;"
        )
        return lbl

    # ── Persistence ────────────────────────────────────────────────────────────

    def _restore_state(self) -> None:
        role = self._settings.value("scheduler/player_role", "", type=str)
        if role:
            self._role_edit.setText(role)

        last_ch = self._settings.value("scheduler/post_channel", "", type=str)
        self._settings.setValue("scheduler/_last_post_channel", last_ch)   # stash for later

    def _save_role(self) -> None:
        self._settings.setValue("scheduler/player_role", self._role_edit.text().strip())

    # ── Campaign list ──────────────────────────────────────────────────────────

    def _populate_campaigns(self) -> None:
        self._campaign_combo.clear()
        vaults = getattr(self._config, "vaults", None) or {}
        if vaults:
            for name in sorted(vaults.keys()):
                self._campaign_combo.addItem(name)
        else:
            self._campaign_combo.addItem("My Campaign")

    # ── Candidate management ───────────────────────────────────────────────────

    def _add_candidate(self) -> None:
        if len(self._candidates) >= MAX_CANDIDATES:
            QMessageBox.information(
                self, "Max Dates Reached",
                f"You can have at most {MAX_CANDIDATES} candidate dates.\n"
                "Remove one before adding another."
            )
            return

        qdate = self._calendar.selectedDate()
        qtime = self._time_edit.time()
        dt = datetime(
            qdate.year(), qdate.month(), qdate.day(),
            qtime.hour(), qtime.minute()
        )

        if dt in self._candidates:
            QMessageBox.information(self, "Already Added",
                                    "That date/time is already in the list.")
            return

        self._candidates.append(dt)
        self._candidates.sort()
        self._refresh_candidate_list()
        self._refresh_poll_preview()
        self._refresh_vote_rows()
        self._update_send_btn_state()
        self.status_message.emit(f"Candidate added: {_fmt_label(dt)}")

    def _remove_candidate(self) -> None:
        row = self._candidate_list.currentRow()
        if row < 0 or row >= len(self._candidates):
            return
        removed = self._candidates.pop(row)
        self._refresh_candidate_list()
        self._refresh_poll_preview()
        self._refresh_vote_rows()
        self._update_send_btn_state()
        self.status_message.emit(f"Candidate removed: {_fmt_label(removed)}")

    def _refresh_candidate_list(self) -> None:
        self._candidate_list.clear()
        for i, dt in enumerate(self._candidates):
            self._candidate_list.addItem(
                f"{POLL_EMOJIS[i]}  {_fmt_label(dt)}"
            )

    # ── Poll preview ───────────────────────────────────────────────────────────

    def _refresh_poll_preview(self) -> None:
        if not self._candidates:
            self._poll_preview.setPlainText("")
            return
        role = self._role_edit.text().strip()
        title = self._title_edit.text().strip() or "Next Session"
        lines = [f"📅 Vote for the next session: **{title}**", ""]
        for i, dt in enumerate(self._candidates):
            lines.append(f"{POLL_EMOJIS[i]}  {_fmt_label(dt)}")
        lines.append("")
        if role:
            lines.append(f"_Only @{role} members may vote._")
        lines.append("_React below! Poll closes when the GM picks a date._")
        self._poll_preview.setPlainText("\n".join(lines))

    # ── Vote rows ──────────────────────────────────────────────────────────────

    def _refresh_vote_rows(self) -> None:
        has_any = bool(self._candidates)
        self._no_candidates_lbl.setVisible(not has_any)
        for i, row_d in enumerate(self._vote_rows):
            visible = i < len(self._candidates)
            row_d["container"].setVisible(visible)
            if visible:
                row_d["date_lbl"].setText(_fmt_label(self._candidates[i]))
                row_d["count_lbl"].setText(str(self._votes.get(i, 0)))
                row_d["bar"].setValue(self._votes.get(i, 0))
                row_d["select_btn"].setEnabled(self._poll_active)

    def _update_bar_ranges(self) -> None:
        max_v = max((self._votes.get(i, 0) for i in range(len(self._candidates))),
                    default=1)
        for bar_row in self._vote_rows:
            bar_row["bar"].setRange(0, max(max_v, 1))

    # ── Poll flow ──────────────────────────────────────────────────────────────

    def _goto_poll_tab(self) -> None:
        if not self._candidates:
            QMessageBox.warning(self, "No Candidates",
                                "Add at least one candidate date before continuing.")
            return
        self._refresh_poll_preview()
        self._tabs.setCurrentIndex(1)
        # Ask Discord for fresh channel list
        self._refresh_channels()

    def _refresh_channels(self) -> None:
        self.request_channels.emit()
        self._poll_status_lbl.setText("⟳  Fetching channels…")

    def _update_send_btn_state(self) -> None:
        ok = bool(self._candidates) and not self._poll_active
        self._send_btn.setEnabled(ok)

    def _send_poll(self) -> None:
        if not self._candidates:
            QMessageBox.warning(self, "No Candidates",
                                "Add at least one date in the Setup tab.")
            return

        ch_id_str = self._channel_combo.currentData()
        if ch_id_str is None:
            QMessageBox.warning(self, "No Channel",
                                "Select a Discord text channel.")
            return

        self._save_role()
        role = self._role_edit.text().strip()

        options: List[Tuple[str, str]] = [
            (_fmt_date(dt), _fmt_time(dt)) for dt in self._candidates
        ]

        self._send_btn.setEnabled(False)
        self._poll_status_lbl.setText("⟳  Sending poll…")
        self._poll_status_lbl.setStyleSheet(f"color: {WARNING}; font-size: 10px;")

        self.send_poll_sig.emit(int(ch_id_str), options, role)

    def _cancel_poll(self) -> None:
        self.close_poll_sig.emit()
        self._poll_active = False
        self._cancel_poll_btn.setEnabled(False)
        self._votes.clear()
        self._refresh_vote_rows()
        self._update_send_btn_state()
        self._poll_status_lbl.setText("Poll cancelled.")
        self._poll_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        for row_d in self._vote_rows:
            row_d["select_btn"].setEnabled(False)
        self.status_message.emit("Scheduler: poll cancelled")

    # ── Winner selection ───────────────────────────────────────────────────────

    def _select_winner(self, idx: int) -> None:
        if idx >= len(self._candidates):
            return
        self._winner = self._candidates[idx]
        votes = self._votes.get(idx, 0)
        title = self._title_edit.text().strip() or "Session"

        # Update Confirm tab
        self._winner_lbl.setText(
            f"🗓  {_fmt_label(self._winner)}"
        )
        self._winner_detail_lbl.setText(
            f"{title}  ·  {self._duration_spin.value()} hrs  "
            f"·  {votes} vote{'s' if votes != 1 else ''}"
        )
        self._gcal_btn.setEnabled(True)
        self._ics_btn.setEnabled(True)
        self._post_btn.setEnabled(True)

        # Pre-fill Discord announcement
        notes = self._notes_edit.toPlainText().strip()
        ann = (
            f"📅 **{title}** is confirmed!\n"
            f"🕐  {_fmt_label(self._winner)}\n"
            f"⏱  Duration: {self._duration_spin.value()} hrs\n"
        )
        if notes:
            ann += f"\n{notes}"
        self._discord_post_preview.setPlainText(ann)

        # Close the poll in Discord worker
        self.close_poll_sig.emit()
        self._poll_active = False
        self._cancel_poll_btn.setEnabled(False)
        self._update_send_btn_state()

        # Switch to Confirm tab
        self._tabs.setCurrentIndex(2)
        self.status_message.emit(f"Scheduler: winner selected — {_fmt_label(self._winner)}")

    # ── Google Calendar ────────────────────────────────────────────────────────

    def _open_gcal(self) -> None:
        if not self._winner:
            return
        title = self._title_edit.text().strip() or "TTRPG Session"
        notes = self._notes_edit.toPlainText().strip()
        end = self._winner + timedelta(hours=self._duration_spin.value())
        url = _gcal_url(title, self._winner, end, notes)
        webbrowser.open(url)
        self.status_message.emit("Google Calendar: opened in browser")

    # ── .ics export ────────────────────────────────────────────────────────────

    def _export_ics(self) -> None:
        if not self._winner:
            return
        title = self._title_edit.text().strip() or "TTRPG Session"
        notes = self._notes_edit.toPlainText().strip()
        end = self._winner + timedelta(hours=self._duration_spin.value())

        default_name = (
            f"session_{self._winner.strftime('%Y-%m-%d')}.ics"
        )
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export .ics File",
            str(Path.home() / default_name),
            "iCalendar Files (*.ics)"
        )
        if not dest:
            return

        try:
            from pantheon.promitor.session_scheduler import SessionInfo, create_ics_file
            info = SessionInfo(
                title=title,
                start=self._winner,
                end=end,
                description=notes,
            )
            create_ics_file(info, Path(dest))
            self._ics_status_lbl.setText(f"✔ Saved: {Path(dest).name}")
            self._ics_status_lbl.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
            self.status_message.emit(f"Scheduler: .ics exported — {Path(dest).name}")
        except Exception as exc:
            self._ics_status_lbl.setText(f"✗ {exc}")
            self._ics_status_lbl.setStyleSheet(f"color: {ERROR}; font-size: 10px;")

    # ── Post to Discord ────────────────────────────────────────────────────────

    def _post_to_discord(self) -> None:
        ch_id_str = self._post_ch_combo.currentData()
        if ch_id_str is None:
            QMessageBox.warning(self, "No Channel", "Select a Discord text channel.")
            return
        content = self._discord_post_preview.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Empty Message", "The announcement is empty.")
            return

        # We emit via main_window wiring; the DiscordPanel will call post_message_to_channel
        # For now we fire a generic status; main_window wires up the actual send
        self._post_via_discord(int(ch_id_str), content)
        self._post_status_lbl.setText("✔ Sent!")
        self._post_status_lbl.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
        self.status_message.emit("Scheduler: session announcement posted to Discord")

    # This slot is connected in main_window.py to DiscordPanel.post_message_to_channel
    _post_channel_request: Optional[Tuple[int, str]] = None

    def _post_via_discord(self, channel_id: int, content: str) -> None:
        """Stores the pending post; main_window wiring calls discord_panel directly."""
        # main_window wires: scheduler._discord_post.connect(discord_panel.post_message_to_channel)
        # We store it and fire a signal that main_window can pick up.
        self._discord_post_channel_id = channel_id
        self._discord_post_content = content
        self.discord_post_ready.emit(channel_id, content)

    discord_post_ready: Signal = Signal(int, str)   # channel_id, message

    # ── Inbound slots (connected by main_window.py) ───────────────────────────

    def on_channels_available(self, channels: list) -> None:
        """Receive text channel list from DiscordPanel."""
        self._text_channels = [(ch_id, name) for ch_id, name in channels]

        # Poll tab channel combo
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        for ch_id, name in self._text_channels:
            self._channel_combo.addItem(f"# {name}", userData=ch_id)
        self._channel_combo.blockSignals(False)

        # Confirm tab post channel combo
        self._post_ch_combo.blockSignals(True)
        self._post_ch_combo.clear()
        for ch_id, name in self._text_channels:
            self._post_ch_combo.addItem(f"# {name}", userData=ch_id)
        self._post_ch_combo.blockSignals(False)

        # Restore last-used post channel
        last = self._settings.value("scheduler/post_channel", "", type=str)
        if last:
            idx = self._post_ch_combo.findText(f"# {last}")
            if idx >= 0:
                self._post_ch_combo.setCurrentIndex(idx)

        self._poll_status_lbl.setText(
            f"{len(channels)} text channel{'s' if len(channels) != 1 else ''} loaded."
        )
        self._poll_status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._update_send_btn_state()

    def on_poll_sent(self, message_id: str) -> None:
        """Discord confirmed the poll message was posted."""
        self._poll_active = True
        self._cancel_poll_btn.setEnabled(True)
        self._poll_status_lbl.setText(f"✔ Poll active  (msg id {message_id})")
        self._poll_status_lbl.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")
        for row_d in self._vote_rows:
            row_d["select_btn"].setEnabled(True)
        self._votes = {i: 0 for i in range(len(self._candidates))}
        self._refresh_vote_rows()
        self.status_message.emit(f"Scheduler: poll posted (id {message_id})")

    def on_vote_updated(self, votes: dict) -> None:
        """Receive fresh vote tallies from the Discord reaction handler."""
        self._votes = {int(k): int(v) for k, v in votes.items()}
        self._update_bar_ranges()
        self._refresh_vote_rows()

    def on_poll_error(self, error: str) -> None:
        """Discord failed to post the poll."""
        self._poll_status_lbl.setText(f"✗ {error}")
        self._poll_status_lbl.setStyleSheet(f"color: {ERROR}; font-size: 10px;")
        self._send_btn.setEnabled(bool(self._candidates))
        self.status_message.emit(f"Scheduler poll error: {error[:60]}")
