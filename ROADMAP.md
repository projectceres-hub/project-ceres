# Project Ceres — Feature Roadmap

> Living document. Update as items are started, completed, or deprioritised.
> Last updated: 2026-04-09

---

## Current State — All Shipped ✅

| Panel | Notes |
|---|---|
| Ceres Chat | GPT-4o NLP agent, command dispatch |
| Discord | Bot, voice record, Whisper transcription, Veras/Chroma personas; text + wake commands for Spotify, Syrinscape, YouTube, Tidal, Local Music |
| Spotify | OAuth2, now playing, search, playlists, 8 scene slots |
| Syrinscape | REST API, soundsets/moods, 8 scene slots, voice commands |
| YouTube | yt-dlp stream + pygame, Data API search, OAuth playlists, 8 scene slots, Discord text + voice commands |
| Tidal | tidalapi OAuth (device flow), search, playlists, pygame playback, scene slots, Discord wiring |
| Soundboard | pygame multi-channel, Sounds + Scenes tabs |
| Volume Mixer | Per-source rows with icons, mute per channel; row visibility tied to `toggleViewAction().toggled` (Modules on/off), not dock tab focus |
| Fantasy Grounds Unity | XML parser, characters/NPCs/items, vault import |
| Scheduler | Session scheduling, .ics export, Discord polls |
| Browser | Embedded WebEngine, Obsidian clip, TTRPG bookmarks |
| Vault & Notes | Obsidian vault browser, note CRUD |
| Console | stdout capture, CLI runner |
| Preferences Dialog | Multi-page: API keys (all services), General (AI model, voice, reminders), FGU/Obsidian paths |
| Local Music | mutagen + pygame folder library, Artist→Album→Track tree, queue, scenes (`local_music_scenes.json`), Discord `!local*` + wake phrases, mixer row |

---

## Phase 2 — Music Ecosystem Expansion

*Goal: give the GM control over every music service they might actually use, each in its own Winamp-style panel.*

### 🎵 Local Music Panel ✅ SHIPPED
Full implementation complete. See `HANDOFF.md` (2026-04-07) for build notes.

- Folder picker with recursive library scan; mutagen for tags and album art
- Artist → Album → Track tree, filter bar, Now Playing + progress + transport
- Queue tab with shuffle/clear; auto-advance when a track ends
- 8 scene slots (track or folder assign, persist to `local_music_scenes.json`)
- Discord: `!localplay`, `!localstop`, `!localpause`, `!localnext`; wake phrases (`play … locally`, `local play …`, `stop local music`, etc.)
- Mixer: `register_source("Local Music", …)` with `music.png` tab icon

**Dependencies:** `mutagen`, `pygame`

---

### 🎬 YouTube Panel ✅ SHIPPED
Full implementation complete. yt-dlp stream + pygame playback, Data API search, OAuth playlists, 8 scene slots, voice and text command wiring through Discord.

---

### 🌊 Tidal Panel ✅ SHIPPED
Full implementation complete. tidalapi OAuth (device flow + `.tidal_token.json`), search, playlist browser, pygame playback from stream URL, 8 scene slots, Discord voice + text command wiring.

---

### 🍎 Apple Music Panel
**Priority: Low | Feasibility: ⚠️ Uncertain — DEFERRED**

Apple Music on Windows has no scriptable API. MusicKit is iOS/macOS/web only. UI automation is fragile and breaks on app updates.

**Decision:** Defer until Apple provides a Windows-compatible API or a reliable COM interface is confirmed. Revisit if `amwin-rp` (GitHub) approach matures.

---

### 🏠 Plex / Jellyfin Panel
**Priority: Low-Medium | Feasibility: ✅ Clean**

For GMs who self-host their media. Both Plex and Jellyfin have well-documented REST APIs. A single panel could support both via a "server type" toggle.

- Connect to Plex or Jellyfin server (URL + API key/token)
- Browse music library
- Play via server's streaming endpoint → pygame
- Scene slots
- Mixer registration

**Dependencies:** `plexapi` (for Plex), raw HTTP for Jellyfin

---

## Phase 3 — The Full Winamp Experience

