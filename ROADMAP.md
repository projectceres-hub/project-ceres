# Project Ceres — Feature Roadmap

> Living document. Update as items are started, completed, or deprioritised.
> Last updated: 2026-05-31 (Phase 5 FGU recovery; Infinite Table captured as future architecture)

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
| Volume Mixer | Per-source rows with icons, mute per channel |
| Fantasy Grounds Unity | XML parser, characters/NPCs/items; Messor `FGUEntityParser`; background import UI; selectable standalone XML export |
| Scheduler | Session scheduling, .ics export, Discord polls |
| Browser | Embedded WebEngine, Obsidian clip, TTRPG bookmarks |
| Vault & Notes | Obsidian vault browser, note CRUD, markdown preview |
| Console | stdout capture, CLI runner |
| Preferences Dialog | API keys, General, Paths, Interface, FGU, Soundboard, Templates, Plex/Jellyfin |
| Local Music | mutagen + pygame folder library, Artist→Album→Track tree, queue, scenes, Discord wiring |
| Now Playing | 2s-poll aggregator across all audio sources, transport controls |
| Equalizer | 10-band EQ, 7 presets, scipy engine, applies to pygame sources |
| Visualiser | numpy FFT spectrum analyser, 5 colour themes, peak-hold |
| Plex / Jellyfin | Server-type toggle, library browser, Now Playing, Search, 8 scene slots, Mixer row |
| Master Scenes | 8 cross-panel scene slots (2×4), JSON persistence, Discord `!scene` / voice |

---

## Phase 5 — Completing Open Items & New Capabilities

*Goal: close out the one incomplete panel, add a cross-panel scene orchestration layer, then tackle the deepest workflow integration in the project.*

---

### 1. 🏠 Plex / Jellyfin — Discord Wiring ✅ COMPLETE

**Priority: High | Scope: Small | Status: Done**

The Plex/Jellyfin panel is functionally complete but lacks Discord text command and wake-word integration — the last requirement for it to be considered fully shipped.

**What to build:**
- Discord text commands in `discord_panel.py`:
  - `!plexplay <query>` — search and play on Plex
  - `!plexstop` — stop playback
  - `!plexpause` — pause/resume
  - `!jellyplay <query>` — search and play on Jellyfin
  - `!jellystop` — stop playback
  - `!jellypause` — pause/resume
- Wake-word phrases in `discord_panel.py` `_on_command_detected`:
  - `"play … on plex"` / `"plex play …"` → `plex_jellyfin_command` signal → `handle_command("play", query)`
  - `"play … on jellyfin"` / `"jellyfin play …"` → same signal path
  - `"stop plex"` / `"stop jellyfin"` → `handle_command("stop", "")`
- New `plex_jellyfin_command` signal on `DiscordPanel` (matching `tidal_command`, `local_music_command` pattern)
- Wire signal in `MainWindow._build_panels` → `PlexJellyfinPanel.handle_command`
- Persona response pool entry for Plex/Jellyfin commands

**Files:** `ui/panels/discord_panel.py`, `ui/main_window.py`
**No new panel, no new Config fields, no new dependencies.**

**Done when:** `!plexplay tavern music` and `"Veras, play something on Jellyfin"` both trigger playback and post a persona reply to Discord.

---

### 2. 🎬 Master Scene Panel ✅ COMPLETE

**Priority: High | Scope: Medium | Status: Done**

A new dock panel that acts as a scene orchestrator — one named slot fires multiple panels simultaneously. Replaces the current per-panel scene approach for complex table moments (combat, boss fight, rest, etc.) where the GM wants ambience, music, and soundboard to all change at once.

**What to build:**

**Panel: `ui/panels/master_scene_panel.py`**
- 8 named scene slots in a 2×4 grid (same layout as Spotify/Syrinscape scenes)
- Each slot stores a scene definition: `{name, spotify_playlist_id, syrinscape_mood, soundboard_scene, youtube_scene, tidal_scene, local_music_scene, plex_jellyfin_track}`
- **Play Scene** fires all defined sub-slots simultaneously via `handle_command` on the relevant panel
- **Stop All** sends stop to all registered panels
- Right-click → Edit scene: name field + per-panel assignment pickers (pull current state from each panel)
- Scene definitions persist to `master_scenes.json`
- `handle_command("play", scene_name_or_index)` for Discord/voice wiring

