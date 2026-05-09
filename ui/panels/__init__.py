"""Panel exports for Project Ceres UI.

Each panel is the current shipped implementation for its feature area.
Panels are dockable unless noted otherwise.
"""

from .browser_panel import BrowserPanel
from .chat_panel import ChatPanel
from .console_panel import ConsolePanel
from .discord_panel import DiscordPanel
from .equalizer_panel import EqualizerPanel
from .fgu_panel import FGUPanel
from .local_music_panel import LocalMusicPanel
from .master_scene_panel import MasterScenePanel
from .mixer_panel import MixerPanel
from .now_playing_panel import NowPlayingPanel
from .plex_jellyfin_panel import PlexJellyfinPanel
from .scheduler_panel import SchedulerPanel
from .soundboard_panel import SoundboardPanel
from .spotify_panel import SpotifyPanel
from .syrinscape_panel import SyrinscapePanel
from .tidal_panel import TidalPanel
from .vault_notes_panel import VaultNotesPanel
from .visualiser_panel import VisualiserPanel
from .youtube_panel import YouTubePanel

__all__ = [
    "BrowserPanel",
    "ChatPanel",
    "ConsolePanel",
    "DiscordPanel",
    "EqualizerPanel",
    "FGUPanel",
    "LocalMusicPanel",
    "MasterScenePanel",
    "MixerPanel",
    "NowPlayingPanel",
    "PlexJellyfinPanel",
    "SchedulerPanel",
    "SoundboardPanel",
    "SpotifyPanel",
    "SyrinscapePanel",
    "TidalPanel",
    "VaultNotesPanel",
    "VisualiserPanel",
    "YouTubePanel",
]
