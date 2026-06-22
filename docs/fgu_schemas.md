# FGU Schema Baseline

This document records the Fantasy Grounds Unity XML mapping currently implemented by Project Ceres. It is a baseline, not a complete validation matrix across every ruleset export shape.

## Source and Detection

- Campaign source: `<campaign>/db.xml`
- Ruleset detection: `pantheon.messor.fgu_import.detect_ruleset`
- Supported normalized rulesets: `dnd5e`, `swade`, `swnr`, `generic`
- Import entry point: `pantheon.messor.fgu_import.import_campaign_entities`
- Export entry point: `pantheon.messor.fgu_export.export_entities_to_xml`

## Shared Frontmatter

Every imported FGU note includes:

| Frontmatter key | Meaning |
|---|---|
| `fgu_entity` | Always `true` for FGU-managed notes |
| `fgu_system` | Normalized ruleset |
| `fgu_campaign` | Source campaign folder name |
| `fgu_source_file` | Usually `db.xml` |
| `fgu_record_class` | `npc`, `pc`, `item`, `encounter`, or `note` |
| `fgu_id` | Source XML record id when available |
| `name` | Display name |
| `system` | Ruleset-facing system key |

## Implemented Import Sections

| Entity | XML sections checked | Vault folder |
|---|---|---|
| NPC | `npcdata`, `npc`, `npcs` | `Campaigns/<campaign>/NPCs` |
| PC | `charsheet`, `character`, `characters`, `pc` | `Campaigns/<campaign>/PCs` |
| Item | `item`, `items`, `itemdata`, `equipment` | `Campaigns/<campaign>/Items` |
| Encounter | `encounter`, `encounters`, `map` | `Campaigns/<campaign>/Encounters` |
| Note | `note`, `notes`, `story`, `referencetextdata` | `Campaigns/<campaign>/Notes` |

## D&D 5E Baseline

For `dnd5e`, NPCs, PCs, and items reuse `FGUCampaignParser` dataclasses from `pantheon.messor.fgu_character`. Encounters and notes fall back to the generic XML path.

| Entity | Key fields |
|---|---|
| NPC | `creature_type`, `size`, `alignment`, `cr`, `xp`, `speed`, `senses`, `languages`, `hp`, `ac`, `abilities`, `saving_throws`, `skills`, `actions`, `traits`, `reactions`, `legendary_actions` |
| PC | `player`, `race`, `class`, `level`, `background`, `alignment`, `hp`, `ac`, `speed`, `abilities`, `saving_throws`, `skills`, `features`, `equipment`, `spells` |
| Item | `item_type`, `subtype`, `rarity`, `weight`, `value`, `attunement`, `description` |

## Generic, SWADE, and OSR/SWN Baseline

Generic and OSR/SWN imports use direct XML reads. SWADE has specialized NPC and PC handling for attributes, skills, edges, hindrances, special abilities, and gear.

| Entity | Key fields |
|---|---|
| Generic NPC | `hd`, `hp`, `ac`, `attacks`, `saves`, `morale`, `movement`, `special`, `xp` |
| Generic PC | `player`, `class`, `level`, `hp`, `ac`, `saving_throws`, `skills`, `equipment` |
| Generic Item | `item_type`, `weight`, `value`, `rarity`, `description`, `properties` |
| SWADE NPC | `wild_card`, `pace`, `parry`, `toughness`, `attributes`, `skills`, `edges`, `hindrances`, `special_abilities`, `gear` |
| SWADE PC | `player`, `race`, `rank`, `derived_stats`, `attributes`, `skills`, `edges`, `hindrances`, `gear` |

## Export Baseline

Standalone XML export groups notes by `fgu_record_class` and never mutates an FGU campaign `db.xml` in place. D&D 5E NPCs have a targeted XML writer; other record classes export scalar frontmatter as generic XML leaves.

## Known Gaps

- Real campaign sample validation is still needed for 5E, SWADE, and SWN/OSR.
- Location-specific records are currently represented through generic encounter/note import paths rather than a dedicated `location` parser.
- Export is intentionally conservative and should be tested inside Fantasy Grounds before any in-place merge feature is considered.
