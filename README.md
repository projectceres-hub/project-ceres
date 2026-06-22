# Project Ceres

A modular Python-based GM Assistant for tabletop RPG game masters. Built around campaign management, session workflows, rules indexing, and a full modular GUI: Obsidian vaults, Ceres Chat (GPT agent), Discord (voice + transcription), multiple music sources (Spotify, YouTube, Tidal, local files), Syrinscape, soundboard scenes, FGU data, scheduler, browser, and a per-source volume mixer.

---

## What It Does

Project Ceres started as a terminal assistant for Obsidian vault management and has grown into a modular workflow platform for the full session lifecycle — all from a single Winamp-style dockable panel interface plus a central chat surface.

**Core capabilities:**

- Manage multiple Obsidian vaults with switching, ignoring, and auto-sync from Obsidian config
- Create, read, edit, and version-control notes with GPT assistance
- **Ceres Chat** — natural-language command dispatch to panels and backend actions
- Manage templates, tags, and structured campaign folders (PCs, NPCs, locations, sessions)
- Index and search SRD documents with fuzzy ranking and contextual snippets
- Convert PDFs to markdown with custom YAML mapping rules
- Schedule TTRPG sessions, generate `.ics` invites, and export Discord-ready JSON packages
- Run background automation jobs (vault backups, SRD rebuilds, session reminders, cache cleanup)
- Process voice commands from text, transcripts, or audio files via wake words (**"Veras"** / **"Chroma"**)
- Ingest Fantasy Grounds Unity logs, parse characters/NPCs/locations, and attach them to session notes
- Record and live-transcribe Discord voice sessions via OpenAI Whisper
- **Spotify** — OAuth2 playback, search, playlists, scene slots (primary UI on the Spotify panel)
- **YouTube** — yt-dlp audio stream + search (Data API) + OAuth playlists + scene slots
- **Tidal** — device-flow OAuth (tokens in `.tidal_token.json`), search, playlists, local pygame playback
- **Local Music** — folder library (mutagen tags), queue, scenes, offline playback via pygame
- **Syrinscape** — REST API soundsets/moods and scene slots
- Trigger multi-track audio scenes via a built-in **soundboard** (simultaneous channels, per-slot volume/loop)
- **Volume Mixer** — per-source level and mute for registered audio panels (visibility follows Modules menu toggles)

---

## Setup

**Requirements:** Python 3.11+

**Install core dependencies:**
```bash
pip install prompt_toolkit openai pyyaml python-dotenv PyQt5
```

**Install optional integrations** (each unlocks or enhances GUI panels):
```bash
pip install discord.py[voice] PyNaCl   # Discord — bot + voice recording
pip install openai                      # Whisper + GPT (already above)
pip install pygame                      # Soundboard, YouTube/Tidal/local music playback
pip install spotipy                     # Spotify — OAuth2 playback control
pip install requests                    # Syrinscape REST (often pre-installed)
pip install PyQtWebEngine               # Browser panel (PyQt5); PySide6 bundles WebEngine
pip install yt-dlp                      # YouTube audio extraction
pip install tidalapi                    # Tidal panel — OAuth device flow
pip install mutagen                     # Local Music — ID3 / Vorbis / FLAC tags
```

**Configure secrets and keys** — add to `variables.env` (never commit this file). The GUI **Preferences** dialog can also push values into the running process (`os.environ`).

```
OPENAI_API_KEY=your-key-here
DISCORD_BOT_TOKEN=your-bot-token-here
SPOTIFY_CLIENT_ID=your-client-id
SPOTIFY_CLIENT_SECRET=your-client-secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
SYRINSCAPE_AUTH_TOKEN=your-syrinscape-token-here
YOUTUBE_API_KEY=your-youtube-data-api-key
# Optional: path to Google OAuth client secrets JSON for YouTube playlists / OAuth flows
YOUTUBE_CLIENT_SECRETS_FILE=C:/path/to/client_secret.json
```

**OAuth / token files (gitignored by default):** `.tidal_token.json`, `.youtube_token.json` — created by the Tidal and YouTube panels after you sign in.

**Run the GUI:**
```bash
python ui_main.py
```

On launch, `ui_main.py` enables High-DPI attributes, then redirects **stdout/stderr** to `logs/ui.log` (fresh file each run). One line is still printed to the real terminal pointing at that log path.

