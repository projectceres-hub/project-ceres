"""Workspace/session state helpers for Project Ceres.

Vervactor owns campaign and workspace setup, so this module provides the
small shared state layer used by UI panels without introducing a GUI
dependency into Pantheon.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class WorkspaceObjectRef:
    """Reference to the object currently in focus for the GM."""

    kind: str = ""
    path: str = ""
    title: str = ""
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceState:
    """Vault-scoped session/workspace state."""

    active_vault: str = ""
    active_campaign: str = ""
    active_session: str = ""
    current_scene: str = ""
    layout_profile: str = "default"
    current_object: Optional[WorkspaceObjectRef] = None


@dataclass
class AudioSourceState:
    """Model state for one playable audio source."""

    source_id: str
    label: str
    title: str = ""
    artist: str = ""
    album: str = ""
    position_ms: int = 0
    duration_ms: int = 0
    playing: bool = False
    paused: bool = False
    volume: int = 100
    can_pause: bool = False
    can_next: bool = False
    can_prev: bool = False
    can_stop: bool = False

    @property
    def progress_pct(self) -> int:
        if self.duration_ms <= 0:
            return -1
        return max(0, min(100, int((self.position_ms / self.duration_ms) * 100)))

    @property
    def subtitle(self) -> str:
        bits = [bit for bit in (self.artist, self.album) if bit]
        return " - ".join(bits)


@runtime_checkable
class AudioSourceAdapter(Protocol):
    """Minimal control/state interface for Now Playing style views."""

    source_id: str
    label: str

    def get_state(self) -> AudioSourceState:
        ...

    def play(self) -> None:
        ...

    def pause(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def next(self) -> None:
        ...

    def previous(self) -> None:
        ...


class PanelAudioSourceAdapter:
    """Adapter for existing panels that expose get_np_state/handle_command."""

    def __init__(self, source_id: str, label: str, panel: object) -> None:
        self.source_id = source_id
        self.label = label
        self._panel = panel

    def get_state(self) -> AudioSourceState:
        raw: Dict[str, Any] = {}
        if hasattr(self._panel, "get_np_state"):
            raw = dict(self._panel.get_np_state())  # type: ignore[attr-defined]
        subtitle = str(raw.get("subtitle", ""))
        artist = str(raw.get("artist", "")) or subtitle
        position_ms = int(raw.get("position_ms", 0) or 0)
        duration_ms = int(raw.get("duration_ms", 0) or 0)
        raw_pct = int(raw.get("progress_pct", -1) or -1)
        if duration_ms <= 0 and raw_pct >= 0:
            position_ms = raw_pct
            duration_ms = 100
        return AudioSourceState(
            source_id=self.source_id,
            label=self.label,
            title=str(raw.get("title", "")),
            artist=artist,
            album=str(raw.get("album", "")),
            position_ms=position_ms,
            duration_ms=duration_ms,
            playing=bool(raw.get("playing", False)),
            paused=bool(raw.get("paused", False)),
            volume=int(raw.get("volume", 100) or 100),
            can_pause=bool(raw.get("can_pause", False)),
            can_next=bool(raw.get("can_next", False)),
            can_prev=bool(raw.get("can_prev", False)),
            can_stop=bool(raw.get("can_stop", False)),
        )

    def play(self) -> None:
        action = "play"
        if self.label == "YouTube":
            action = "pause"
        self._command(action, "")

    def pause(self) -> None:
        self._command("pause", "")

    def stop(self) -> None:
        action = "pause" if self.label == "Spotify" else "stop"
        self._command(action, "")

    def next(self) -> None:
        action = "skip" if self.label in {"Spotify", "Tidal"} else "next"
        self._command(action, "")

    def previous(self) -> None:
        self._command("previous", "")

    def _command(self, action: str, query: str) -> None:
        if hasattr(self._panel, "handle_command"):
            self._panel.handle_command(action, query)  # type: ignore[attr-defined]


def _vault_path_from_config(config: object) -> Optional[Path]:
    current = getattr(config, "current_vault", None)
    vaults = getattr(config, "vaults", {}) or {}
    if current and current in vaults:
        return Path(vaults[current])
    return None


def workspace_dir(config: object) -> Optional[Path]:
    """Return the active vault's .ceres directory, or None when no vault exists."""
    vault_path = _vault_path_from_config(config)
    if vault_path is None:
        return None
    return vault_path / ".ceres"


def _state_path(config: object) -> Optional[Path]:
    root = workspace_dir(config)
    return None if root is None else root / "workspace_state.json"


def load_workspace_state(config: object) -> WorkspaceState:
    """Load active-vault workspace state, returning empty in-memory state if absent."""
    current = getattr(config, "current_vault", None) or ""
    path = _state_path(config)
    if path is None or not path.exists():
        return WorkspaceState(active_vault=current)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        obj_data = data.get("current_object")
        current_object = (
            WorkspaceObjectRef(**obj_data)
            if isinstance(obj_data, dict)
            else None
        )
        return WorkspaceState(
            active_vault=str(data.get("active_vault", current)),
            active_campaign=str(data.get("active_campaign", "")),
            active_session=str(data.get("active_session", "")),
            current_scene=str(data.get("current_scene", "")),
            layout_profile=str(data.get("layout_profile", "default")),
            current_object=current_object,
        )
    except Exception:
        return WorkspaceState(active_vault=current)


def save_workspace_state(config: object, state: WorkspaceState) -> bool:
    """Persist workspace state under the active vault; return False if unavailable."""
    path = _state_path(config)
    if path is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def set_current_object(config: object, ref: WorkspaceObjectRef) -> None:
    """Update only the current object in the active workspace state."""
    state = load_workspace_state(config)
    state.active_vault = getattr(config, "current_vault", None) or state.active_vault
    state.current_object = ref
    save_workspace_state(config, state)


def _scene_path(config: object, service: str) -> Optional[Path]:
    root = workspace_dir(config)
    if root is None:
        return None
    return root / "scenes" / f"{service}.json"


def load_scene_data(
    config: object,
    service: str,
    legacy_path: Path,
    default: Any,
) -> Any:
    """Load scene JSON from the active vault, migrating legacy root JSON once."""
    scene_path = _scene_path(config, service)
    if scene_path is not None:
        if scene_path.exists():
            try:
                return json.loads(scene_path.read_text(encoding="utf-8"))
            except Exception:
                return default
        if legacy_path.exists():
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
                scene_path.parent.mkdir(parents=True, exist_ok=True)
                scene_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                return data
            except Exception:
                return default
        return default

    if legacy_path.exists():
        try:
            return json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_scene_data(
    config: object,
    service: str,
    legacy_path: Path,
    data: Any,
) -> bool:
    """Save scene JSON to active-vault storage, falling back to legacy path."""
    scene_path = _scene_path(config, service)
    target = scene_path if scene_path is not None else legacy_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True
