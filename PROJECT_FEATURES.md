# Project Ceres - Features & Changes Summary

**Version:** 0.1  
**Project Type:** Python-based terminal assistant for managing Obsidian markdown vaults

---

## 🎯 Core Features

### **Vault Management**
- **Multiple Vault Support**: Manage multiple Obsidian vaults simultaneously
- **Auto-Sync with Obsidian**: Automatically detects and imports vaults from Obsidian config
- **Vault Switching**: Switch between vaults by name or number
- **Vault Ignoring**: Ignore specific vaults from auto-import
- **Default Vault**: Automatic default vault creation and management

### **Note Management**
- **Create Notes**: Create new markdown notes, optionally from templates
- **Read Notes**: Display note contents in terminal
- **List Notes**: List all markdown files in current vault (with folder filtering)
- **Tree View**: Visual tree structure of vault folders and notes
- **Edit Notes**: Edit notes with ChatGPT assistance (append, overwrite, or save as new)
- **Send Notes**: Send note contents to ChatGPT for analysis/summarization
- **Undo Functionality**: Undo last operation on a note (with history management)

### **Templates System**
- **View Templates**: List and preview available templates
- **Create Templates**: Create new markdown templates by typing/pasting
- **Upload Templates**: Upload existing .md files as templates
- **Batch Upload**: Upload all .md files from a folder as templates
- **Delete Templates**: Remove templates from the system

### **AI Integration (ChatGPT/GPT)**
- **GPT Write**: Ask ChatGPT questions and optionally save responses to notes
- **Note Editing**: AI-assisted note editing with multiple save options
- **Note Analysis**: Send notes to GPT for analysis or summarization
- **Configurable Model**: Support for different GPT models (default: gpt-4o)

### **Search & Indexing**
- **General Search**: Search notes by title, type, system, or tags
  - Example: `search spell system:dnd-5e`
- **Vault Indexing**: Build searchable index of all vault notes
- **SRD Indexing**: Specialized indexing for SRD (System Reference Document) files
  - Indexes files in `/SRDs/` directory
  - Extracts title, system, tags (frontmatter + inline), and summary
- **SRD Search**: Advanced search for SRD files with filters
  - `search-srd spell tag:magic system:dnd-5e`
  - Supports: `tag:`, `system:`, `name:` filters
  - **Fuzzy Ranking**: Relevance-based result ordering
  - **Contextual Snippets**: Shows matching content with context around query terms
  - **Content Sampling**: Indexes up to 1000 characters for snippet generation

### **Tag Management**
- **Add Tags**: Add tags to notes (frontmatter or inline)
- **Remove Tags**: Remove tags from notes
- **List Tags**: View all tags in current vault with note counts
- **Tag Search**: Find all notes with a specific tag
- **Autocomplete**: Tag autocompletion in command line

### **PDF Processing**
- **PDF to Markdown**: Convert PDF files to markdown format
- **Batch PDF Conversion**: Convert multiple PDFs from a folder
- **Mapping Support**: Custom YAML mapping rules for PDF structure
- **Multiple Implementations**: Legacy and modern PDF processing tools
- **Send to Vault**: Convert PDFs and automatically save to current vault
- **Auto-numbering**: Automatic numbered copies for duplicate files

### **Session Scheduling**
- **Session Calendar**: Generate .ics calendar invite files for TTRPG sessions
- **Share Messages**: Create easy-to-share calendar links
- **Time Zone Support**: Time zone handling for session scheduling
- **Session Reminders**: Automatic reminders for upcoming TTRPG sessions
  - Configurable reminder window (default: 24 hours before session)
  - Checks every hour for upcoming sessions
  - Supports future Discord/email/desktop notification integration

### **Background Automation**
- **Job Scheduler**: Background task scheduling system
- **Periodic Tasks**: Run tasks at specified intervals
- **Scheduler Control**: Start, stop, and manage scheduled jobs
- **Job Registration**: Register and manage background jobs
- **Default Jobs**: Pre-configured automation jobs including:
  - **Vault Backup**: Automatic vault backups every 24 hours (dated zip files)
  - **Template Sync**: Periodic template synchronization from remote sources
  - **SRD Index Rebuild**: Automatic SRD index updates every 12 hours
  - **Session Reminders**: Hourly checks for upcoming session reminders
  - **Vault Sync**: Periodic sync with Obsidian configuration (every 10 minutes)