**Run the terminal assistant:**
```bash
python assistant.py
```

On first launch the assistant will prompt you to select a vault. Settings are saved to `settings.json`.

---

## GUI Panels

The desktop interface is a modular Winamp-style window. **Ceres Chat** is the central widget; other modules are **QDockWidget** panels you can dock, tab, float, or hide via **View** / **Modules**. Branded tab icons are applied from `ui/assets/` where PNGs exist.

### 💬 Ceres Chat (central)
- GPT-4o agent with conversational UI; interprets intent and dispatches to backend commands and panels
- Status messages and optional console output bridge

### 📚 Vault & Notes
- Obsidian vault browser, note CRUD, templates integration via shared `Config`

### 🖥 Console
- Captures stdout-style output and can run CLI-oriented flows; **hidden by default** (toggle from View menu)

### 🎙 Discord Panel
Connects a Discord bot to the GM workflow.

- **Bot connection** — `DISCORD_BOT_TOKEN` from `variables.env`
- **Voice channel monitoring** — shows who's in the session channel
- **Session recording** — voice audio chunked to OpenAI Whisper for live transcription
- **Wake-word detection** — **Veras** / **Chroma** on transcripts; note-taking commands and **media** phrases (Spotify, Syrinscape, YouTube, Tidal, local library) — see `ui/panels/discord_panel.py` for exact regex and text prefixes
- **Text commands** (examples): Spotify `!play`, `!pause`, `!skip`, `!stop`, `!search`; YouTube `!ytplay`, `!ytstop`, …; Tidal `!tidalplay`, …; Local `!localplay`, `!localstop`, …
- **Persona responses** — varied reply pools per command type; posted to a configurable text channel
- **Transcript view** — live display of transcription and detected commands
- **Save transcript** — export to the active vault
- Signals wired in `ui/main_window.py` to **Spotify**, **Syrinscape**, **YouTube**, **Tidal**, and **Local Music** `handle_command` slots

### 🎵 Spotify Panel
Full Spotify integration via OAuth2. **Browse, search, and playlists live here** — this is the main Spotify UX.

- Now Playing, album art, transport, volume
- Track search and playlist browser
- **Scene slots** (8) — assign playlists for quick recall; soundboard integration where wired
- Discord `!play` / `!search` and wake-word Spotify phrases forward into this panel (no duplicate full player UI on Discord)

### 🔊 Soundboard Panel
Two-tab interface for audio playback.

**Sounds tab** — load a folder of audio files. Files are grouped by subfolder into labelled categories (Ambience, Combat, Music, SFX, etc.) with one-click trigger buttons and a master volume slider.

**Scenes tab** — named collections of audio slots for full scene setup.
- Create, rename, and delete scenes (e.g. "Tavern Night", "Dark Forest Combat", "Boss Fight")
- Each scene holds multiple audio slots. Per slot: file path, individual volume (0–100), loop toggle
- **Play Scene** — starts all slots simultaneously using `pygame.mixer.Channel` (up to 32 concurrent sounds)
- **Stop Scene** — stops all active scene channels
- Individual slot Play / Stop buttons for mid-scene adjustments
- Volume sliders update the live channel volume in real time
- Loop toggle can be changed while playing — sound restarts with new loop setting
- Scenes persist across restarts via QSettings
- Graceful fallback message if pygame is not installed

### ⚔ Fantasy Grounds Unity Panel
Reads FGU campaign data from the local install.

- Scans the FGU campaigns root for all installed campaigns
- Parses characters, NPCs, locations, and items from FGU XML exports
- Displays parsed data in a browseable tree
- Attach FGU chat logs to session notes in Obsidian

### 📅 Scheduler Panel
- Schedule TTRPG sessions, generate `.ics` calendar invites, and post Discord polls for availability
- View and manage upcoming sessions

### 🎲 Syrinscape Panel
Controls Syrinscape Online Player via its REST API.

