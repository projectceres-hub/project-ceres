# Project Ceres Pantheon

The Pantheon architecture organizes Project Ceres subsystems by the twelve helper gods of Ceres, each representing a domain of Roman agriculture and a corresponding area of functionality in the GM Assistant.

## Vervactor – Campaign Creation & Vault Setup

- **"He who ploughs"**
- **Roman role:** Prepares the field for planting by breaking up the soil
- **Ceres role:** Responsible for campaign creation, initial vault structure, and top-level organization. Modules: `core/campaigns.py` (campaign creation), vault initialization, folder structure setup.

## Reparator – Template System & Preparation

- **"He who prepares"**
- **Roman role:** Prepares the soil after ploughing, making it ready for seeds
- **Ceres role:** Manages template system, formatting tools, and content preparation. Modules: `core/templates.py`, template creation and management, content formatting utilities.

## Imporcitor – Bulk Import

- **"He who harrows"**
- **Roman role:** Breaks up clods and levels the field after ploughing
- **Ceres role:** Handles bulk import operations, batch processing, and large-scale data ingestion. Modules: PDF→MD batch processing, SRD imports, bulk file operations.

## Insitor – Note Creation & Seeding

- **"He who sows"**
- **Roman role:** Plants seeds in the prepared soil
- **Ceres role:** Creates and seeds notes, generates initial content. Modules: `core/notes.py` (createnote), NPC/session note generation, initial content creation.

## Obarator – Tags & Metadata

- **"He who covers"**
- **Roman role:** Covers seeds with soil after planting
- **Ceres role:** Manages tags, metadata, frontmatter, and indexing information. Modules: `core/tags.py`, tag commands, frontmatter shaping, indexing metadata.

## Occator – Search & SRD Indexing

- **"He who harrows"**
- **Roman role:** Smooths and levels the field surface
- **Ceres role:** Provides search functionality and SRD indexing. Modules: `core/search_index.py`, `core/srd_index.py`, search commands, index building.

## Serritor – Automation & Background Jobs

- **"He who weeds"**
- **Roman role:** Removes weeds and maintains the field during growth
- **Ceres role:** Handles automation, scheduled jobs, and background tasks. Modules: `core/scheduler.py`, `automation/`, task scheduling, recurring jobs.

## Subruncinator – Cleanup & Maintenance

- **"He who prunes"**
- **Roman role:** Removes unwanted growth and maintains plant health
- **Ceres role:** Performs cleanup, maintenance, and removal of temporary or unwanted data. Modules: cache cleaning, temp file removal, vault linting, maintenance tasks.

## Messor – Session Harvesting

- **"He who reaps"**
- **Roman role:** Harvests the mature crops
- **Ceres role:** Collects and processes session data from various sources. Modules: `core/fgu_integration.py`, `core/audio.py`, session logs, Discord audio imports, FGU log processing.

## Convector – Data Transport

- **"He who carries"**
- **Roman role:** Transports harvested crops from field to storage
- **Ceres role:** Handles data transport and import pipelines from external sources into Ceres. Modules: Import pipelines, data transformation, format conversion utilities. Routes VoiceCommands created by the wake word parser (wake words: "Veras" and "Chroma"). Extracts and routes VoiceCommands discovered in transcript files (via the "Veras" or "Chroma" wake words).

## Conditor – Storage, Backups, History

- **"He who stores"**
- **Roman role:** Stores harvested crops in granaries
- **Ceres role:** Manages storage, backups, history, and versioning. Modules: `core/history.py`, backup jobs, snapshots, undo functionality, version control.

## Promitor – Distribution & Reports

- **"He who distributes"**
- **Roman role:** Distributes stored grain to those who need it
- **Ceres role:** Generates summaries, exports, reports, and shareable artifacts. Modules: Calendar exports, session summaries, shareable message generation, distribution utilities.

---

## Architecture Notes

This pantheon structure provides a conceptual framework for organizing Project Ceres modules. Each god's domain represents a distinct phase in the agricultural cycle, mirrored in the GM's workflow from campaign setup through session management to distribution of game materials.

Modules will eventually be organized under these domains, but the current codebase structure remains intact until migration is planned and executed.

