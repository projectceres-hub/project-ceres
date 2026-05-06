"""
FGU standalone XML export from Obsidian notes (Phase 5 Item 3b).

Reads notes with ``fgu_entity: true`` YAML frontmatter and writes one importable
XML file. Never mutates campaign db.xml.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_FM_PATTERN = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def read_fgu_frontmatter(note_path: Path) -> Optional[Dict[str, Any]]:
    """Load YAML frontmatter from a markdown note if ``fgu_entity`` is true.

    Args:
        note_path: Path to a ``.md`` file.

    Returns:
        Parsed frontmatter dict, or None if missing / invalid / not an FGU note.
    """
    try:
        text = note_path.read_text(encoding="utf-8")
        m = _FM_PATTERN.match(text)
        if not m:
            return None
        fm: Dict[str, Any] = yaml.safe_load(m.group(1)) or {}
        if not fm.get("fgu_entity"):
            return None
        return fm
    except Exception:
        return None


def _sub(parent: ET.Element, tag: str, text: str = "", type_attr: str = "string") -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.set("type", type_attr)
    if text:
        el.text = str(text)
    return el


def _id_child(parent: ET.Element, index: int) -> ET.Element:
    return ET.SubElement(parent, f"id-{index:05d}")


def _skills_to_string(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        parts: List[str] = []
        for item in val:
            if isinstance(item, dict):
                parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "; ".join(parts)
    return str(val)


def _npc_5e_to_xml(fm: Dict[str, Any], record_id: int) -> ET.Element:
    """Build an FGU-style NPC id-* element from 5E frontmatter."""
    node = ET.Element(f"id-{record_id:05d}")
    _sub(node, "name", str(fm.get("name", "")))
    _sub(node, "type", str(fm.get("creature_type", "")))
    _sub(node, "size", str(fm.get("size", "")))
    _sub(node, "alignment", str(fm.get("alignment", "")))
    _sub(node, "cr", str(fm.get("cr", "")))
    xp = fm.get("xp", 0)
    _sub(node, "xp", str(xp), "number")
    _sub(node, "speed", str(fm.get("speed", "")))
    _sub(node, "senses", str(fm.get("senses", "")))
    _sub(node, "languages", str(fm.get("languages", "")))
    hp = fm.get("hp", 0)
    _sub(node, "hp", str(hp), "number")
    ac = fm.get("ac", 0)
    _sub(node, "ac", str(ac), "number")
    _sub(node, "skills", _skills_to_string(fm.get("skills")))
    _sub(node, "damageimmunities", str(fm.get("damage_immunities", "")))
    _sub(node, "damageresistances", str(fm.get("damage_resistances", "")))
    _sub(node, "conditionimmunities", str(fm.get("condition_immunities", "")))

    abilities = fm.get("abilities") or {}
    abilities_node = ET.SubElement(node, "abilities")
    mapping = (
        ("str", "strength"),
        ("dex", "dexterity"),
        ("con", "constitution"),
        ("int", "intelligence"),
        ("wis", "wisdom"),
        ("cha", "charisma"),
    )
    for short, long in mapping:
        ab = abilities.get(short, {})
        if not isinstance(ab, dict):
            ab = {}
        ab_node = ET.SubElement(abilities_node, long)
        _sub(ab_node, "score", str(ab.get("score", 10)), "number")
        _sub(ab_node, "save", str(ab.get("save", 0)), "number")

    for fm_key, xml_tag in (
        ("actions", "actions"),
        ("traits", "traits"),
        ("reactions", "reactions"),
        ("legendary_actions", "legendaryactions"),
    ):
        items = fm.get(fm_key) or []
        if not isinstance(items, list) or not items:
            continue
        parent_node = ET.SubElement(node, xml_tag)
        for i, act in enumerate(items, 1):
            if not isinstance(act, dict):
                continue
            row = _id_child(parent_node, i)
            _sub(row, "name", str(act.get("name", "")))
            _sub(row, "desc", str(act.get("description", "")), "formattedtext")

    return node


def _entity_generic_to_xml(fm: Dict[str, Any], record_id: int) -> ET.Element:
    """Write scalar frontmatter keys as typed leaf elements."""
    node = ET.Element(f"id-{record_id:05d}")
    skip = {
        "fgu_entity",
        "fgu_system",
        "fgu_campaign",
        "fgu_source_file",
        "fgu_record_class",
        "fgu_id",
        "tags",
        "abilities",
        "actions",
        "traits",
        "reactions",
        "legendary_actions",
        "bonus_actions",
        "classes",
        "inventory",
        "skills",
    }
    for key, val in fm.items():
        if key in skip or isinstance(val, (dict, list)):
            continue
        t = "number" if isinstance(val, (int, float)) and not isinstance(val, bool) else "string"
        _sub(node, key, str(val), t)
    return node


def entity_to_fgu_xml(fm: Dict[str, Any], record_id: int) -> ET.Element:
    """Dispatch to a ruleset/record-class XML builder."""
    system = fm.get("fgu_system", "unknown")
    record_class = fm.get("fgu_record_class", "unknown")
    if system == "dnd5e" and record_class == "npc":
        return _npc_5e_to_xml(fm, record_id)
    return _entity_generic_to_xml(fm, record_id)


def read_fgu_notes_in_vault(vault_path: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    """Find all ``*.md`` files under *vault_path* with FGU frontmatter."""
    results: List[Tuple[Path, Dict[str, Any]]] = []
    root = Path(vault_path)
    if not root.is_dir():
        return results
    for md_file in root.rglob("*.md"):
        fm = read_fgu_frontmatter(md_file)
        if fm is not None:
            results.append((md_file, fm))
    return results


def export_entities_to_xml(
    note_paths: List[Path],
    output_path: Path,
) -> Tuple[int, List[str]]:
    """Write a standalone FGU-importable XML file from note paths.

    Args:
        note_paths: Markdown files to read (typically from read_fgu_notes_in_vault).
        output_path: Destination ``.xml`` path.

    Returns:
        (entity_count, error_messages)
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    errors: List[str] = []

    for note_path in note_paths:
        fm = read_fgu_frontmatter(note_path)
        if fm is None:
            errors.append(f"No fgu_entity frontmatter: {note_path.name}")
            continue
        rc = str(fm.get("fgu_record_class", "unknown"))
        groups.setdefault(rc, []).append(fm)

    root_el = ET.Element("root")
    root_el.set("release", "8.1|CoreRPG:7")
    total = 0

    for record_class, fm_list in groups.items():
        section_el = ET.SubElement(root_el, record_class)
        for i, fm in enumerate(fm_list, 1):
            try:
                node = entity_to_fgu_xml(fm, i)
                orig_id = fm.get("fgu_id")
                if orig_id and re.match(r"^id-\d{5}$", str(orig_id)):
                    node.tag = str(orig_id)
                section_el.append(node)
                total += 1
            except Exception as exc:
                errors.append(f"{fm.get('name', '?')}: {exc}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root_el)
    ET.indent(tree, space="\t")
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True)
    return total, errors