- **Connect** — enter or load `SYRINSCAPE_AUTH_TOKEN` from `variables.env`; Connect validates the token and loads soundsets
- **Soundsets tab** — lists all user soundsets with artwork thumbnails; click to load its moods
- **Moods tab** — filter bar + scrollable mood list for the selected soundset; double-click or **▶ Play** to play; updates the Now Playing label
- **Scenes tab** — 8 named quick-launch slots in a 2×4 grid (Combat, Ambient, Tavern, Travel, Dungeon, Chase, Rest, Boss); left-click plays, right-click assigns the selected mood or clears; slots persist across restarts via `syrinscape_scenes.json`
- **Stop All** — `POST /stop-all/` from the header bar
- **Master volume** — 0–100 slider with 400ms debounce (stored locally; real-time per-element volume is a planned enhancement)
- **Voice command slot** — `handle_command("play_mood", name)` / `handle_command("stop", "")` for Discord/chat integration

### 🌐 Browser Panel
Embedded web view for quick reference while prepping or running a session.

- **Navigation** — back, forward, reload; address bar accepts URLs, bare domains, or DuckDuckGo search; status line shows load progress
- **TTRPG bookmarks** — defaults (D&D Beyond, SRD APIs, VTTs, tools) on first run; stored in QSettings. **🔖** menu jumps to a site; **✎ Manage bookmarks** opens a list to **add by URL**, **rename**, or **remove**. **`Ctrl+D`** prompts for a name and saves the current page
- **Clip to Obsidian** — **✂ Clip to Obsidian** grabs the text selection via JavaScript; the dialog lets you pick vault folder, tags, and title, then writes Obsidian-style markdown (quote block when text is selected, or a short reference note with link only). Requires an **active vault** (set in Vault / Notes)
- Requires **PyQtWebEngine** (`pip install PyQtWebEngine`) for PyQt5, or use PySide6 which bundles Qt WebEngine; without it, the panel shows an install hint

### ▶ YouTube Panel
- yt-dlp stream + pygame playback, YouTube Data API search (`YOUTUBE_API_KEY`), optional OAuth for playlists (client secrets file + token cache)
- Scene slots, mixer registration, Discord text + wake-word commands

### 🌊 Tidal Panel
- `tidalapi` device-flow login; tokens persisted to `.tidal_token.json`
- Search, playlists, pygame playback from stream URL, scene slots, Discord commands

### 🎵 Local Music Panel
- Folder picker, recursive scan, **mutagen** metadata, Artist → Album → Track tree
- Now Playing, queue, transport, 8 scene slots (`local_music_scenes.json`)
- Discord `!localplay` / `!localstop` / `!localpause` / `!localnext` and local-music wake phrases
- Registered on the Volume Mixer as **Local Music**

### 🎚 Volume Mixer Panel
- One row per registered source (Soundboard, Syrinscape, Spotify, YouTube, Tidal, Local Music) with optional brand icon
- Per-source and master level; mute; row visibility follows **Modules** checkboxes (`toggleViewAction`), not which dock tab is front-most

### ⚙ Preferences
- **Settings** from the menu bar — multi-page dialog (`ui/dialogs/preferences_dialog.py`): API keys, general options (model, voice, reminders), service-specific blocks, FGU/Obsidian paths

---

## Wake Words & Persona Responses

Wake words are configured in `pantheon/convector/wake_words.py`:

```python
WAKE_WORDS = ("veras", "chroma")
```

Both work identically for command detection. The active wake word becomes the **persona** that replies.

| Wake word | Persona name | Character |
|-----------|-------------|-----------|
| `veras`   | **Veras**   | Warm, direct, note-keeper style |
| `chroma`  | **Chroma**  | Technical, signal/data flavoured |

**Supported voice command formats (note-taking examples):**
```
Veras, add bookmark: <label>
Veras, append note <note_path>: <content>
Veras, add session marker: <label>
Chroma, add bookmark: <label>
```

Additional wake-word patterns route audio to the right panel (e.g. “play … on youtube”, “play … on tidal”, “play … locally” / “stop …”) — implementation detail in `ui/panels/discord_panel.py` (`_on_command_detected`).

Response pools and persona display names are defined at the top of `ui/panels/discord_panel.py`. To add a new persona, add the wake word to `WAKE_WORDS` and add a matching entry in `PERSONA_RESPONSES` and `PERSONA_DISPLAY`.

---

## Terminal Command Reference

### Vault
| Command | Description |
|---|---|
| `vaults` | List available vaults |
| `switch [name/number]` | Switch active vault |
| `addvault <path>` | Add a new vault |
| `ignorevault <name>` | Exclude a vault from auto-import |
| `unignorevault <name>` | Re-include a vault |
| `showignored` | List ignored vaults |

