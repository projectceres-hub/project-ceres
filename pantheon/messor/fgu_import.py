"""
FGU campaign entity import for Project Ceres (Phase 5 Item 3b).

Parses Fantasy Grounds Unity campaign XML (db.xml) and converts NPCs, PCs,
items, encounters, and notes into NoteSpec objects suitable for create_note().

Design decisions
----------------
- ``FGUEntityParser`` wraps ``FGUCampaignParser`` (from fgu_character.py) and
  caches one parser instance per resolved campaign path.
- ``_notespec_to_markdown_file`` pre-serialises nested YAML frontmatter via
  ``yaml.safe_dump`` into the note body so that ``create_note`` (which only
  emits scalar frontmatter) receives ``frontmatter=None``.
- ``_iter_records`` unwraps one ``<category>`` level from FGU XML.
- SWADE attributes: ``*Adjustment``/``*Mod`` sibling nodes sit next to the die
  element, not inside it.
- For 5E entities the existing ``FGUCampaignParser`` dataclasses are reused;
  SWADE/OSR fall back to a lightweight generic path.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from core.config import Config

from pantheon.insitor.note_creator import NoteSpec, create_note

# ---------------------------------------------------------------------------
# Ruleset detection
# ---------------------------------------------------------------------------

_RULESET_TOKENS: List[Tuple[str, str]] = [
    ("dnd5e", "dnd5e"),
    ("5e",    "dnd5e"),
    ("swade", "swade"),
    ("savage worlds", "swade"),
    ("swnr",  "swnr"),
    ("swr",   "swnr"),
    ("stars without number", "swnr"),
    ("corerpg", "generic"),
    ("corerPG", "generic"),
]


def detect_ruleset(campaign_path: Path) -> str:
    """Detect the ruleset for an FGU campaign folder.

    Reads the ``release`` attribute on the XML root (e.g.
    ``"8.1|dnd5e:6"``), then falls back to a ``<ruleset>`` child
    element, then ``<campaign><ruleset>``, then returns ``"generic"``.

    Args:
        campaign_path: Path to the campaign folder (must contain db.xml).

    Returns:
        Normalised ruleset string: ``"dnd5e"``, ``"swade"``,
        ``"swnr"``, or ``"generic"``.
    """
    db = Path(campaign_path) / "db.xml"
    if not db.exists():
        return "generic"

    try:
        raw = db.read_bytes()
        # Try direct parse first; if it fails, strip bad chars and retry
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            from pantheon.messor.fgu_character import _sanitize_xml
            root = ET.fromstring(_sanitize_xml(raw))
    except Exception:
        return "generic"

    def _match(text: str) -> Optional[str]:
        lower = text.lower()
        for token, norm in _RULESET_TOKENS:
            if token in lower:
                return norm
        return None

    # 1. root release attribute
    release = root.get("release", "")
    if result := _match(release):
        return result

    # 2. <ruleset> direct child
    rs_el = root.find("ruleset")
    if rs_el is not None and rs_el.text:
        if result := _match(rs_el.text):
            return result

    # 3. <campaign><ruleset>
    cam = root.find("campaign")
    if cam is not None:
        rs2 = cam.find("ruleset")
        if rs2 is not None and rs2.text:
            if result := _match(rs2.text):
                return result

    return "generic"


# ---------------------------------------------------------------------------
# XML helpers (generic; independent of fgu_character helpers)
# ---------------------------------------------------------------------------

def _txt(node: Optional[ET.Element], tag: str, default: str = "") -> str:
    """Return stripped text of *tag* child, or *default* if absent."""
    if node is None:
        return default
    child = node.find(tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _num(node: Optional[ET.Element], tag: str, default: int = 0) -> int:
    """Return int value of *tag* child, or *default* if absent/invalid."""
    raw = _txt(node, tag, "")
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return default


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


def _iter_records(section: ET.Element) -> List[ET.Element]:
    """Yield record elements, unwrapping one ``<category>`` level if present.

    FGU XML can nest records inside a single ``<category>`` wrapper.
    This function normalises both layouts into a flat list.

    Args:
        section: Parent XML element (e.g. ``<npcdata>`` or ``<npc>``).

    Returns:
        Flat list of id-* child elements.
    """
    records: List[ET.Element] = []
    for child in section:
        if child.tag == "category":
            records.extend(child)
        else:
            records.append(child)
    return records


# ---------------------------------------------------------------------------
# Shared frontmatter builder
# ---------------------------------------------------------------------------

def _base_fm(
    name: str,
    system: str,
    campaign: str,
    source_file: str,
    record_class: str,
    record_id: str,
) -> Dict[str, Any]:
    """Return the standard FGU frontmatter keys shared by all entity types."""
    return {
        "fgu_entity": True,
        "fgu_system": system,
        "fgu_campaign": campaign,
        "fgu_source_file": source_file,
        "fgu_record_class": record_class,
        "fgu_id": record_id,
        "name": name,
        "system": system,
    }


# ---------------------------------------------------------------------------
# NoteSpec serialiser — pre-renders nested YAML into body
# ---------------------------------------------------------------------------

def _notespec_to_markdown_file(
    title: str,
    folder: str,
    fm: Dict[str, Any],
    tags: Optional[List[str]] = None,
    extra_body: str = "",
) -> NoteSpec:
    """Wrap frontmatter and optional body into a NoteSpec for create_note().

    Because ``_build_frontmatter`` in ``note_creator.py`` only serialises
    scalar key/value lines, nested dicts and lists are pre-serialised here
    via ``yaml.safe_dump``.  ``create_note`` receives ``frontmatter=None``
    to avoid the flat-serialiser path.

    Args:
        title: Note title (also used as filename stem).
        folder: Vault subfolder (e.g. ``"Campaigns/Ceres/NPCs"``).
        fm: Full frontmatter dict, may contain nested structures.
        tags: Tags applied after note creation via Obarator.
        extra_body: Additional markdown appended after the title heading.

    Returns:
        :class:`NoteSpec` with pre-rendered YAML in ``body``.
    """
    yaml_block = yaml.safe_dump(
        fm,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    body = f"---\n{yaml_block}---\n\n# {title}\n\n"
    if extra_body:
        body += extra_body.strip() + "\n"

    return NoteSpec(
        title=title,
        folder=folder,
        frontmatter=None,
        body=body,
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# 5E NoteSpec builders — convert fgu_character dataclasses → NoteSpec
# ---------------------------------------------------------------------------

def _npc_5e_to_notespec(npc: Any, system: str, campaign: str) -> NoteSpec:
    """Convert an ``FGUNPC`` (from fgu_character) into a NoteSpec.

    Args:
        npc: ``FGUNPC`` dataclass instance.
        system: Ruleset string (``"dnd5e"``).
        campaign: Campaign folder name.

    Returns:
        NoteSpec ready for ``create_note()``.
    """
    fm: Dict[str, Any] = _base_fm(
        npc.name, system, campaign, "db.xml", "npc", npc.fgu_id
    )
    fm.update({
        "creature_type": npc.npc_type,
        "size": npc.size,
        "alignment": npc.alignment,
        "cr": npc.cr,
        "xp": npc.xp,
        "hp": npc.hp_max,
        "hp_formula": getattr(npc, "hp_desc", ""),
        "ac": npc.ac,
        "ac_text": getattr(npc, "ac_desc", ""),
        "speed": npc.speed,
        "senses": npc.senses,
        "languages": npc.languages,
        "abilities": {
            "str": {"score": npc.strength.score,     "bonus": npc.strength.bonus,     "save": npc.strength.save},
            "dex": {"score": npc.dexterity.score,    "bonus": npc.dexterity.bonus,    "save": npc.dexterity.save},
            "con": {"score": npc.constitution.score, "bonus": npc.constitution.bonus, "save": npc.constitution.save},
            "int": {"score": npc.intelligence.score, "bonus": npc.intelligence.bonus, "save": npc.intelligence.save},
            "wis": {"score": npc.wisdom.score,       "bonus": npc.wisdom.bonus,       "save": npc.wisdom.save},
            "cha": {"score": npc.charisma.score,     "bonus": npc.charisma.bonus,     "save": npc.charisma.save},
        },
        "traits":            [{"name": a.name, "description": a.description} for a in npc.traits],
        "actions":           [{"name": a.name, "description": a.description} for a in npc.actions],
        "reactions":         [{"name": a.name, "description": a.description} for a in npc.reactions],
        "legendary_actions": [{"name": a.name, "description": a.description} for a in npc.legendary],
        "tags": ["fgu", "npc", system],
    })
    return _notespec_to_markdown_file(
        title=npc.name or "Unnamed NPC",
        folder=f"Campaigns/{campaign}/NPCs",
        fm=fm,
        tags=["fgu", "npc", system],
    )


def _pc_5e_to_notespec(pc: Any, system: str, campaign: str) -> NoteSpec:
    """Convert an ``FGUCharacter`` (from fgu_character) into a NoteSpec.

    Args:
        pc: ``FGUCharacter`` dataclass instance.
        system: Ruleset string (``"dnd5e"``).
        campaign: Campaign folder name.

    Returns:
        NoteSpec ready for ``create_note()``.
    """
    fm: Dict[str, Any] = _base_fm(
        pc.name, system, campaign, "db.xml", "pc", pc.fgu_id
    )
    fm.update({
        "race": pc.race,
        "class": pc.class_string,
        "level": pc.level,
        "background": pc.background,
        "alignment": pc.alignment,
        "hp": pc.hp_current,
        "hp_max": pc.hp_max,
        "ac": pc.ac,
        "speed": pc.speed,
        "abilities": {
            "str": {"score": pc.strength.score,     "bonus": pc.strength.bonus,     "save": pc.strength.save},
            "dex": {"score": pc.dexterity.score,    "bonus": pc.dexterity.bonus,    "save": pc.dexterity.save},
            "con": {"score": pc.constitution.score, "bonus": pc.constitution.bonus, "save": pc.constitution.save},
            "int": {"score": pc.intelligence.score, "bonus": pc.intelligence.bonus, "save": pc.intelligence.save},
            "wis": {"score": pc.wisdom.score,       "bonus": pc.wisdom.bonus,       "save": pc.wisdom.save},
            "cha": {"score": pc.charisma.score,     "bonus": pc.charisma.bonus,     "save": pc.charisma.save},
        },
        "skills": [
            {"name": s.name, "total": s.total, "proficient": s.proficient}
            for s in pc.skills
        ],
        "inventory": [
            {"name": i.name, "count": i.count, "weight": i.weight}
            for i in pc.inventory
        ],
        "personality": getattr(pc, "personality", ""),
        "ideals":      getattr(pc, "ideals", ""),
        "bonds":       getattr(pc, "bonds", ""),
        "flaws":       getattr(pc, "flaws", ""),
        "tags": ["fgu", "pc", system],
    })
    return _notespec_to_markdown_file(
        title=pc.name or "Unnamed PC",
        folder=f"Campaigns/{campaign}/PCs",
        fm=fm,
        tags=["fgu", "pc", system],
    )


def _item_5e_to_notespec(item: Any, system: str, campaign: str) -> NoteSpec:
    """Convert an ``FGUItem`` (from fgu_character) into a NoteSpec.

    Args:
        item: ``FGUItem`` dataclass instance.
        system: Ruleset string.
        campaign: Campaign folder name.

    Returns:
        NoteSpec ready for ``create_note()``.
    """
    fm: Dict[str, Any] = _base_fm(
        item.name, system, campaign, "db.xml", "item", item.fgu_id
    )
    fm.update({
        "item_type":   item.item_type,
        "subtype":     getattr(item, "subtype", ""),
        "rarity":      item.rarity,
        "weight":      item.weight,
        "value":       item.cost,
        "attunement":  item.attunement,
        "description": item.description,
        "tags": ["fgu", "item", system],
    })
    return _notespec_to_markdown_file(
        title=item.name or "Unnamed Item",
        folder=f"Campaigns/{campaign}/Items",
        fm=fm,
        tags=["fgu", "item", system],
    )


# ---------------------------------------------------------------------------
# Generic / SWADE / OSR parsers (operate directly on ET.Element)
# ---------------------------------------------------------------------------

def _parse_npc_generic(
    node: ET.Element, system: str, campaign: str
) -> NoteSpec:
    """Parse an NPC record for OSR/SWN or any unrecognised ruleset."""
    name = _txt(node, "name")
    fm: Dict[str, Any] = _base_fm(name, system, campaign, "db.xml", "npc", node.tag)
    fm.update({
        "hd":       _txt(node, "hd"),
        "hp":       _num(node, "hp"),
        "ac":       _num(node, "ac"),
        "attacks":  _strip_html(_txt(node, "attacks")),
        "saves":    _txt(node, "saves"),
        "morale":   _num(node, "morale"),
        "movement": _txt(node, "movement"),
        "special":  _strip_html(_txt(node, "special")),
        "xp":       _num(node, "xp"),
        "tags": ["fgu", "npc", system],
    })
    return _notespec_to_markdown_file(
        title=name or "Unnamed NPC",
        folder=f"Campaigns/{campaign}/NPCs",
        fm=fm,
        tags=["fgu", "npc", system],
    )


def _parse_pc_generic(
    node: ET.Element, system: str, campaign: str
) -> NoteSpec:
    """Parse a PC record for OSR/SWN or any unrecognised ruleset."""
    name = _txt(node, "name")
    fm: Dict[str, Any] = _base_fm(name, system, campaign, "db.xml", "pc", node.tag)
    fm.update({
        "player":         _txt(node, "playername"),
        "class":          _txt(node, "class"),
        "level":          _num(node, "level", 1),
        "hp":             _num(node, "hp"),
        "ac":             _num(node, "ac"),
        "saving_throws":  _txt(node, "saves"),
        "skills":         _txt(node, "skills"),
        "equipment":      _strip_html(_txt(node, "equipment")),
        "tags": ["fgu", "pc", system],
    })
    return _notespec_to_markdown_file(
        title=name or "Unnamed PC",
        folder=f"Campaigns/{campaign}/PCs",
        fm=fm,
        tags=["fgu", "pc", system],
    )


def _parse_item_generic(
    node: ET.Element, system: str, campaign: str
) -> NoteSpec:
    """Parse an item record for any ruleset."""
    name = _txt(node, "name")
    fm: Dict[str, Any] = _base_fm(name, system, campaign, "db.xml", "item", node.tag)
    fm.update({
        "item_type":   _txt(node, "type"),
        "weight":      _txt(node, "weight"),
        "value":       _txt(node, "cost"),
        "rarity":      _txt(node, "rarity"),
        "description": _strip_html(_txt(node, "description")),
        "properties":  _txt(node, "properties"),
        "tags": ["fgu", "item", system],
    })
    return _notespec_to_markdown_file(
        title=name or "Unnamed Item",
        folder=f"Campaigns/{campaign}/Items",
        fm=fm,
        tags=["fgu", "item", system],
    )


# Explicit alias used by __init__.py exports and HANDOFF references
_item_to_notespec = _parse_item_generic


def _parse_npc_swade(node: ET.Element, campaign: str) -> NoteSpec:
    """Parse a SWADE NPC XML element into a NoteSpec.

    SWADE attribute dice: the ``<die>`` element lives *inside* the attribute
    element, with optional ``<sides>`` child.  Adjacency modifiers sit as
    sibling elements named ``<attrAdjustment>`` at the record level.

    Args:
        node: The id-* record element.
        campaign: Campaign folder name.

    Returns:
        NoteSpec ready for ``create_note()``.
    """
    name = _txt(node, "name")
    fm: Dict[str, Any] = {
        "fgu_entity":       True,
        "fgu_record_class": "npc",
        "system":           "swade",
        "fgu_campaign":     campaign,
        "name":             name,
        "wild_card":        _txt(node, "wildcard") in ("1", "true", "True"),
        "pace":             _num(node, "pace", 6),
        "parry":            _num(node, "parry"),
        "toughness":        _num(node, "toughness"),
        "attributes": {},
        "skills":     {},
        "edges":      [],
        "hindrances": [],
        "special_abilities": [],
        "gear": [],
        "tags": ["fgu", "npc", "swade"],
    }

    attrs_el = node.find("attributes")
    if attrs_el is not None:
        for attr_el in attrs_el:
            attr_name = attr_el.tag
            die_el = attr_el.find("die")
            sides = _num(die_el, "sides", 4) if die_el is not None else 4
            adj_tag = f"{attr_name}Adjustment"
            adj = _num(node, adj_tag, 0)
            fm["attributes"][attr_name] = f"d{sides}" + (f"+{adj}" if adj else "")

    skills_el = node.find("skills")
    if skills_el is not None:
        for sk in _iter_records(skills_el):
            sk_name = _txt(sk, "name")
            if not sk_name:
                continue
            die_el = sk.find("die")
            sides = _num(die_el, "sides", 4) if die_el is not None else 4
            fm["skills"][sk_name] = f"d{sides}"

    for key, xml_tag in [
        ("edges",            "edges"),
        ("hindrances",       "hindrances"),
        ("special_abilities","specialabilities"),
        ("gear",             "gear"),
    ]:
        container = node.find(xml_tag)
        if container is not None:
            fm[key] = [
                _txt(r, "name")
                for r in _iter_records(container)
                if _txt(r, "name")
            ]

    return _notespec_to_markdown_file(
        title=name or "Unnamed SWADE NPC",
        folder=f"Campaigns/{campaign}/NPCs",
        fm=fm,
        tags=["fgu", "npc", "swade"],
    )


def _parse_pc_swade(node: ET.Element, campaign: str) -> NoteSpec:
    """Parse a SWADE PC XML element into a NoteSpec."""
    name = _txt(node, "name")
    fm: Dict[str, Any] = {
        "fgu_entity":       True,
        "fgu_record_class": "pc",
        "system":           "swade",
        "fgu_campaign":     campaign,
        "name":             name,
        "player":           _txt(node, "playername"),
        "race":             _txt(node, "race"),
        "rank":             _txt(node, "rank"),
        "derived_stats": {
            "pace":      _num(node, "pace", 6),
            "parry":     _num(node, "parry"),
            "toughness": _num(node, "toughness"),
        },
        "attributes": {},
        "skills":     {},
        "edges":      [],
        "hindrances": [],
        "gear":       [],
        "tags": ["fgu", "pc", "swade"],
    }

    attrs_el = node.find("attributes")
    if attrs_el is not None:
        for attr_el in attrs_el:
            attr_name = attr_el.tag
            die_el = attr_el.find("die")
            sides = _num(die_el, "sides", 4) if die_el is not None else 4
            adj_tag = f"{attr_name}Adjustment"
            adj = _num(node, adj_tag, 0)
            fm["attributes"][attr_name] = f"d{sides}" + (f"+{adj}" if adj else "")

    skills_el = node.find("skills")
    if skills_el is not None:
        for sk in _iter_records(skills_el):
            sk_name = _txt(sk, "name")
            if not sk_name:
                continue
            die_el = sk.find("die")
            sides = _num(die_el, "sides", 4) if die_el is not None else 4
            fm["skills"][sk_name] = f"d{sides}"

    for key, xml_tag in [
        ("edges",      "edges"),
        ("hindrances", "hindrances"),
        ("gear",       "gear"),
    ]:
        container = node.find(xml_tag)
        if container is not None:
            fm[key] = [
                _txt(r, "name")
                for r in _iter_records(container)
                if _txt(r, "name")
            ]

    return _notespec_to_markdown_file(
        title=name or "Unnamed SWADE PC",
        folder=f"Campaigns/{campaign}/PCs",
        fm=fm,
        tags=["fgu", "pc", "swade"],
    )


def _parse_encounter(node: ET.Element, system: str, campaign: str) -> NoteSpec:
    """Parse an encounter/scene record."""
    name = _txt(node, "name")
    fm: Dict[str, Any] = _base_fm(name, system, campaign, "db.xml", "encounter", node.tag)
    fm.update({
        "description": _strip_html(_txt(node, "description")),
        "tags": ["fgu", "encounter", system],
    })
    return _notespec_to_markdown_file(
        title=name or "Unnamed Encounter",
        folder=f"Campaigns/{campaign}/Encounters",
        fm=fm,
        tags=["fgu", "encounter", system],
    )


def _parse_shared_note(node: ET.Element, system: str, campaign: str) -> NoteSpec:
    """Parse a shared story / reference note."""
    name = _txt(node, "name")
    fm: Dict[str, Any] = _base_fm(name, system, campaign, "db.xml", "note", node.tag)
    fm.update({"tags": ["fgu", "note", system]})
    extra = _strip_html(_txt(node, "text"))
    return _notespec_to_markdown_file(
        title=name or "Unnamed Note",
        folder=f"Campaigns/{campaign}/Notes",
        fm=fm,
        tags=["fgu", "note", system],
        extra_body=extra,
    )


# ---------------------------------------------------------------------------
# FGUEntityParser — high-level public interface with per-path cache
# ---------------------------------------------------------------------------

class FGUEntityParser:
    """High-level parser for FGU campaign entities.

    Uses ``FGUCampaignParser`` from ``fgu_character`` internally for the
    5E XML work, caching one instance per resolved campaign path.

    For SWADE and OSR/SWN rulesets the XML is re-read via a lightweight
    generic path (``_iter_records`` + ``_txt``/``_num`` helpers).

    Args:
        campaign_path: Path to the FGU campaign folder (must contain db.xml).

    Example::

        parser = FGUEntityParser(Path("...campaigns/Tutorial 5E Campaign"))
        assert parser.load()
        specs = parser.parse(("npc", "pc"))
        print(len(specs), parser.system)
    """

    # Class-level cache: resolved path string → FGUCampaignParser instance
    _cache: Dict[str, Any] = {}

    def __init__(self, campaign_path: Path) -> None:
        self.campaign_path = Path(campaign_path)
        self._loaded: bool = False
        self._system: str = "generic"
        # Raw XML root for non-5E paths (loaded lazily)
        self._root: Optional[ET.Element] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_campaign_parser(self) -> Optional[Any]:
        """Return a cached or freshly loaded ``FGUCampaignParser``."""
        from pantheon.messor.fgu_character import FGUCampaignParser as _CParser
        key = str(self.campaign_path.resolve())
        if key not in FGUEntityParser._cache:
            p = _CParser(self.campaign_path)
            if not p.load():
                return None
            FGUEntityParser._cache[key] = p
        return FGUEntityParser._cache[key]

    def _load_raw_root(self) -> Optional[ET.Element]:
        """Parse db.xml into an ET root (used for SWADE/OSR paths)."""
        if self._root is not None:
            return self._root
        db = self.campaign_path / "db.xml"
        if not db.exists():
            return None
        try:
            raw = db.read_bytes()
            try:
                self._root = ET.fromstring(raw)
            except ET.ParseError:
                from pantheon.messor.fgu_character import _sanitize_xml
                self._root = ET.fromstring(_sanitize_xml(raw))
        except Exception:
            return None
        return self._root

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Load and cache the campaign XML.

        Returns:
            ``True`` if db.xml was found and parsed, ``False`` otherwise.
        """
        self._system = detect_ruleset(self.campaign_path)
        if self._system == "dnd5e":
            parser = self._get_campaign_parser()
            self._loaded = parser is not None
        else:
            root = self._load_raw_root()
            self._loaded = root is not None
        return self._loaded

    @property
    def system(self) -> str:
        """Detected ruleset string (available after ``load()``)."""
        return self._system

    def parse(
        self,
        entity_types: Tuple[str, ...] = ("npc", "pc", "item"),
    ) -> List[NoteSpec]:
        """Parse campaign entities and return NoteSpec objects.

        For 5E the existing ``FGUCampaignParser`` dataclasses are reused;
        for other rulesets a lightweight generic XML path is used.

        Args:
            entity_types: Which entity types to include.  Valid values:
                ``"npc"``, ``"pc"``, ``"item"``, ``"encounter"``,
                ``"note"``.

        Returns:
            List of :class:`~pantheon.insitor.note_creator.NoteSpec` objects
            ready for ``create_note()``.
        """
        if self._system == "dnd5e":
            return self._parse_5e(entity_types)
        return self._parse_generic(entity_types)

    # ------------------------------------------------------------------
    # 5E parse path (via FGUCampaignParser dataclasses)
    # ------------------------------------------------------------------

    def _parse_5e(self, entity_types: Tuple[str, ...]) -> List[NoteSpec]:
        parser = self._get_campaign_parser()
        if parser is None:
            return []
        campaign = self.campaign_path.name
        system = self._system
        specs: List[NoteSpec] = []

        if "npc" in entity_types:
            for npc in parser.npcs.values():
                try:
                    specs.append(_npc_5e_to_notespec(npc, system, campaign))
                except Exception:
                    pass

        if "pc" in entity_types:
            for pc in parser.characters.values():
                try:
                    specs.append(_pc_5e_to_notespec(pc, system, campaign))
                except Exception:
                    pass

        if "item" in entity_types:
            for item in parser.items.values():
                try:
                    specs.append(_item_5e_to_notespec(item, system, campaign))
                except Exception:
                    pass

        # Encounters and notes — fall through to generic XML path
        root = self._load_raw_root()
        if root is not None:
            if "encounter" in entity_types:
                specs.extend(self._collect_generic(root, ("encounter", "encounters"), "encounter", campaign))
            if "note" in entity_types:
                specs.extend(self._collect_notes(root, campaign))

        return specs

    # ------------------------------------------------------------------
    # Generic / SWADE / OSR parse path (direct ET.Element)
    # ------------------------------------------------------------------

    def _parse_generic(self, entity_types: Tuple[str, ...]) -> List[NoteSpec]:
        root = self._load_raw_root()
        if root is None:
            return []
        campaign = self.campaign_path.name
        system = self._system
        specs: List[NoteSpec] = []

        if "npc" in entity_types:
            for sec_tag in ("npcdata", "npc", "npcs"):
                sec = root.find(sec_tag)
                if sec is None:
                    continue
                for record in _iter_records(sec):
                    if not _txt(record, "name"):
                        continue
                    try:
                        if system == "swade":
                            specs.append(_parse_npc_swade(record, campaign))
                        else:
                            specs.append(_parse_npc_generic(record, system, campaign))
                    except Exception:
                        pass
                break

        if "pc" in entity_types:
            for sec_tag in ("charsheet", "character", "characters", "pc"):
                sec = root.find(sec_tag)
                if sec is None:
                    continue
                for record in _iter_records(sec):
                    if not _txt(record, "name"):
                        continue
                    try:
                        if system == "swade":
                            specs.append(_parse_pc_swade(record, campaign))
                        else:
                            specs.append(_parse_pc_generic(record, system, campaign))
                    except Exception:
                        pass
                break

        if "item" in entity_types:
            for sec_tag in ("item", "items", "itemdata", "equipment"):
                sec = root.find(sec_tag)
                if sec is None:
                    continue
                for record in _iter_records(sec):
                    if not _txt(record, "name"):
                        continue
                    try:
                        specs.append(_parse_item_generic(record, system, campaign))
                    except Exception:
                        pass
                break

        if "encounter" in entity_types:
            specs.extend(self._collect_generic(root, ("encounter", "encounters", "map"), "encounter", campaign))

        if "note" in entity_types:
            specs.extend(self._collect_notes(root, campaign))

        return specs

    # ------------------------------------------------------------------
    # Shared section collectors
    # ------------------------------------------------------------------

    def _collect_generic(
        self,
        root: ET.Element,
        section_tags: Tuple[str, ...],
        entity_type: str,
        campaign: str,
    ) -> List[NoteSpec]:
        system = self._system
        specs: List[NoteSpec] = []
        for sec_tag in section_tags:
            sec = root.find(sec_tag)
            if sec is None:
                continue
            for record in _iter_records(sec):
                if not _txt(record, "name"):
                    continue
                try:
                    specs.append(_parse_encounter(record, system, campaign))
                except Exception:
                    pass
            break
        return specs

    def _collect_notes(self, root: ET.Element, campaign: str) -> List[NoteSpec]:
        system = self._system
        specs: List[NoteSpec] = []
        for sec_tag in ("note", "notes", "story", "referencetextdata"):
            sec = root.find(sec_tag)
            if sec is None:
                continue
            for record in _iter_records(sec):
                if not _txt(record, "name"):
                    continue
                try:
                    specs.append(_parse_shared_note(record, system, campaign))
                except Exception:
                    pass
            break
        return specs