**Discord / voice wiring:**
- Wake-word: `"Veras, play [scene name]"` → matches against master scene names → fires scene
- Text command: `!scene <name or number>`
- New `scene_command` signal on `DiscordPanel`
- Persona response pool entry for scene commands

**MainWindow wiring:**
- Dock #18, tabified after Plex/Jellyfin on the right stack
- `_TAB_ICONS["Master Scenes"]` → `music.png` (or a dedicated icon later)
- View + Modules menu toggles
- `_reset_layout` entry
- Construct panel after all audio panels exist; pass references or use signal-based `handle_command` to avoid direct panel imports

**Files:** `ui/panels/master_scene_panel.py` (new), `ui/panels/discord_panel.py`, `ui/main_window.py`

**Done when:** Clicking a master scene slot fires Spotify, Syrinscape, and Soundboard simultaneously, and `"Veras, play Tavern Night"` does the same from Discord.

---

### 3. ⚔ FGU ↔ Obsidian Deep Import

**Priority: High | Scope: Large | Status: Backend, templates, worker-based UI, and CLI recovery complete; real-campaign manual validation still required**

The most complex item in Phase 5. Extends the existing FGU panel from surface-level XML browsing into a full bidirectional bridge — FGU entities become structured Obsidian notes, and notes can be exported back to FGU-compatible XML.

**Scope:**
- Entity types: NPCs (with stat blocks), Player Characters, Locations, Items/Equipment
- Game systems: D&D 5e, Savage Worlds, Stars Without Number / OSR
- Direction: **Bidirectional** — FGU → Obsidian (import) and Obsidian → FGU (export)
- Trigger: Manual from the FGU panel (Import / Export buttons per entity type)
- Note format: Ceres defines canonical YAML frontmatter + markdown layout per entity type and system

---

#### 3a. Research Spike — FGU XML Schemas ✅ BASELINE CAPTURED

Before writing a line of implementation code, we need to map the XML structure for each system. FGU stores campaign data as XML under `<campaign>/db.xml` (and split files in newer versions).

**Research targets:**

| System | Entity types to map |
|---|---|
| D&D 5e (`dnd5e` ruleset) | NPC stat block fields, PC sheet fields, locations (`encounter` / `reference` nodes), items |
| Savage Worlds (`swade` ruleset) | Wildcard/Extra NPC fields, PC attributes/skills/edges, locations, gear |
| Stars Without Number / OSR (`swnr`, generic OSR) | NPC fields (AC, HD, attacks, saves), PC fields (class, level, saves, skills), locations, equipment |

**Deliverable from spike:** `docs/fgu_schemas.md` now documents the implemented baseline and remaining schema validation gaps. It should be expanded with real exported campaign samples before deeper system-specific parser work.

---

#### 3b. Pantheon Domain: `pantheon/messor/fgu_import.py` (extend existing Messor domain) ✅ COMPLETE

- `FGUEntityParser` class: reads `db.xml`, dispatches to per-system/per-entity parsers
- Per-system parser modules (or a single table-driven approach based on schema doc):
  - `_parse_npc_5e(node)` → `NoteSpec`
  - `_parse_npc_swade(node)` → `NoteSpec`
  - `_parse_npc_osr(node)` → `NoteSpec`
  - Same pattern for PC, location, item
- `NoteSpec` output feeds into existing `pantheon.insitor.create_note()` — no new vault writing logic
- Canonical YAML frontmatter schema per entity type (e.g. `npc_type`, `system`, `hp`, `ac`, `abilities`, `actions`, `tags`)

**Export path (`fgu_export.py`):**
- Reads Obsidian note frontmatter
- Reconstructs FGU-compatible XML node
- Merges into `db.xml` (or writes a standalone importable XML file)
- Design note: keep export as a standalone XML file first (safer than mutating `db.xml` in place)

---

#### 3c. FGU Panel UI Extensions (`ui/panels/fgu_panel.py`) ✅ COMPLETE