### **Campaign Management** (NEW)
- **Campaign Creation**: Create structured campaign folders with entity organization
- **Folder Structure**: Organized campaign directories:
  - `Campaigns/<Name>/_campaign.md` - Campaign overview file
  - `Party/` - Player character files
  - `NPCs/<Attitude>/` - NPC files organized by attitude (Ally, Friendly, Neutral, Adversarial, Antagonist)
  - `Locations/` - Location files
  - `Sessions/` - Session notes directory
- **Entity Creation**: Create PCs, NPCs, and locations with proper YAML frontmatter
- **YAML Metadata**: Automatic frontmatter generation for all campaign entities

### **History & Undo**
- **Operation History**: Track all note modifications
- **Undo Support**: Restore notes to previous state (convenience wrapper)
- **Version History**: Explicit version history management:
  - **List History**: View numbered history entries for any note
  - **Restore Versions**: Restore specific versions by index
  - **History Preservation**: Restore operations preserve history (unlike undo)
- **Per-Note History**: Undo and history operations specific to individual notes
- **Automatic Backups**: Backup notes before modifications

---

## 📦 Module Structure

### **Core Modules** (`core/`)
- **`assistant.py`**: Main entry point and command loop
- **`config.py`**: Centralized configuration management (replaces globals)
  - Extended with: `templates_remote_url`, `templates_local_path`, `session_reminder_hours_before`
- **`gpt.py`**: GPT/ChatGPT API integration
- **`notes.py`**: Note reading, listing, and management
- **`vaults.py`**: Vault management and Obsidian sync
- **`templates.py`**: Template management system
  - Extended with: `sync_templates_from_remote()` function (placeholder for future GitHub/HTTP integration)
- **`search_index.py`**: General vault search and indexing
- **`srd_index.py`**: SRD-specific indexing and search
  - Enhanced with: fuzzy ranking, contextual snippets, content sampling
- **`tags.py`**: Tag management and extraction
- **`history.py`**: Undo/history functionality
  - Extended with: `list_history()`, `restore_version()` methods
- **`pdf.py`**: PDF conversion utilities
- **`session_scheduler.py`**: TTRPG session scheduling
  - Extended with: `get_next_session_info()` for reading session data from JSON/ICS files
- **`campaigns.py`**: Campaign management system (NEW)
- **`scheduler.py`**: Background job scheduler (shim)
- **`audio.py`**: Audio transcription scaffold

### **Automation** (`automation/`)
- **`job.py`**: Job dataclass definitions
- **`task_scheduler.py`**: Task scheduler implementation
  - Extended with: `register_backup_job()`, `register_template_sync_job()`, `register_srd_index_job()`, `register_session_reminder_job()`
- **`jobs.py`**: Concrete job implementations (NEW)
  - `backup_vault()` - Vault backup job
  - `sync_templates_job()` - Template sync job
  - `rebuild_srd_index_job()` - SRD index rebuild job
  - `session_reminder_job()` - Session reminder job

### **PDF Tools** (`pdf_tools/`)
- **`pdf_to_md.py`**: Modern PDF to markdown conversion
- **`cleaning.py`**: Markdown cleaning utilities
- **`ocr_utils.py`**: OCR processing utilities

---

## 🆕 Recent Changes & Additions

### **1. Automation Job System** (`automation/jobs.py`)
**Added:** Comprehensive automation job implementations

**Vault Backup Job:**
- Automatic vault backups every 24 hours
- Creates dated zip files: `backups/YYYY-MM-DD/vault-backup-YYYY-MM-DD_HHMMSS.zip`
- Maintains only last N backups (default: 7)
- On-demand backup: `schedule-backup-run-now`

**Template Sync Job:**
- Scaffolded for future GitHub/HTTP template synchronization
- Configurable remote URL in settings
- Runs every 6 hours when configured
- On-demand sync: `template-sync-now`

**SRD Index Rebuild Job:**
- Automatic SRD index rebuilds every 12 hours
- Only runs if SRDs directory exists
- On-demand rebuild: `srd-index-run-now`

