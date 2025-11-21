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
  - Fuzzy matching by default

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

### **Background Automation**
- **Job Scheduler**: Background task scheduling system
- **Periodic Tasks**: Run tasks at specified intervals
- **Scheduler Control**: Start, stop, and manage scheduled jobs
- **Job Registration**: Register and manage background jobs
- **Default Jobs**: Pre-configured automation jobs

### **History & Undo**
- **Operation History**: Track all note modifications
- **Undo Support**: Restore notes to previous state
- **Per-Note History**: Undo specific to individual notes
- **Automatic Backups**: Backup notes before modifications

---

## 📦 Module Structure

### **Core Modules** (`core/`)
- **`assistant.py`**: Main entry point and command loop
- **`config.py`**: Centralized configuration management (replaces globals)
- **`gpt.py`**: GPT/ChatGPT API integration
- **`notes.py`**: Note reading, listing, and management
- **`vaults.py`**: Vault management and Obsidian sync
- **`templates.py`**: Template management system
- **`search_index.py`**: General vault search and indexing
- **`srd_index.py`**: SRD-specific indexing and search (NEW)
- **`tags.py`**: Tag management and extraction
- **`history.py`**: Undo/history functionality
- **`pdf.py`**: PDF conversion utilities
- **`session_scheduler.py`**: TTRPG session scheduling
- **`scheduler.py`**: Background job scheduler (shim)
- **`audio.py`**: Audio transcription scaffold (NEW)

### **Automation** (`automation/`)
- **`job.py`**: Job dataclass definitions
- **`task_scheduler.py`**: Task scheduler implementation

### **PDF Tools** (`pdf_tools/`)
- **`pdf_to_md.py`**: Modern PDF to markdown conversion
- **`cleaning.py`**: Markdown cleaning utilities
- **`ocr_utils.py`**: OCR processing utilities

---

## 🆕 Recent Changes & Additions

### **1. SRD Indexing Module** (`core/srd_index.py`)
**Added:** New specialized indexing system for SRD documents

**Features:**
- Recursively indexes markdown files in `/SRDs/` directory
- Extracts YAML frontmatter (title, system, tags)
- Extracts inline `#tags` from content
- Extracts first paragraph as summary
- Saves JSON index to `.ceres_index/records.json`

**New Commands:**
- `srd-index`: Build/rebuild SRD index
- `search-srd <query>`: Search SRD files with advanced filters

**Usage Examples:**
```
srd-index
search-srd spell
search-srd tag:magic system:dnd-5e
search-srd name:fireball
```

---

### **2. Audio Transcription Scaffold** (`core/audio.py`)
**Added:** Foundation module for future audio transcription features

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
- `undo [note_path]` - Undo last operation on note

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

### **Session Commands**
- `session-schedule` - Schedule next TTRPG session and generate calendar invite

### **Scheduler Commands**
- `schedule-start` - Start background job scheduler
- `schedule-stop` - Stop scheduler
- `schedule-run-once` - Run pending jobs once (for testing)
- `schedule-status` - Show scheduler status and registered jobs

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
- `.ceres_index/records.json` - SRD search index
- `settings.json` - Application settings
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

*Last Updated: Current Session*  
*Project Ceres - GM Assistant for Obsidian Vaults*