- **Import tab**: entity type selector, ruleset display, overwrite toggle, background worker, progress bar, and result log.
- **Export tab**: vault scan, selectable FGU-note list, Export Selected, Export All, and background XML export.
- CLI commands: `fgu-import` and `fgu-export`.

---

#### 3d. Note Templates (Ceres-defined, per system) ✅ COMPLETE

Ceres defines the canonical markdown layout for each entity type. These become Ceres templates (via Reparator) so users can customise them:

| Template | Fields |
|---|---|
| `FGU NPC (5e)` | name, system, hp, ac, speed, abilities, saving_throws, skills, damage_immunities, condition_immunities, senses, languages, challenge, actions, reactions, legendary_actions, tags |
| `FGU NPC (Savage Worlds)` | name, system, wild_card, attributes, skills, pace, parry, toughness, edges, hindrances, special_abilities, gear, tags |
| `FGU NPC (OSR/SWN)` | name, system, hd, hp, ac, attacks, saves, morale, movement, special, xp, tags |
| `FGU PC (5e)` | name, player, race, class, level, background, alignment, hp, ac, speed, abilities, saving_throws, skills, features, equipment, spells, tags |
| `FGU PC (Savage Worlds)` | name, player, race, rank, attributes, skills, derived_stats, edges, hindrances, gear, tags |
| `FGU PC (OSR/SWN)` | name, player, class, level, hp, ac, saving_throws, skills, equipment, tags |
| `FGU Location` | name, system, campaign, description, connections, npcs, items, tags |
| `FGU Item` | name, system, item_type, weight, value, rarity, description, properties, tags |

---

#### 3e. Done When

- From the FGU panel, clicking Import NPCs on a 5e campaign creates properly formatted Obsidian notes for every NPC in that campaign
- The same works for Savage Worlds and SWN campaigns
- Clicking Export on an Obsidian NPC note produces a valid FGU XML file that can be dropped into a campaign
- PCs, Locations, and Items all import correctly with correct YAML frontmatter for their system

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

## Phase 5 Build Order

| # | Item | Scope | Prerequisite |
|---|---|---|---|
| 1 | Plex/Jellyfin Discord wiring | Small | None — start immediately |
| 2 | Master Scene Panel | Medium | ✅ Done |
| 3a | FGU schema research spike | Research | Baseline captured; expand with real campaign samples |
| 3b | FGU import/export engine (Messor) | Large | ✅ Done (3a complete) |
| 3c | FGU panel UI extensions | Medium | ✅ Done |
| 3d | Note templates (all systems) | Small | ✅ Done |

---

## Notes on Architecture for Phase 5

**Master Scene Panel** must not import panel modules directly. It fires `handle_command` via references passed through `MainWindow` at construction — same pattern as `NowPlayingPanel`. Each sub-slot stores only an ID/index (not a live object reference) and the scene is fired via the MainWindow's already-wired panel references.

**FGU export** should write a standalone importable XML file first (never mutate `db.xml` in place). A future version can offer in-place merge once the export format is validated against multiple FGU versions.

**Bidirectional FGU design principle:** Obsidian is the note-taking layer; FGU is the game-state layer. On conflict (e.g. HP changed in both), FGU wins for mechanical data, Obsidian wins for narrative/description fields. Export should never overwrite FGU mechanical data without explicit user confirmation.

---

## Phase 6 — Shared Workspace & Infinite Table (Future)

*Goal: support both the current Command Center and a future Infinite Table as synchronized views over the same workspace model.*

This is not an immediate canvas build. The first step is architectural: expand the existing `pantheon/vervactor/workspace.py` state layer into a shared workspace object model. Command Center panels and the future Infinite Table must reference the same notes, NPCs, locations, encounters, audio sources, reminders, and scene objects rather than maintaining separate panel state and canvas state.

### View Modes

| Mode | Purpose |
|---|---|
| Command Center | Dockable/floating live-session panels for fast action |
| Infinite Table | Free-panning spatial canvas for prep, relationship mapping, scene staging, and session overview |

### First Implementation Slice

- Write `docs/infinite_table_mode.md` as the architecture brief and AI delegation plan.
- Extend workspace planning around object identity, layout profiles, and per-view presentation state.
- Do not build the visual canvas until the shared model is explicit and reviewed.