*Goal: replicate the Winamp "main window" utilities — EQ and visualiser. (Mixer is already shipped.)*

### 🎚 Volume Mixer Panel ✅ SHIPPED
Per-source rows with optional brand icons, visibility tied to `toggleViewAction().toggled` (Modules on/off), not dock tab selection. Mixer `register_source` wired across all audio panels.

---

### 🎛 Equalizer Panel
**Priority: Medium | Feasibility: ✅ for local audio / ⚠️ limited for streams**

Classic 10-band graphic EQ, Winamp-style. Applies to pygame-based audio (Soundboard, Local Music, YouTube audio via yt-dlp). Cannot EQ Spotify/Tidal/Syrinscape streams at the API level.

```
┌─ 🎛 EQUALIZER ──────────────────────────────────────────┐
│  Preset: [Flat ▾]                    [Reset] [On/Off]   │
│                                                          │
│  32   64  125  250  500   1K   2K   4K   8K  16K  Hz    │
│  ▲    ▲    ▲    ▲    ▲    ▲    ▲    ▲    ▲    ▲         │
│  ●    │    │    │    ●    │    │    │    │    │    +12dB │
│  │    ●    ●    ●    │    ●    ●    ●    ●    ●    0dB  │
│  │    │    │    │    │    │    │    │    │    │   -12dB  │
└──────────────────────────────────────────────────────────┘
```

- 10 vertical sliders (32Hz → 16kHz), ±12dB range
- Built-in presets: Flat, Bass Boost, Treble Boost, Vocal, Rock, Classical, Gaming
- Custom preset save/load
- Applies to pygame audio via numpy/scipy real-time convolution
- Panel clearly labels which sources are affected ("applies to Soundboard, Local Music, YouTube")

**Dependencies:** `numpy`, `scipy` (for FFT-based EQ filter)
**Note:** Real-time EQ on pygame audio requires routing PCM through a processing buffer — needs careful implementation to avoid latency.

---

### 📊 Visualiser Panel
**Priority: Low (fun stretch goal) | Feasibility: ✅ Moderate**

Animated audio visualiser, pure nostalgia. Classic bar spectrum analyser or oscilloscope waveform display, driven by the pygame audio buffer.

- Bar spectrum analyser (FFT of pygame output buffer)
- Oscilloscope mode
- A few colour themes
- Runs in its own QThread to avoid blocking the UI

**Dependencies:** `numpy` (FFT), Qt painter or `pyqtgraph`

---

## Phase 4 — Deferred / Won't Do

| Item | Decision |
|---|---|
| SRD Reference Panel | ❌ Already covered — Obsidian plugin handles SRD lookup, no need to duplicate |
| Amazon Music Panel | ❌ No public API, no viable path |
| Apple Music Panel (Windows) | ⏸ Deferred — no scriptable Windows API as of 2026. Revisit if Apple ships COM interface |
| SoundCloud Panel | ⏸ Low priority — API is limited and the GM use case is weak |
| Bandcamp Panel | ❌ No playback API — purchase/browse only |

---

## Current Build Order

Based on GM utility, technical feasibility, and momentum:

1. **Equalizer Panel** ← **NEXT** — completes the Winamp trio (Mixer ✅, EQ, Visualiser); applies to pygame-backed sources per Phase 3 spec
2. **Visualiser Panel** — stretch goal, fun
3. **Plex / Jellyfin Panel** — niche but clean build for self-hosters
4. ~~Local Music Panel~~ ✅ — done
5. ~~Syrinscape polish~~ ✅ — done
6. ~~Volume Mixer Panel~~ ✅ — done
7. ~~YouTube Panel~~ ✅ — done
8. ~~Tidal Panel~~ ✅ — done

---

## Notes on Audio Architecture

All pygame-based audio (Soundboard, Local Music, YouTube) share the same `pygame.mixer` instance. The Volume Mixer panel owns the master volume concept and signals down to each panel via `register_source`. EQ panel (when built) should sit between the audio buffer and pygame output — requires a processing shim.

Streaming panels (Spotify, Tidal, Syrinscape) use their own service APIs for volume — the Mixer panel talks to their signals rather than touching pygame directly. This boundary should be preserved as new panels are added.
