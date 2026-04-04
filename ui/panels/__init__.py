"""
Panel modules for Project Ceres UI.

Each panel is a QDockWidget that can be docked, floated, or hidden.
Panels communicate with the backend through run_command() or directly
via the Config reference passed at construction time.

Available panels
----------------
VaultNotesPanel  — vault selector + note browser + quick actions     [ACTIVE]
ConsolePanel     — raw command input + scrollable output log          [ACTIVE]
SoundboardPanel  — load a folder of audio files and trigger them      [ACTIVE]
DiscordPanel     — Discord bot connection + session recording         [SCAFFOLD]
SpotifyPanel     — Spotify playback + scene playlist quick-launch     [SCAFFOLD]
FGUPanel         — Fantasy Grounds Unity campaign browser + import    [SCAFFOLD]
"""

from .vault_notes_panel import VaultNotesPanel
from .console_panel     import ConsolePanel
from .soundboard_panel  import SoundboardPanel
from .discord_panel     import DiscordPanel
from .spotify_panel     import SpotifyPanel
from .fgu_panel         import FGUPanel

__all__ = [
    "VaultNotesPanel",
    "ConsolePanel",
    "SoundboardPanel",
    "DiscordPanel",
    "SpotifyPanel",
    "FGUPanel",
]
