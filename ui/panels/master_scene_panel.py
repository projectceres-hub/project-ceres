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
        QFormLayout,
        QSizePolicy,
        QFrame,
        QMenu,
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
        QFormLayout,
        QSizePolicy,
        QFrame,
        QMenu,
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


class _SceneEditDialog(QDialog):
    """Edit one master scene slot — name plus per-panel assignment strings."""

    def __init__(self, scene: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Master Scene")
        self.setModal(True)
        self._scene: Dict[str, Any] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(scene.get("name", "") or "")
        form.addRow("Name", self._name_edit)

        self._spotify_edit = QLineEdit(scene.get("spotify_playlist_id", "") or "")
        form.addRow("Spotify playlist ID/URI", self._spotify_edit)

        self._syrin_edit = QLineEdit(scene.get("syrinscape_mood", "") or "")
        form.addRow("Syrinscape mood", self._syrin_edit)

        self._sb_edit = QLineEdit(scene.get("soundboard_scene", "") or "")
        form.addRow("Soundboard scene", self._sb_edit)

        self._yt_edit = QLineEdit(scene.get("youtube_scene", "") or "")
        form.addRow("YouTube scene/playlist", self._yt_edit)

        self._tidal_edit = QLineEdit(scene.get("tidal_scene", "") or "")
        form.addRow("Tidal scene/playlist", self._tidal_edit)

        self._local_edit = QLineEdit(scene.get("local_music_scene", "") or "")
        form.addRow("Local Music scene", self._local_edit)

        self._plex_edit = QLineEdit(scene.get("plex_jellyfin_track", "") or "")
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
            "spotify_playlist_id": self._spotify_edit.text().strip(),
            "syrinscape_mood": self._syrin_edit.text().strip(),
            "soundboard_scene": self._sb_edit.text().strip(),
            "youtube_scene": self._yt_edit.text().strip(),
            "tidal_scene": self._tidal_edit.text().strip(),
            "local_music_scene": self._local_edit.text().strip(),
            "plex_jellyfin_track": self._plex_edit.text().strip(),
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
        super().__init__("Master Scenes", parent)
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

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct toolbar + 2×4 slot grid."""
        outer = QWidget()
        outer.setStyleSheet(f"background: {BG};")
        main = QVBoxLayout(outer)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        toolbar = QHBoxLayout()
        stop_btn = QPushButton("Stop All")
        stop_btn.setFixedHeight(32)
        stop_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT};"
            f" border: 2px solid {ACCENT}; border-radius: 4px; padding: 4px 12px; }}"
            f"QPushButton:hover {{ background: {SURFACE}; }}"
        )
        stop_btn.clicked.connect(self._stop_all)
        toolbar.addWidget(stop_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self._status_lbl.setWordWrap(True)
        toolbar.addWidget(self._status_lbl, 1)
        main.addLayout(toolbar)

        grid_frame = QFrame()
        grid_frame.setStyleSheet(
            f"QFrame {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}"
        )
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)

        self._slot_buttons = []
        for index in range(NUM_SLOTS):
            btn = self._make_slot_button(index)
            self._slot_buttons.append(btn)
            row, col = index // 4, index % 4
            grid.addWidget(btn, row, col)

        main.addWidget(grid_frame)
        self.setWidget(outer)

    def _style_slot_btn(self, btn: QPushButton) -> None:
        btn.setMinimumHeight(64)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        dlg = _SceneEditDialog(self._scenes[index], self)
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