**Session Reminder Job:**
- Checks for upcoming sessions every hour
- Configurable reminder window (default: 24 hours)
- Prints reminders when session is within window
- On-demand check: `session-reminder-run-now`

---

### **2. Campaign Management System** (`core/campaigns.py`)
**Added:** Complete campaign organization system

**Features:**
- Structured campaign folder hierarchy
- Entity creation with proper YAML frontmatter
- Organized NPC storage by attitude

**Campaign Structure:**
```
Campaigns/<CampaignName>/
  _campaign.md          # Campaign overview (status: active)
  Party/                # Player character files
  NPCs/
    Ally/              # Friendly NPCs
    Friendly/
    Neutral/
    Adversarial/
    Antagonist/        # Main antagonists
  Locations/           # Location files
  Sessions/            # Session notes directory
```

**New Commands:**
- `campaign-create <name>` - Create a new campaign with full folder structure
- `campaign-add-pc <campaign> <name>` - Add a player character
- `campaign-add-npc <campaign> <attitude> <name>` - Add an NPC (attitude: ally, friendly, neutral, adversarial, antagonist)
- `campaign-add-location <campaign> <name>` - Add a location

**Usage Examples:**
```
campaign-create "The Lost Mines"
campaign-add-pc "The Lost Mines" "Aragorn"
campaign-add-npc "The Lost Mines" friendly "Innkeeper Bob"
campaign-add-location "The Lost Mines" "Phandalin"
```

---

### **3. Enhanced SRD Search** (`core/srd_index.py`)
**Upgraded:** Advanced search with fuzzy ranking and snippets

**New Features:**
- **Fuzzy Relevance Scoring**: Results ranked by relevance
  - Exact matches: 10.0 points
  - Starts-with matches: 5.0 points
  - Contains matches: 1.0+ points (position-based)
- **Contextual Snippets**: Shows matching content with surrounding context
- **Content Sampling**: Indexes up to 1000 characters per file for snippet generation
- **Improved Ranking**: Title matches weighted higher than tag/content matches

**Enhanced Function:**
- `search_srd_index()`: New function with fuzzy ranking and snippet generation
- Preserves backward compatibility with existing `search_index()` function

**Example Output:**
- Ranked results with relevance scoring
- Snippets showing context around query matches
- Improved result ordering (most relevant first)

---

### **4. Version History System** (`core/history.py`)
**Extended:** Explicit version history management

**New Features:**
- **History Listing**: View numbered history entries for any note
- **Selective Restoration**: Restore specific versions by index
- **History Preservation**: Restore operations don't remove history entries
- **Path Properties**: Easy access to Path and datetime objects via properties

**New Methods:**
- `list_history(note_path, limit=10)`: Returns recent history entries
- `restore_version(entry)`: Restores from specific backup without removing from history

**New Commands:**
- `history-list <note> [limit]` - Show numbered history entries (default: 10)
- `history-restore <note> <index>` - Restore specific version by index

**Usage Examples:**
```
history-list MyNote        # Show last 10 versions
history-list MyNote 20     # Show last 20 versions
history-restore MyNote 3   # Restore version #3
undo MyNote                # Quick restore of most recent (unchanged)
```

**Note:** `undo` command remains as a convenience wrapper that restores the most recent version.

---

### **5. Session Reminder System** (`core/session_scheduler.py`)
**Extended:** Automatic session reminders

**New Features:**
- **Session Info Retrieval**: `get_next_session_info()` reads session data from JSON/ICS files
- **Automatic Reminders**: Hourly checks for upcoming sessions
- **Configurable Window**: Reminder hours before session (default: 24 hours)
- **Dual Storage**: JSON metadata file (preferred) + ICS file (fallback)

**Configuration:**
- `session_reminder_hours_before`: Hours before session to send reminder (default: 24)
- Stored in `settings.json` for persistence

**Future Ready:**
- Structured for Discord/email/desktop notification integration
- Clean separation between reminder logic and notification delivery

---

### **6. SRD Indexing Module** (`core/srd_index.py`)
**Original Addition:** Specialized indexing system for SRD documents

