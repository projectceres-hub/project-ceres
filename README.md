# Project Ceres

A modular Python-based GM assistant for managing Obsidian markdown vaults. Built around campaign management, session workflows, rules indexing, automation, and a growing set of integrations with Discord, Fantasy Grounds Unity, Spotify, and voice transcription.

---

## What It Does

Project Ceres started as a terminal assistant for Obsidian vault management and has grown into a modular workflow platform for tabletop RPG game masters. It handles the full session lifecycle: organizing notes and campaigns, indexing rules documents, scheduling sessions, recording and transcribing audio, exporting to Discord, and running background jobs automatically.

**Core capabilities:**

- Manage multiple Obsidian vaults with switching, ignoring, and auto-sync from Obsidian config
- Create, read, edit, and version-control notes with GPT assistance
- Manage templates, tags, and structured campaign folders (PCs, NPCs, locations, sessions)
- Index and search SRD documents with fuzzy ranking and contextual snippets
- Convert PDFs to markdown with custom YAML mapping rules
- Schedule TTRPG sessions, generate `.ics` invites, and export Discord-ready JSON packages
- Run background automation jobs (vault backups, SRD rebuilds, session reminders, cache cleanup)
- Process voice commands from text, transcripts, or audio files via wake words ("Veras" / "Chroma")
- Ingest Fantasy Grounds Unity logs and attach them to session notes

---

## Setup

**Requirements:** Python 3.11+

**Install dependencies:**
```bash
pip install prompt_toolkit openai pyyaml python-dotenv
```

**Configure your API key** — copy the template and add your key:
```
variables.env   ← add: OPENAI_API_KEY=your-key-here
```

**Run:**
```bash
python assistant.py
```

On first launch the assistant will prompt you to select a vault. Settings are saved to `settings.json`.

---

## Command Reference

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
| `pdf-convert <path> [--map maps/dnd5e.yaml]` | Convert a single PDF to markdown |
| `pdf-batch <folder> [--map maps/dnd5e.yaml]` | Batch-convert a folder of PDFs |
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

Project Ceres organizes its functionality into twelve named domains called the Pantheon, each named after a helper deity of Ceres and responsible for a distinct phase of the GM workflow.

| Domain | Path | Responsibility |
|---|---|---|
| **Vervactor** | `pantheon/vervactor/` | Campaign creation and vault setup |
| **Reparator** | `pantheon/reparator/` | Templates and preparation |
| **Imporcitor** | `pantheon/imporcitor/` | Bulk import, PDF tools, batch processing |
| **Insitor** | `pantheon/insitor/` | Note creation and seeding (planned) |
| **Obarator** | `pantheon/obarator/` | Tags and metadata |
| **Occator** | `pantheon/occator/` | Search and SRD indexing |
| **Serritor** | `pantheon/serritor/` | Automation and background jobs |
| **Subruncinator** | `pantheon/subruncinator/` | Cleanup and maintenance |
| **Messor** | `pantheon/messor/` | Session harvesting — FGU logs, audio transcription |
| **Convector** | `pantheon/convector/` | Data transport — voice commands, Discord exports, session packages |
| **Conditor** | `pantheon/conditor/` | Storage, backups, history |
| **Promitor** | `pantheon/promitor/` | Distribution — session scheduling, calendar exports |

The `core/` and `automation/` directories still exist as **backward-compatibility shims** that re-export from Pantheon. New code should always be placed in the appropriate Pantheon domain.

**Shim mapping:**

| Shim | Canonical location |
|---|---|
| `core/campaigns.py` | `pantheon/vervactor/` |
| `core/templates.py` | `pantheon/reparator/` |
| `core/pdf.py` | `pantheon/imporcitor/` |
| `pdf_tools/` | `pantheon/imporcitor/pdf_tools/` |
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
├── assistant.py              # Main entry point and command loop
├── variables.env             # API keys (gitignored — never commit)
├── settings.json             # Persisted app settings (gitignored)
├── vaults.json               # Vault configuration (gitignored)
│
├── core/                     # Legacy shims → Pantheon
├── automation/               # Legacy shims → pantheon/serritor/
├── pdf_tools/                # Legacy shims → pantheon/imporcitor/pdf_tools/
├── pantheon/                 # Canonical module implementations
│   ├── conditor/             # History, backups
│   ├── convector/            # Voice, Discord, session packages
│   ├── imporcitor/           # PDF tools
│   ├── insitor/              # Note seeding (planned)
│   ├── messor/               # FGU logs, audio
│   ├── obarator/             # Tags
│   ├── occator/              # Search, SRD index
│   ├── promitor/             # Session scheduling, calendar
│   ├── reparator/            # Templates
│   ├── serritor/             # Background jobs
│   ├── subruncinator/        # Cleanup
│   └── vervactor/            # Campaigns
│
├── helpers/
│   └── discord_bot/          # Discord integration scaffold + JSON schema
│
├── ui/                       # GUI panels (Winamp-style modular interface)
│   └── panels/               # Discord, FGU, Spotify, Soundboard, Scheduler, etc.
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

**Runtime data directories (created automatically):**
- `.ceres_history/` — Note version backups and history index
- `.ceres_index/` — SRD search index
- `backups/YYYY-MM-DD/` — Scheduled vault backups
- `inbox/voice_commands/` — Queued voice command files

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
- `prompt_toolkit` — Interactive terminal UI with autocompletion
- `openai` — GPT-4o integration and Whisper audio transcription
- `pyyaml` — YAML frontmatter and mapping rules
- `python-dotenv` — Environment variable loading from `variables.env`
- `PyQt5` / `tkinter` — UI panels (modular GUI)

---

## Development Notes

**Code standards:**
- Google-style docstrings on all public functions
- Full type hints required
- 4-space indentation
- No circular imports — all state flows through the `Config` dataclass
- Pure functions where possible; no global variables

**Adding a feature:**
1. Identify the correct Pantheon domain for your feature
2. Add implementation inside `pantheon/<domain>/`
3. If backward compatibility is needed, add a shim in `core/` or `automation/`
4. Register any new CLI commands in `assistant.py`
5. Document the command in this README

**Git workflow:**
- One feature or bug fix per commit
- Run any affected scheduler or automation code before pushing
- Keep `variables.env`, `settings.json`, `vaults.json`, and `exports/` out of git — they're already gitignored

---

## Roadmap

**Active / in progress:**
- Modular GUI (Winamp-style panels) for Discord, FGU, Spotify, Soundboard, and Scheduler
- Fantasy Grounds Unity deeper integration (character import, item/place extraction)
- Discord bot for session announcements and voice transcription

**Scaffolded and ready to build:**
- Full OpenAI Whisper audio transcription pipeline
- Spotify playlist control and voice-triggered scene music
- Discord voice channel recording and real-time transcription

**Longer term:**
- Webhook integrations for external services
- Plugin/extension system
- Cloud storage sync options
