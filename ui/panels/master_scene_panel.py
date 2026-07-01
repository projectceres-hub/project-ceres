"""
Master Scene panel — cross-panel scene orchestration for Project Ceres.

Fires Spotify, Syrinscape, Soundboard, YouTube, Tidal, Local Music, and
Plex/Jellyfin from one named slot via each panel's ``handle_command`` API.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from PyQt5.QtWidgets import (
        QDockWidget,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QGridLayout,
        QPushButton,
        QLabel,
        QDialog,
        QDialogButtonBox,
        QLineEdit,
        QComboBox,
        QFormLayout,
        QSizePolicy,
        QFrame,
        QMenu,
        QSlider,
    )
    from PyQt5.QtCore import Qt, pyqtSignal as Signal
except ImportError:
    from PySide6.QtWidgets import (  # type: ignore
        QDockWidget,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QGridLayout,
        QPushButton,
        QLabel,
        QDialog,
        QDialogButtonBox,
        QLineEdit,
        QComboBox,
        QFormLayout,
        QSizePolicy,
        QFrame,
        QMenu,
        QSlider,
    )
    from PySide6.QtCore import Qt, Signal  # type: ignore

from ui.theme import ACCENT, BG, BORDER, MUTED, PANEL, SURFACE, TEXT
from pantheon.vervactor.workspace import (
    load_scene_data,
    load_workspace_state,
    save_scene_data,
    save_workspace_state,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCENES_PATH = _PROJECT_ROOT / "master_scenes.json"

_DEFAULT_SCENE: Dict[str, Any] = {
    "name": "",
    "spotify_playlist_id": "",
    "syrinscape_mood": "",
    "soundboard_scene": "",
    "youtube_scene": "",
    "tidal_scene": "",
    "local_music_scene": "",
    "plex_jellyfin_track": "",
}
NUM_SLOTS = 8


def _dialog_accepted(result: int) -> bool:
    """True if *result* is an accepted QDialog exec code (PyQt5 or PySide6)."""
    if result == QDialog.Accepted:  # type: ignore[attr-defined]
        return True
    dc = getattr(QDialog, "DialogCode", None)
    if dc is not None:
        return bool(result == dc.Accepted)
    return False


def _dedupe_options(options: List[tuple[str, str]]) -> List[tuple[str, str]]:
    seen: set[str] = set()
    out: List[tuple[str, str]] = []
    for label, value in options:
        value = str(value or "").strip()
        label = str(label or value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append((label, value))
    return out


def _scene_picker_options(panel_refs: Dict[str, Any]) -> Dict[str, List[tuple[str, str]]]:
    """Return selectable scene assignments discovered from live media panels."""
    choices: Dict[str, List[tuple[str, str]]] = {
        key: []
        for key in (
            "spotify_playlist_id",
            "syrinscape_mood",
            "soundboard_scene",
            "youtube_scene",
            "tidal_scene",
            "local_music_scene",
            "plex_jellyfin_track",
        )
    }

    spotify = getattr(panel_refs.get("spotify"), "_scene_config", {}) or {}
    for slot, assignment in spotify.items():
        if isinstance(assignment, dict) and assignment.get("uri"):
            name = assignment.get("name") or slot
            choices["spotify_playlist_id"].append((f"{slot}: {name}", assignment["uri"]))

    syrinscape = getattr(panel_refs.get("syrinscape"), "_scene_config", {}) or {}
    for slot, assignment in syrinscape.items():
        if isinstance(assignment, dict) and assignment.get("mood_name"):
            mood = assignment["mood_name"]
            soundset = assignment.get("soundset_name", "")
            label = f"{slot}: {soundset} - {mood}" if soundset else f"{slot}: {mood}"
            choices["syrinscape_mood"].append((label, mood))

    soundboard_scenes = getattr(panel_refs.get("soundboard"), "_scenes", []) or []
    for scene in soundboard_scenes:
        name = getattr(scene, "name", "")
        if name:
            choices["soundboard_scene"].append((name, name))

    youtube = getattr(panel_refs.get("youtube"), "_scene_config", {}) or {}
    for slot, assignment in youtube.items():
        if isinstance(assignment, dict) and assignment.get("title"):
            title = assignment["title"]
            choices["youtube_scene"].append((f"{slot}: {title}", title))

    tidal = getattr(panel_refs.get("tidal"), "_scene_config", {}) or {}
    for slot, assignment in tidal.items():
        if isinstance(assignment, dict) and assignment.get("name"):
            name = assignment["name"]
            choices["tidal_scene"].append((f"{slot}: {name}", name))

    local_scenes = getattr(panel_refs.get("local_music"), "_scenes", []) or []
    for scene in local_scenes:
        name = getattr(scene, "name", "")
        path = getattr(scene, "path", "")
        if name and path:
            choices["local_music_scene"].append((name, name))

    plex_scenes = getattr(panel_refs.get("plex_jellyfin"), "_scenes", []) or []
    for index, scene in enumerate(plex_scenes, start=1):
        track = scene.get("track") if isinstance(scene, dict) else None
        if isinstance(track, dict) and track.get("title"):
            title = track["title"]
            choices["plex_jellyfin_track"].append((f"Scene {index}: {title}", title))

    return {key: _dedupe_options(value) for key, value in choices.items()}


def _make_scene_combo(current_value: str, options: List[tuple[str, str]]) -> QComboBox:
    combo = QComboBox()
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    combo.addItem("(none)", "")
    for label, value in options:
        combo.addItem(label, value)
    current_value = str(current_value or "").strip()
    if current_value:
        idx = combo.findData(current_value)
        if idx < 0:
            combo.addItem(f"Current: {current_value}", current_value)
            idx = combo.findData(current_value)
        combo.setCurrentIndex(idx)
    return combo


def _combo_value(combo: QComboBox) -> str:
    data = combo.currentData()
    if data is None:
        return combo.currentText().strip()
    return str(data).strip()


class _SceneEditDialog(QDialog):
    """Edit one master scene slot with real per-panel scene choices."""

    def __init__(
        self,
        scene: Dict[str, Any],
        panel_refs: Dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Campaign Scene")
        self.setModal(True)
        self._scene: Dict[str, Any] = {}
        self._choices = _scene_picker_options(panel_refs or {})

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(scene.get("name", "") or "")
        form.addRow("Name", self._name_edit)

        self._spotify_edit = _make_scene_combo(
            scene.get("spotify_playlist_id", "") or "",
            self._choices["spotify_playlist_id"],
        )
        form.addRow("Spotify playlist ID/URI", self._spotify_edit)

        self._syrin_edit = _make_scene_combo(
            scene.get("syrinscape_mood", "") or "",
            self._choices["syrinscape_mood"],
        )
        form.addRow("Syrinscape mood", self._syrin_edit)

        self._sb_edit = _make_scene_combo(
            scene.get("soundboard_scene", "") or "",
            self._choices["soundboard_scene"],
        )
        form.addRow("Soundboard scene", self._sb_edit)

        self._yt_edit = _make_scene_combo(
            scene.get("youtube_scene", "") or "",
            self._choices["youtube_scene"],
        )
        form.addRow("YouTube scene/playlist", self._yt_edit)

        self._tidal_edit = _make_scene_combo(
            scene.get("tidal_scene", "") or "",
            self._choices["tidal_scene"],
        )
        form.addRow("Tidal scene/playlist", self._tidal_edit)

        self._local_edit = _make_scene_combo(
            scene.get("local_music_scene", "") or "",
            self._choices["local_music_scene"],
        )
        form.addRow("Local Music scene", self._local_edit)

        self._plex_edit = _make_scene_combo(
            scene.get("plex_jellyfin_track", "") or "",
            self._choices["plex_jellyfin_track"],
        )
        form.addRow("Plex/Jellyfin track", self._plex_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_scene(self) -> Dict[str, Any]:
        """Return the edited scene dict (all string fields)."""
        return {
            "name": self._name_edit.text().strip(),
            "spotify_playlist_id": _combo_value(self._spotify_edit),
            "syrinscape_mood": _combo_value(self._syrin_edit),
            "soundboard_scene": _combo_value(self._sb_edit),
            "youtube_scene": _combo_value(self._yt_edit),
            "tidal_scene": _combo_value(self._tidal_edit),
            "local_music_scene": _combo_value(self._local_edit),
            "plex_jellyfin_track": _combo_value(self._plex_edit),
        }


class MasterScenePanel(QDockWidget):
    """Eight master scene slots; each fires multiple audio panels at once.

    Panel references are injected from ``MainWindow``; this widget never imports
    other panel modules.
    """

    status_message: Signal = Signal(str)

    def __init__(
        self,
        panel_refs: Dict[str, Any],
        config: Any = None,
        parent=None,
    ) -> None:
        """Create the dock and load scene definitions from ``master_scenes.json``.

        Args:
            panel_refs: Map of panel key → live panel instance (or None).
            config: Application config used for active-vault scene storage.
            parent: Optional Qt parent widget.
        """
        super().__init__("Campaign Scenes", parent)
        self.setObjectName("MasterScenePanel")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable  # type: ignore[attr-defined]
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._panel_refs: Dict[str, Any] = dict(panel_refs)
        self._config = config
        self._scenes: List[Dict[str, Any]] = self._load_scenes()
        self._slot_buttons: List[QPushButton] = []
        self._active_scene_name = ""
        self._scene_paused = False
        self._campaign_volume = 80

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct toolbar + 2×4 slot grid."""
        outer = QWidget()
        outer.setStyleSheet(f"background: {BG};")
        main = QVBoxLayout(outer)
        main.setContentsMargins(6, 6, 6, 6)
        main.setSpacing(6)

        self._toolbar_frame = QFrame()
        self._toolbar_frame.setMaximumHeight(42)
        self._toolbar_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toolbar_frame.setStyleSheet(
            f"QFrame {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 3px; }}"
        )
        toolbar = QHBoxLayout(self._toolbar_frame)
        toolbar.setContentsMargins(6, 4, 6, 4)
        toolbar.setSpacing(6)

        self._currently_playing_label = QLabel("Currently: Nothing playing")
        self._currently_playing_label.setStyleSheet(f"color: {TEXT}; font-size: 10px;")
        self._currently_playing_label.setWordWrap(False)
        self._currently_playing_label.setFixedWidth(150)
        toolbar.addWidget(self._currently_playing_label)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setFixedWidth(64)
        self._pause_btn.setFixedHeight(28)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT};"
            f" border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 12px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; }}"
            f"QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER}; }}"
        )
        self._pause_btn.clicked.connect(self._toggle_pause_targets)
        toolbar.addWidget(self._pause_btn)

        stop_btn = QPushButton("Stop All")
        stop_btn.setFixedWidth(78)
        stop_btn.setFixedHeight(28)
        stop_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT};"
            f" border: 2px solid {ACCENT}; border-radius: 4px; padding: 4px 12px; }}"
            f"QPushButton:hover {{ background: {SURFACE}; }}"
        )
        stop_btn.clicked.connect(self._stop_all)
        toolbar.addWidget(stop_btn)

        vol_lbl = QLabel("Vol")
        vol_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        vol_lbl.setFixedWidth(24)
        toolbar.addWidget(vol_lbl)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)  # type: ignore[attr-defined]
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(self._campaign_volume)
        self._volume_slider.setFixedWidth(90)
        self._volume_slider.setToolTip("Campaign Scenes volume")
        self._volume_slider.valueChanged.connect(self._on_campaign_volume_changed)
        toolbar.addWidget(self._volume_slider)

        self._volume_label = QLabel(f"{self._campaign_volume}%")
        self._volume_label.setStyleSheet(f"color: {MUTED}; font-size: 10px; min-width: 32px;")
        self._volume_label.setFixedWidth(34)
        toolbar.addWidget(self._volume_label)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._status_lbl.setWordWrap(False)
        toolbar.addWidget(self._status_lbl, 1)
        main.addWidget(self._toolbar_frame)

        self._grid_frame = QFrame()
        self._grid_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._grid_frame.setStyleSheet(
            f"QFrame {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}"
        )
        grid = QGridLayout(self._grid_frame)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)
        for row in range(2):
            grid.setRowStretch(row, 1)
        for col in range(4):
            grid.setColumnStretch(col, 1)

        self._slot_buttons = []
        for index in range(NUM_SLOTS):
            btn = self._make_slot_button(index)
            self._slot_buttons.append(btn)
            row, col = index // 4, index % 4
            grid.addWidget(btn, row, col)

        main.addWidget(self._grid_frame, 1)
        self.setWidget(outer)

    def _iter_target_panels(self):
        for p in self._panel_refs.values():
            if p is not None:
                yield p

    def _set_currently_playing(self, text: str) -> None:
        self._currently_playing_label.setText(text)

    def _set_active_scene(self, name: str) -> None:
        self._active_scene_name = name
        self._scene_paused = False
        self._pause_btn.setText("Pause")
        self._pause_btn.setEnabled(True)
        self._set_currently_playing(f"Currently: {name}")

    def _clear_active_scene(self, text: str = "Stopped") -> None:
        self._active_scene_name = ""
        self._scene_paused = False
        self._pause_btn.setText("Pause")
        self._pause_btn.setEnabled(False)
        self._set_currently_playing(text)

    def _toggle_pause_targets(self) -> None:
        if not self._active_scene_name:
            return
        for panel in self._iter_target_panels():
            handler = getattr(panel, "handle_command", None)
            if handler is None:
                continue
            try:
                handler("pause", "")
            except Exception:
                pass
        self._scene_paused = not self._scene_paused
        if self._scene_paused:
            self._pause_btn.setText("Resume")
            self._set_currently_playing(f"Paused: {self._active_scene_name}")
        else:
            self._pause_btn.setText("Pause")
            self._set_currently_playing(f"Currently: {self._active_scene_name}")

    def _on_campaign_volume_changed(self, value: int) -> None:
        self._campaign_volume = max(0, min(100, int(value)))
        self._volume_label.setText(f"{self._campaign_volume}%")
        for panel in self._iter_target_panels():
            setter = getattr(panel, "set_volume", None)
            if setter is None:
                continue
            try:
                setter(self._campaign_volume)
            except Exception:
                pass

    def _style_slot_btn(self, btn: QPushButton) -> None:
        btn.setMinimumHeight(58)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE}; color: {TEXT};"
            f" border: 1px solid {BORDER}; border-radius: 4px; padding: 6px;"
            f" font-size: 12px; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; }}"
        )

    def _make_slot_button(self, index: int) -> QPushButton:
        btn = QPushButton()
        self._style_slot_btn(btn)
        name = self._scenes[index].get("name", "").strip()
        btn.setText(name if name else f"Scene {index + 1}")
        btn.clicked.connect(lambda checked, i=index: self._play_scene(i))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)  # type: ignore[attr-defined]
        btn.customContextMenuRequested.connect(lambda pos, i=index: self._on_slot_context(i, pos))
        return btn

    def _on_slot_context(self, index: int, pos) -> None:
        menu = QMenu(self)
        edit_act = menu.addAction("Edit Scene…")
        clear_act = menu.addAction("Clear")
        act = menu.exec(self._slot_buttons[index].mapToGlobal(pos))
        if act == edit_act:
            self._edit_scene(index)
        elif act == clear_act:
            self._clear_scene(index)

    def _edit_scene(self, index: int) -> None:
        dlg = _SceneEditDialog(self._scenes[index], self._panel_refs, self)
        if _dialog_accepted(dlg.exec()):  # type: ignore[arg-type]
            self._scenes[index] = dlg.get_scene()
            self._save_scenes()
            self._refresh_button(index)

    def _clear_scene(self, index: int) -> None:
        self._scenes[index] = copy.deepcopy(_DEFAULT_SCENE)
        self._save_scenes()
        self._refresh_button(index)

    def _refresh_button(self, index: int) -> None:
        if not (0 <= index < len(self._slot_buttons)):
            return
        name = self._scenes[index].get("name", "").strip()
        self._slot_buttons[index].setText(name if name else f"Scene {index + 1}")

    def _load_scenes(self) -> List[Dict[str, Any]]:
        """Load from ``master_scenes.json``; fill missing slots with defaults."""
        out: List[Dict[str, Any]] = []
        try:
            data = load_scene_data(self._config, "master_scenes", SCENES_PATH, [])
            if isinstance(data, list):
                for i in range(NUM_SLOTS):
                    if i < len(data) and isinstance(data[i], dict):
                        merged = copy.deepcopy(_DEFAULT_SCENE)
                        merged.update(data[i])
                        out.append(merged)
                    else:
                        out.append(copy.deepcopy(_DEFAULT_SCENE))
                return out
        except (OSError, json.JSONDecodeError):
            pass
        return [copy.deepcopy(_DEFAULT_SCENE) for _ in range(NUM_SLOTS)]

    def _save_scenes(self) -> None:
        """Persist ``self._scenes`` to ``master_scenes.json``."""
        try:
            save_scene_data(self._config, "master_scenes", SCENES_PATH, self._scenes)
        except OSError:
            pass

    def _play_scene(self, index: int) -> None:
        if not (0 <= index < len(self._scenes)):
            return
        scene = self._scenes[index]
        name = scene.get("name", "").strip() or f"Scene {index + 1}"

        pr = self._panel_refs

        v = scene.get("spotify_playlist_id", "").strip()
        if v and pr.get("spotify") is not None:
            try:
                pr["spotify"].handle_command("play_playlist", v)
            except Exception:
                pass

        v = scene.get("syrinscape_mood", "").strip()
        if v and pr.get("syrinscape") is not None:
            try:
                pr["syrinscape"].handle_command("play_mood", v)
            except Exception:
                pass

        v = scene.get("soundboard_scene", "").strip()
        if v and pr.get("soundboard") is not None:
            try:
                pr["soundboard"].handle_command("play_scene", v)
            except Exception:
                pass

        for key, field in (
            ("youtube", "youtube_scene"),
            ("tidal", "tidal_scene"),
            ("local_music", "local_music_scene"),
        ):
            v = scene.get(field, "").strip()
            if v and pr.get(key) is not None:
                try:
                    pr[key].handle_command("play", v)
                except Exception:
                    pass

        v = scene.get("plex_jellyfin_track", "").strip()
        if v and pr.get("plex_jellyfin") is not None:
            try:
                pr["plex_jellyfin"].handle_command("play", v)
            except Exception:
                pass

        state = load_workspace_state(self._config)
        state.current_scene = name
        save_workspace_state(self._config, state)
        self._set_active_scene(name)
        self._on_campaign_volume_changed(self._campaign_volume)
        self.status_message.emit(f"Playing scene: {name}")
        self._status_lbl.setText(f"Last: {name}")

    def _stop_all(self) -> None:
        for key in (
            "spotify",
            "syrinscape",
            "soundboard",
            "youtube",
            "tidal",
            "local_music",
            "plex_jellyfin",
        ):
            p = self._panel_refs.get(key)
            if p is None:
                continue
            try:
                p.handle_command("stop", "")
            except Exception:
                pass
        self._clear_active_scene("Stopped")
        self.status_message.emit("All master scene targets stopped.")
        self._status_lbl.setText("Stopped all.")

    def handle_command(self, action: str, query: str = "") -> None:
        """Discord/voice entry point."""
        action = action.lower().strip()
        if action == "stop":
            self._stop_all()
            return
        if action in ("play", "play_scene"):
            q = query.strip().lower()
            for i, sc in enumerate(self._scenes):
                if sc.get("name", "").strip().lower() == q:
                    self._play_scene(i)
                    return
            try:
                idx = int(query.strip()) - 1
                if 0 <= idx < NUM_SLOTS:
                    self._play_scene(idx)
            except ValueError:
                pass