### Notes
| Command | Description |
|---|---|
| `read <filename>` | Display a note in the terminal |
| `list [folder]` | List markdown files, optionally filtered |
| `tree` | Show vault folder structure |
| `createnote` | Create a note (blank or from template) |
| `editnote` | Edit a note with GPT assistance |
| `send <note>` | Send note to GPT for analysis or summarization |
| `undo [note_path]` | Restore note to previous state |
| `history-list <note> [limit]` | Show version history (default: last 10) |
| `history-restore <note> <index>` | Restore a specific version |

### Templates
| Command | Description |
|---|---|
| `showtemplates` | List and preview templates |
| `createtemplate` | Create a new template |
| `uploadtemplate` | Upload a `.md` file as a template |
| `uploadalltemplates` | Upload all `.md` files from a folder |
| `deletetemplate` | Remove a template |
| `template-preview` | Preview a template with variable substitution |

### Search & Indexing
| Command | Description |
|---|---|
| `search <query>` | Search notes — supports `system:`, `tag:`, `name:` filters |
| `index` | Rebuild the vault search index |
| `srd-index` | Rebuild the SRD index (reads from `/SRDs/`) |
| `search-srd <query>` | Search SRD files with fuzzy ranking and snippets |

### Tags
| Command | Description |
|---|---|
| `tag-add <note> <tag>` | Add a tag to a note |
| `tag-remove <note> <tag>` | Remove a tag from a note |
| `tag-list` | List all tags in the vault with counts |
| `tag-notes <tag>` | Find all notes with a specific tag |

### PDF
| Command | Description |
|---|---|
| `pdf2md <path> [--map maps/dnd5e.yaml]` | Convert a single PDF to markdown |
| `pdfbatch <folder> [--map maps/dnd5e.yaml]` | Batch-convert a folder of PDFs |
| `pdf-send-to-vault --input <path>` | Convert and save directly to vault |

### Campaigns
| Command | Description |
|---|---|
| `campaign-create <name>` | Create a campaign with full folder structure |
| `campaign-add-pc <campaign> <name>` | Add a player character |
| `campaign-add-npc <campaign> <attitude> <name>` | Add an NPC (ally/friendly/neutral/adversarial/antagonist) |
| `campaign-add-location <campaign> <name>` | Add a location |

### Sessions
| Command | Description |
|---|---|
| `session-schedule` | Schedule the next session and generate a calendar invite |
| `session-discord-export` | Schedule a session and export a Discord-ready JSON package |
| `session-reminder-run-now` | Immediately check for upcoming session reminders |
| `session-create` | Create a new session note for a campaign |
| `fgu-import-log` | Import a Fantasy Grounds chat log into a session note |
| `fgu-import <campaign_path> [--types npc,pc,item,encounter,note] [--overwrite]` | Import FGU campaign entities into the active vault |
| `fgu-export <output_xml_path> [--vault <vault_name>]` | Export FGU-tagged vault notes to standalone XML |

### Automation
| Command | Description |
|---|---|
| `schedule-start` | Start the background job scheduler |
| `schedule-stop` | Stop the scheduler |
| `schedule-status` | Show scheduler status and registered jobs |
| `schedule-run-once` | Run all pending jobs once (for testing) |
| `schedule-backup-run-now` | Run a vault backup immediately |
| `srd-index-run-now` | Rebuild the SRD index immediately |
| `template-sync-now` | Run template sync immediately |
| `cache-clean-now` | Run cache cleanup immediately |
| `snapshot-run-now` | Run a daily snapshot immediately |

### Voice Commands
| Command | Description |
|---|---|
| `voice-enable` / `voice-disable` / `voice-status` | Toggle voice command processing |
| `voice-command <text>` | Parse a text string into a voice command and queue it |
| `voice-commands-from-transcript <path>` | Extract and queue commands from a transcript file |
| `voice-commands-from-audio <path>` | Transcribe an audio file and queue wake-word commands |
| `session-audio-ingest "<campaign>" "<session>" <path>` | Transcribe session audio, attach to session note, extract commands |
| `voice-commands-process [--dry-run]` | Process all queued voice commands |

Wake words are **"Veras"** and **"Chroma"** (case-insensitive).

### System
| Command | Description |
|---|---|
| `help` | Show help |
| `debug` | Print diagnostic information |
| `reset` | Reset all settings to defaults |