**Features:**
- Recursively indexes markdown files in `/SRDs/` directory
- Extracts YAML frontmatter (title, system, tags)
- Extracts inline `#tags` from content
- Extracts first paragraph as summary
- Extracts content sample (up to 1000 chars) for snippet generation
- Saves JSON index to `.ceres_index/records.json`

**Commands:**
- `srd-index`: Build/rebuild SRD index
- `search-srd <query>`: Search SRD files with advanced filters and fuzzy ranking

**Usage Examples:**
```
srd-index
search-srd spell
search-srd tag:magic system:dnd-5e
search-srd name:fireball
```

---

### **7. Audio Transcription Scaffold** (`core/audio.py`)
**Previous Addition:** Foundation module for future audio transcription features

**Components:**
- `Transcript` dataclass: Stores transcribed text, source, timestamp, metadata
- `transcribe_audio()`: Placeholder for audio file transcription
- `attach_transcript_to_note()`: Attach transcripts to markdown notes with formatted sections

**Future Integration Points:**
- OpenAI Whisper API
- Discord bot integration
- Local microphone recording
- Multiple audio formats (MP3, WAV, OGG, etc.)

**Note:** This is a scaffold - no actual transcription implemented yet. Ready for future development.

---

## 📋 Complete Command Reference

### **Basic Commands**
- `exit` - Exit the assistant
- `help` - Show help message
- `debug` - Print diagnostic information

### **Vault Commands**
- `vaults` - List available vaults
- `switch [name/number]` - Switch to different vault
- `addvault <path>` - Add a new vault
- `ignorevault <name>` - Ignore a vault from auto-import
- `unignorevault <name>` - Stop ignoring a vault
- `showignored` - Show ignored vaults

### **Note Commands**
- `read <filename>` - Read a markdown file
- `list [folder]` - List markdown files (optionally filtered by folder)
- `tree` - Show vault structure as tree
- `createnote` - Create a new note (from template or blank)
- `editnote` - Edit a note with ChatGPT
- `send <note>` - Send note to ChatGPT for analysis
- `undo [note_path]` - Undo last operation on note (convenience wrapper)
- `history-list <note> [limit]` - List version history for a note
- `history-restore <note> <index>` - Restore specific version by index

### **Template Commands**
- `showtemplates` - List and preview templates
- `createtemplate` - Create a new template
- `uploadtemplate` - Upload .md file as template
- `uploadalltemplates` - Upload all .md files from folder as templates
- `deletetemplate` - Delete a template

### **AI/GPT Commands**
- `gptwrite NoteName.md: prompt text` - Ask ChatGPT and optionally save to note
- `editnote` - AI-assisted note editing

### **Search Commands**
- `search <query>` - Search notes (e.g., `search spell system:dnd-5e`)
- `index` - Build/rebuild vault search index
- `srd-index` - Build/rebuild SRD index
- `search-srd <query>` - Search SRD files with filters

### **Tag Commands**
- `tag-add <note> <tag>` - Add tag to note
- `tag-remove <note> <tag>` - Remove tag from note
- `tag-list` - List all tags in current vault
- `tag-notes <tag>` - Find all notes with a tag

### **PDF Commands**
- `pdf2md <PDF_PATH> [--map maps/dnd5e.yaml]` - Convert single PDF (legacy)
- `pdfbatch <PDF_FOLDER> [--map maps/dnd5e.yaml]` - Convert folder of PDFs (legacy)
- `pdf-convert <PDF_PATH> [--map maps/dnd5e.yaml]` - Convert single PDF (modern)
- `pdf-batch <PDF_FOLDER> [--map maps/dnd5e.yaml]` - Convert folder of PDFs (modern)
- `pdf-send-to-vault --input <PDF_PATH or FOLDER>` - Convert and save to vault

### **Campaign Commands** (NEW)
- `campaign-create <name>` - Create a new campaign with folder structure
- `campaign-add-pc <campaign> <name>` - Add a player character to campaign
- `campaign-add-npc <campaign> <attitude> <name>` - Add an NPC to campaign
- `campaign-add-location <campaign> <name>` - Add a location to campaign

### **Session Commands**
- `session-schedule` - Schedule next TTRPG session and generate calendar invite
- `session-reminder-run-now` - Check for upcoming sessions immediately