# ---------------------------------------------------------------------------
# Public import entry point
# ---------------------------------------------------------------------------

def import_campaign_entities(
    campaign_path: Path,
    config: "Config",
    entity_types: Tuple[str, ...] = ("npc", "pc", "item"),
    overwrite: bool = False,
) -> Tuple[int, List[str]]:
    """Import FGU campaign entities as Obsidian notes.

    Parses the campaign XML, converts each entity to a NoteSpec, and
    calls ``create_note()`` to write the note to the active vault.

    Args:
        campaign_path: Path to the FGU campaign folder (must contain db.xml).
        config: Application config (must have ``current_vault`` set).
        entity_types: Which entity types to import.
        overwrite: If ``True``, overwrite existing notes; if ``False``,
            collisions are skipped silently (``create_note`` resolves unique
            paths internally).

    Returns:
        ``(created_count, error_messages)`` tuple.
    """
    parser = FGUEntityParser(Path(campaign_path))
    if not parser.load():
        return 0, [f"Could not load campaign at {campaign_path}"]

    specs = parser.parse(entity_types)
    created = 0
    errors: List[str] = []

    for spec in specs:
        try:
            result = create_note(spec, config)
            if result is not None:
                created += 1
        except Exception as exc:
            errors.append(f"{spec.title}: {exc}")

    return created, errors