---

## Architecture — The Pantheon

Project Ceres organizes its functionality into twelve named domains called the Pantheon, each responsible for a distinct phase of the GM workflow.

| Domain | Path | Responsibility |
|---|---|---|
| **Vervactor** | `pantheon/vervactor/` | Campaign creation and vault setup |
| **Reparator** | `pantheon/reparator/` | Templates and preparation |
| **Imporcitor** | `pantheon/imporcitor/` | Bulk import, PDF tools, batch processing |
| **Insitor** | `pantheon/insitor/` | Note creation and seeding |
| **Obarator** | `pantheon/obarator/` | Tags and metadata |
| **Occator** | `pantheon/occator/` | Search and SRD indexing |
| **Serritor** | `pantheon/serritor/` | Automation and background jobs |
| **Subruncinator** | `pantheon/subruncinator/` | Cleanup and maintenance |
| **Messor** | `pantheon/messor/` | Session harvesting — FGU logs, audio transcription |
| **Convector** | `pantheon/convector/` | Data transport — voice commands, Discord exports, session packages |
| **Conditor** | `pantheon/conditor/` | Storage, backups, history |
| **Promitor** | `pantheon/promitor/` | Distribution — session scheduling, calendar exports |

The `core/` and `automation/` directories exist as **backward-compatibility shims** that re-export from Pantheon. New code should always be placed in the appropriate Pantheon domain.

**Shim mapping:**

| Shim | Canonical location |
|---|---|
| `core/campaigns.py` | `pantheon/vervactor/` |
| `core/templates.py` | `pantheon/reparator/` |
| `core/pdf.py` | `pantheon/imporcitor/` |
| `pdf_tools/` | `pantheon/imporcitor/pdf_tools/` |
| `core/notes.py` (create) | `pantheon/insitor/` |
| `core/tags.py` | `pantheon/obarator/` |
| `core/search_index.py` | `pantheon/occator/` |
| `core/srd_index.py` | `pantheon/occator/` |
| `core/scheduler.py` | `pantheon/serritor/` |
| `automation/job.py` | `pantheon/serritor/job` |
| `automation/task_scheduler.py` | `pantheon/serritor/task_scheduler` |
| `core/history.py` | `pantheon/conditor/` |
| `core/session_scheduler.py` | `pantheon/promitor/` |

---

## File Structure

```
Project Ceres/
├── assistant.py              # Terminal entry point and command loop
├── ui_main.py                # GUI entry point (modular panel interface)
├── variables.env             # API keys (gitignored — never commit)
├── settings.json             # Persisted app settings (gitignored)
├── vaults.json               # Vault configuration (gitignored)
│
├── core/                     # Legacy shims → Pantheon
├── automation/               # Legacy shims → pantheon/serritor/
├── pdf_tools/                # Legacy shims → pantheon/imporcitor/pdf_tools/
│
├── pantheon/                 # Canonical module implementations
│   ├── conditor/             # History, backups
│   ├── convector/            # Voice commands, Discord exports, wake words, chat agent
│   │   ├── wake_words.py     # WAKE_WORDS = ("veras", "chroma")
│   │   ├── chat_agent.py     # Ceres Chat NLP / dispatch
│   │   ├── transcript_parser.py
│   │   ├── text_command_parser.py
│   │   └── voice_commands.py
│   ├── imporcitor/           # PDF tools
│   ├── insitor/              # Note creation and seeding
│   │   └── note_creator.py   # NoteSpec, create_note(), safe_filename()
│   ├── messor/               # FGU logs, audio transcription
│   ├── obarator/             # Tags
│   ├── occator/              # Search, SRD index
│   ├── promitor/             # Session scheduling, calendar
│   ├── reparator/            # Templates
│   ├── serritor/             # Background jobs
│   ├── subruncinator/        # Cleanup
│   └── vervactor/            # Campaigns
│
├── ui/                       # GUI (Winamp-style docks + central chat)
│   ├── theme.py
│   ├── input_bridge.py       # Qt input provider for CLI prompts in GUI mode
│   ├── main_window.py        # All docks, menus, signal wiring
│   ├── dialogs/
│   │   └── preferences_dialog.py
│   ├── assets/               # Tab / mixer PNG icons (youtube, spotify, …)
│   └── panels/
│       ├── chat_panel.py
│       ├── vault_notes_panel.py
│       ├── console_panel.py
│       ├── discord_panel.py
│       ├── spotify_panel.py
│       ├── soundboard_panel.py
│       ├── fgu_panel.py
│       ├── scheduler_panel.py
│       ├── browser_panel.py
│       ├── syrinscape_panel.py
│       ├── youtube_panel.py
│       ├── tidal_panel.py
│       ├── local_music_panel.py
│       └── mixer_panel.py
│
├── helpers/
│   └── discord_bot/          # Discord integration scaffold + JSON schema
│
├── core/maps/                # YAML rule maps for PDF conversion
│   ├── dnd5e.yaml
│   ├── pf2e.yaml
│   ├── wwn.yaml
│   └── generic.yaml
│
└── exports/                  # Runtime outputs (gitignored)
    ├── next_session.ics
    ├── next_session.json
    └── session_share_message.txt
```