### **Scheduler Commands**
- `schedule-start` - Start background job scheduler
- `schedule-stop` - Stop scheduler
- `schedule-run-once` - Run pending jobs once (for testing)
- `schedule-status` - Show scheduler status and registered jobs
- `schedule-backup-run-now` - Run vault backup job immediately
- `template-sync-now` - Run template sync job immediately
- `srd-index-run-now` - Run SRD index rebuild job immediately

### **System Commands**
- `reset` - Reset all settings to first-launch state
- `debug` - Print diagnostic information

---

## 🏗️ Architecture Highlights

### **Design Principles**
- **No Global Variables**: All state managed through Config object
- **Dependency Injection**: Functions receive dependencies as parameters
- **Modular Structure**: Single-purpose modules with clear responsibilities
- **Type Hints**: Full type annotations throughout codebase
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Backward Compatibility**: Maintains compatibility with existing functionality

### **Configuration Management**
- Centralized `Config` dataclass
- Settings persisted to `settings.json`
- Vaults stored in `vaults.json`
- Environment variables for API keys (`variables.env`)

### **Data Storage**
- `.gm_assistant_history` - Command history file
- `.ceres_history/` - Note undo history directory
  - `history_index.json` - History index with backup metadata
  - `*.bak` - Backup files for notes
- `.ceres_index/records.json` - SRD search index (with content samples)
- `backups/YYYY-MM-DD/` - Vault backup zip files
- `exports/` - Export directory
  - `next_session.ics` - Current session calendar file
  - `next_session.json` - Session metadata (for reminders)
  - `session_share_message.txt` - Session share message
- `settings.json` - Application settings (includes: templates_remote_url, templates_local_path, session_reminder_hours_before)
- `vaults.json` - Vault configuration

---

## 🔧 Technical Stack

- **Python**: 3.11+
- **Key Libraries**:
  - `prompt_toolkit` - Interactive terminal UI
  - `openai` - GPT API integration
  - `pyyaml` - YAML parsing
  - `python-dotenv` - Environment variable management
  - Custom modules for PDF processing, OCR, etc.

---

## 📝 Development Notes

### **Code Standards**
- Google-style docstrings
- Type hints required
- 4-space indentation
- No circular imports
- Pure functions where possible

### **File Organization**
- Core functionality in `core/` directory
- Automation engine in `automation/` directory
- PDF tools in `pdf_tools/` directory
- Main entry point: `assistant.py`

---

## 🚀 Future Roadmap (Scaffolded)

### **Audio Transcription** (Foundation Ready)
- OpenAI Whisper integration
- Discord bot integration
- Local microphone support
- Multi-format audio support

### **Potential Enhancements**
- Webhook integrations
- Cloud storage sync
- Advanced search algorithms
- Plugin system
- GUI interface option

---

---

## 📅 Change Log

### **Session: Automation & Campaign Management Updates**

**New Modules:**
- `automation/jobs.py` - Concrete job implementations for scheduled tasks
- `core/campaigns.py` - Campaign management system

**Enhanced Modules:**
- `core/history.py` - Extended with version history listing and selective restoration
- `core/srd_index.py` - Enhanced search with fuzzy ranking and contextual snippets
- `core/session_scheduler.py` - Added session reminder functionality
- `core/templates.py` - Added template sync scaffold
- `core/config.py` - Added configuration fields for templates and session reminders
- `automation/task_scheduler.py` - Added job registration functions for all new jobs
- `assistant.py` - Added 10+ new CLI commands

**New Automation Jobs:**
1. Vault Backup (24-hour interval)
2. Template Sync (6-hour interval, conditional)
3. SRD Index Rebuild (12-hour interval, conditional)
4. Session Reminder (1-hour interval)

**New Campaign Features:**
- Campaign folder structure creation
- PC/NPC/Location entity creation with frontmatter
- Organized NPC storage by attitude

**New History Features:**
- Explicit version listing
- Selective version restoration
- History preservation on restore

**Enhanced SRD Search:**
- Fuzzy relevance scoring
- Contextual snippet generation
- Content sampling for better matches

---

*Last Updated: Automation & Campaign Management Session*  
*Project Ceres - GM Assistant for Obsidian Vaults*