**Runtime data directories / files (often gitignored):**
- `logs/` — GUI log (`ui.log`), errors, etc.
- `.ceres_history/` — Note version backups and history index
- `.ceres_index/` — SRD search index
- `backups/YYYY-MM-DD/` — Scheduled vault backups
- `inbox/voice_commands/` — Queued voice command files
- `.tidal_token.json`, `.youtube_token.json` — OAuth token caches
- `local_music_scenes.json`, `tidal_scene_playlists.json`, `syrinscape_scenes.json` — user scene presets (as created by panels)

---

## Background Jobs

The scheduler runs these jobs automatically when started with `schedule-start`:

| Job | Interval | Description |
|---|---|---|
| Vault Backup | 24 hours | Creates a dated zip of the active vault |
| SRD Index Rebuild | 12 hours | Rebuilds the SRD search index |
| Session Reminder | 1 hour | Checks for upcoming sessions |
| Template Sync | 6 hours | Syncs templates from remote URL (when configured) |
| Cache Cleanup | Periodic | Clears stale cache files |
| Daily Snapshot | Daily | Creates a vault snapshot |

---

## Tech Stack

- **Python 3.11+**
- `PyQt5` / `PySide6` — GUI (try PyQt5 first, fall back to PySide6); **Qt WebEngine** for Browser
- `pygame` — Soundboard (multi-channel), YouTube/Tidal/local music playback paths
- `openai` — GPT-4o (chat + note assist) and Whisper transcription
- `discord.py[voice]` + `PyNaCl` — Discord bot and voice sink
- `spotipy` — Spotify OAuth2
- `yt-dlp` — YouTube audio extraction
- `tidalapi` — Tidal OAuth device flow and metadata
- `mutagen` — Local Music tags / album art
- `requests` — Syrinscape REST and general HTTP
- `prompt_toolkit` — Terminal assistant UI
- `pyyaml` — YAML frontmatter and PDF mapping rules
- `python-dotenv` — Load `variables.env`

---

## Development Notes

**Code standards:**
- Google-style docstrings on all public functions
- Full type hints required
- 4-space indentation, PyQt5/PySide6 try/except guards on all UI imports
- No circular imports — all state flows through the `Config` dataclass
- Pure functions where possible; no global variables

**Adding a feature:**
1. Identify the correct Pantheon domain for your feature
2. Add implementation inside `pantheon/<domain>/`
3. If backward compatibility is needed, add a shim in `core/` or `automation/`
4. Register any new CLI commands in `assistant.py`
5. Document the command in this README

**Adding a wake word / persona:**
1. Add the word (lowercase) to `WAKE_WORDS` in `pantheon/convector/wake_words.py`
2. Add a matching entry in `PERSONA_RESPONSES` (response pools per command type) and `PERSONA_DISPLAY` (display name) at the top of `ui/panels/discord_panel.py`

**Git workflow:**
- One feature or bug fix per commit
- Keep `variables.env`, `settings.json`, `vaults.json`, and `exports/` out of git — they're already gitignored

---

## Roadmap

Shipped panels and upcoming work (Equalizer, Visualiser, Plex/Jellyfin, deferred music services) are maintained in **`ROADMAP.md`**. That file is the canonical feature backlog; this README focuses on how to run and navigate the current app.

**Still desirable (not panel-complete):** deeper FGU → Obsidian import workflows, tighter soundboard ↔ Spotify scene linking, and other items listed under Phase 3+ in `ROADMAP.md`.
