"""
Fantasy Grounds Unity — Character & Entity Parser
==================================================

Parses FGU campaign db.xml files and extracts characters (PCs), NPCs,
and items into clean Python dataclasses that can be written to Obsidian notes.

FGU Campaign Path (Windows)
---------------------------
Primary:   %APPDATA%\\SmiteWorks\\Fantasy Grounds\\campaigns\\<name>\\
Fallback:  %APPDATA%\\Fantasy Grounds\\campaigns\\<name>\\
           ~/Documents/Fantasy Grounds/campaigns/<name>/

Key file: db.xml  — main campaign database (GM data)
          client.xml — player-visible data (mirrors some of db.xml)

db.xml XML structure (5E ruleset)
----------------------------------
<root>
  <charsheet>
    <id-00001>
      <name type="string">Aragorn</name>
      <race type="string">Human</race>
      <classes>
        <id-00001>
          <name type="string">Ranger</name>
          <level type="number">5</level>
        </id-00001>
      </classes>
      <abilities>
        <strength>
          <score type="number">18</score>
          <bonus type="number">4</bonus>
          <save type="number">6</save>
          <saveprof type="number">1</saveprof>
        </strength>
        ... (dexterity, constitution, intelligence, wisdom, charisma)
      </abilities>
      <hp>
        <total type="number">44</total>
        <wounds type="number">0</wounds>
        <temporary type="number">0</temporary>
      </hp>
      <defenses>
        <ac><total type="number">16</total></ac>
      </defenses>
      <proficiencybonus type="number">3</proficiencybonus>
      <background type="string">Outlander</background>
      <alignment type="string">Neutral Good</alignment>
      <inventory>
        <id-00001>
          <name type="string">Longsword</name>
          <count type="number">1</count>
          <weight type="number">3</weight>
        </id-00001>
      </inventory>
      <skills>
        <athletics><cs type="number">1</cs><total type="number">6</total></athletics>
        ...
      </skills>
    </id-00001>
  </charsheet>

  <npc>
    <id-00001>
      <name type="string">Goblin</name>
      <type type="string">Humanoid (goblinoid)</type>
      <cr type="string">1/4</cr>
      <size type="string">Small</size>
      <speed type="string">30 ft.</speed>
      <hp><total type="number">7</total></hp>
      <ac type="number">15</ac>
      <abilities>...</abilities>
      <actions>...</actions>
      <traits>...</traits>
    </id-00001>
  </npc>

  <item>
    <id-00001>
      <name type="string">+1 Longsword</name>
      <type type="string">Weapon</type>
      <subtype type="string">Martial Melee</subtype>
      <rarity type="string">Uncommon</rarity>
      <weight type="number">3</weight>
      <cost type="string">500 gp</cost>
      <description type="formattedtext">...</description>
    </id-00001>
  </item>
</root>

Notes
-----
- Leaf nodes have a `type` attribute; subtree nodes do not.
- Numbered id-XXXXX pattern used for all list entries.
- Some rulesets differ (CoreRPG uses slightly flatter structure).
- This parser attempts to be resilient: missing nodes return sensible defaults.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET


# Characters that are illegal in XML 1.0 (except tab/LF/CR)
_INVALID_XML_CHARS = re.compile(
    r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f'   # C0 controls (minus \t \n \r)
    r'\ud800-\udfff'                        # lone surrogates
    r'\ufffe\uffff]'                        # non-characters
)
# All numeric character references — evaluated individually by _remove_invalid_numrefs
_ALL_XML_NUMREFS = re.compile(r'&#([xX][0-9a-fA-F]+|\d+);')


def _is_valid_xml_char(codepoint: int) -> bool:
    """
    Return True if *codepoint* is a legal XML 1.0 character.

    XML 1.0 production [2]:
      Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

    Everything else (surrogates 0xD800-0xDFFF, 0xFFFE, 0xFFFF, and anything
    above 0x10FFFF) is forbidden.
    """
    return (
        codepoint in (0x9, 0xA, 0xD)
        or (0x20    <= codepoint <= 0xD7FF)
        or (0xE000  <= codepoint <= 0xFFFD)
        or (0x10000 <= codepoint <= 0x10FFFF)
    )


def _remove_invalid_numrefs(text: str) -> str:
    """
    Evaluate every &#…; numeric character reference and strip those that
    refer to code points illegal in XML 1.0.

    This handles both hex (&#xD83E;) and decimal (&#55358;) forms, including
    surrogate-pair references that FGU emits when it encodes emoji as two
    surrogate code units (e.g. &#55358;&#56800; for a Unicode emoji).
    """
    def _replace(m: re.Match) -> str:
        val_str = m.group(1)
        try:
            cp = int(val_str[1:], 16) if val_str[0] in "xX" else int(val_str)
        except ValueError:
            return m.group(0)       # malformed — leave as-is, let ET report it
        return "" if not _is_valid_xml_char(cp) else m.group(0)

    return _ALL_XML_NUMREFS.sub(_replace, text)


def _sanitize_xml(raw: bytes) -> bytes:
    """
    Strip characters and numeric references that are illegal in XML 1.0.

    FGU db.xml files can contain:
    - Raw control characters embedded in formattedtext nodes
    - Decimal surrogate-pair numeric references for emoji (e.g. &#55358;&#56800;)
    - Hex numeric references for low control chars (e.g. &#x1F;)

    All of these cause ET.parse to fail; this function removes them before
    the second parse attempt.
    """
    # Decode leniently (replace undecodable bytes with replacement char)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = raw.decode("latin-1", errors="replace")

    # Remove numeric references to illegal code points (covers hex AND decimal,
    # including the surrogate range 55296-57343 that the old regex missed)
    text = _remove_invalid_numrefs(text)
    # Remove any raw illegal characters that slipped through
    text = _INVALID_XML_CHARS.sub("", text)
    return text.encode("utf-8")


# ── FGU data paths ─────────────────────────────────────────────────────────────

def get_fgu_campaign_roots() -> List[Path]:
    """
    Return candidate paths where FGU stores campaigns, in priority order.
    Checks both the modern SmiteWorks path and legacy locations.
    """
    candidates: List[Path] = []

    appdata = os.environ.get("APPDATA", "")
    home = Path.home()

    if appdata:
        # Modern FGU path (post-2020)
        candidates.append(Path(appdata) / "SmiteWorks" / "Fantasy Grounds" / "campaigns")
        # Legacy FGU path
        candidates.append(Path(appdata) / "Fantasy Grounds" / "campaigns")

    # Documents fallback (some users configure FGU to store here)
    candidates.append(home / "Documents" / "Fantasy Grounds" / "campaigns")
    candidates.append(home / "OneDrive" / "Documents" / "Fantasy Grounds" / "campaigns")

    return [p for p in candidates if p.exists()]


def find_campaign_folders() -> Dict[str, Path]:
    """
    Scan known FGU paths and return {campaign_name: campaign_folder_path}.
    """
    campaigns: Dict[str, Path] = {}
    for root in get_fgu_campaign_roots():
        try:
            for entry in sorted(root.iterdir()):
                if entry.is_dir() and (entry / "db.xml").exists():
                    campaigns[entry.name] = entry
        except PermissionError:
            continue
    return campaigns


def scan_campaigns_in_folder(folder: Path) -> Dict[str, Path]:
    """
    Scan *folder* for FGU campaign sub-directories and return
    {campaign_name: campaign_folder_path}.

    A sub-directory is treated as a campaign if it contains a db.xml file.
    If *folder* itself contains a db.xml it is returned as a single-campaign
    dict (useful when the user browses directly to a campaign folder).

    Returns an empty dict if the folder doesn't exist or has no campaigns.
    """
    if not folder.is_dir():
        return {}

    # Direct campaign folder?
    if (folder / "db.xml").exists():
        return {folder.name: folder}

    # Campaigns root — scan one level of subdirectories
    campaigns: Dict[str, Path] = {}
    try:
        for entry in sorted(folder.iterdir()):
            if entry.is_dir() and (entry / "db.xml").exists():
                campaigns[entry.name] = entry
    except PermissionError:
        pass
    return campaigns


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class FGUAbility:
    score: int = 10
    bonus: int = 0
    save: int = 0
    save_prof: bool = False


@dataclass
class FGUSkill:
    name: str = ""
    total: int = 0
    proficient: int = 0   # 0=none, 1=proficient, 2=expertise


@dataclass
class FGUInventoryItem:
    name: str = ""
    count: int = 1
    weight: float = 0.0
    equipped: bool = False
    item_type: str = ""


@dataclass
class FGUCharacter:
    """A parsed PC (player character) from charsheet."""
    fgu_id: str = ""
    name: str = "Unknown"
    race: str = ""
    background: str = ""
    alignment: str = ""
    xp: int = 0
    proficiency_bonus: int = 2

    # Classes: list of (class_name, level)
    classes: List[tuple] = field(default_factory=list)

    # Abilities
    strength:     FGUAbility = field(default_factory=FGUAbility)
    dexterity:    FGUAbility = field(default_factory=FGUAbility)
    constitution: FGUAbility = field(default_factory=FGUAbility)
    intelligence: FGUAbility = field(default_factory=FGUAbility)
    wisdom:       FGUAbility = field(default_factory=FGUAbility)
    charisma:     FGUAbility = field(default_factory=FGUAbility)

    # HP
    hp_max:  int = 0
    hp_wounds: int = 0   # damage taken (FGU tracks damage, not current hp)
    hp_temp: int = 0

    # AC
    ac: int = 10

    # Skills
    skills: List[FGUSkill] = field(default_factory=list)

    # Inventory
    inventory: List[FGUInventoryItem] = field(default_factory=list)

    # Raw extras
    speed: str = "30 ft."
    senses: str = ""
    languages: str = ""
    personality: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""

    @property
    def hp_current(self) -> int:
        return max(0, self.hp_max - self.hp_wounds)

    @property
    def level(self) -> int:
        return sum(lvl for _, lvl in self.classes) if self.classes else 0

    @property
    def class_string(self) -> str:
        return " / ".join(f"{cls} {lvl}" for cls, lvl in self.classes)


@dataclass
class FGUAction:
    name: str = ""
    description: str = ""


@dataclass
class FGUNPC:
    """A parsed NPC from the npc section of db.xml."""
    fgu_id: str = ""
    name: str = "Unknown"
    npc_type: str = ""
    size: str = ""
    alignment: str = ""
    cr: str = ""
    xp: int = 0
    speed: str = ""
    senses: str = ""
    languages: str = ""
    challenge: str = ""

    # HP / AC
    hp_max: int = 0
    hp_desc: str = ""   # e.g. "2d6+4"
    ac: int = 10
    ac_desc: str = ""   # e.g. "natural armor"

    # Abilities
    strength:     FGUAbility = field(default_factory=FGUAbility)
    dexterity:    FGUAbility = field(default_factory=FGUAbility)
    constitution: FGUAbility = field(default_factory=FGUAbility)
    intelligence: FGUAbility = field(default_factory=FGUAbility)
    wisdom:       FGUAbility = field(default_factory=FGUAbility)
    charisma:     FGUAbility = field(default_factory=FGUAbility)

    # Actions / Traits
    traits:    List[FGUAction] = field(default_factory=list)
    actions:   List[FGUAction] = field(default_factory=list)
    reactions: List[FGUAction] = field(default_factory=list)
    legendary: List[FGUAction] = field(default_factory=list)


@dataclass
class FGUItem:
    """A parsed item from the item section of db.xml."""
    fgu_id: str = ""
    name: str = "Unknown"
    item_type: str = ""
    subtype: str = ""
    rarity: str = ""
    weight: float = 0.0
    cost: str = ""
    attunement: bool = False
    description: str = ""


# ── XML helpers ────────────────────────────────────────────────────────────────

def _text(node: Optional[ET.Element], default: str = "") -> str:
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _int(node: Optional[ET.Element], default: int = 0) -> int:
    try:
        return int(_text(node, str(default)))
    except (ValueError, TypeError):
        return default


def _float(node: Optional[ET.Element], default: float = 0.0) -> float:
    try:
        return float(_text(node, str(default)))
    except (ValueError, TypeError):
        return default


def _ability(node: Optional[ET.Element]) -> FGUAbility:
    if node is None:
        return FGUAbility()
    return FGUAbility(
        score=_int(node.find("score")),
        bonus=_int(node.find("bonus")),
        save=_int(node.find("save")),
        save_prof=bool(_int(node.find("saveprof"))),
    )


def _strip_html(text: str) -> str:
    """Very basic HTML tag stripper for formattedtext nodes."""
    import re
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def _action_list(parent: Optional[ET.Element]) -> List[FGUAction]:
    if parent is None:
        return []
    actions = []
    for child in parent:
        name_node = child.find("name")
        desc_node = child.find("desc")
        if desc_node is None:
            desc_node = child.find("description")
        actions.append(FGUAction(
            name=_text(name_node),
            description=_strip_html(_text(desc_node)),
        ))
    return actions


# ── Main parser ────────────────────────────────────────────────────────────────

class FGUCampaignParser:
    """
    Parses an FGU campaign db.xml and exposes characters, NPCs, and items.

    Usage:
        parser = FGUCampaignParser(Path("...campaigns/My Campaign"))
        parser.load()
        for char in parser.characters.values():
            print(char.name, char.class_string, char.hp_current)
    """

    def __init__(self, campaign_path: Path) -> None:
        self.campaign_path = campaign_path
        self.db_path = campaign_path / "db.xml"
        self.characters: Dict[str, FGUCharacter] = {}
        self.npcs: Dict[str, FGUNPC] = {}
        self.items: Dict[str, FGUItem] = {}
        self._loaded = False
        self._error: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def error(self) -> Optional[str]:
        return self._error

    def load(self) -> bool:
        """
        Parse the campaign db.xml.
        Returns True on success, False on failure (check self.error).
        """
        if not self.db_path.exists():
            self._error = f"db.xml not found in: {self.campaign_path}"
            return False
        try:
            raw = self.db_path.read_bytes()
        except OSError as e:
            self._error = f"Cannot read db.xml: {e}"
            return False

        try:
            # First attempt: parse as-is
            root = ET.fromstring(raw)
        except ET.ParseError:
            # Second attempt: strip illegal XML characters and retry
            try:
                clean = _sanitize_xml(raw)
                root = ET.fromstring(clean)
            except ET.ParseError as e:
                self._error = f"XML parse error (even after sanitizing): {e}"
                return False

        self.characters = {}
        self.npcs = {}
        self.items = {}

        charsheet_node = root.find("charsheet")
        if charsheet_node is not None:
            for entry in charsheet_node:
                if not entry.tag.startswith("id-"):   # skip <public/>, <category>, etc.
                    continue
                char = self._parse_character(entry)
                self.characters[char.fgu_id] = char

        npc_node = root.find("npc")
        if npc_node is not None:
            for entry in npc_node:
                if not entry.tag.startswith("id-"):
                    continue
                npc = self._parse_npc(entry)
                self.npcs[npc.fgu_id] = npc

        item_node = root.find("item")
        if item_node is not None:
            for entry in item_node:
                if not entry.tag.startswith("id-"):
                    continue
                item = self._parse_item(entry)
                self.items[item.fgu_id] = item

        self._loaded = True
        self._error = None
        return True

    # ── Character parsing ──────────────────────────────────────────────────────

    def _parse_character(self, node: ET.Element) -> FGUCharacter:
        c = FGUCharacter(fgu_id=node.tag)
        c.name       = _text(node.find("name"))
        c.race       = _text(node.find("race"))
        c.background = _text(node.find("background"))
        c.alignment  = _text(node.find("alignment"))
        c.speed      = _text(node.find("speed"), "30 ft.")
        c.senses     = _text(node.find("senses"))
        c.languages  = _text(node.find("languages"))
        c.proficiency_bonus = _int(node.find("proficiencybonus"), 2)

        # XP
        xp_node = node.find("xp")
        if xp_node is not None:
            c.xp = _int(xp_node.find("total"))

        # Classes
        classes_node = node.find("classes")
        if classes_node is not None:
            for cls_entry in classes_node:
                cls_name  = _text(cls_entry.find("name"))
                cls_level = _int(cls_entry.find("level"), 1)
                if cls_name:
                    c.classes.append((cls_name, cls_level))

        # Abilities
        abilities = node.find("abilities")
        if abilities is not None:
            c.strength     = _ability(abilities.find("strength"))
            c.dexterity    = _ability(abilities.find("dexterity"))
            c.constitution = _ability(abilities.find("constitution"))
            c.intelligence = _ability(abilities.find("intelligence"))
            c.wisdom       = _ability(abilities.find("wisdom"))
            c.charisma     = _ability(abilities.find("charisma"))

        # HP
        hp_node = node.find("hp")
        if hp_node is not None:
            c.hp_max    = _int(hp_node.find("total"))
            c.hp_wounds = _int(hp_node.find("wounds"))
            c.hp_temp   = _int(hp_node.find("temporary"))

        # AC — try nested defenses/ac/total, then flat ac
        defenses = node.find("defenses")
        if defenses is not None:
            ac_node = defenses.find("ac")
            if ac_node is not None:
                c.ac = _int(ac_node.find("total"), 10)
        if c.ac == 10:
            c.ac = _int(node.find("ac"), 10)

        # Skills
        skills_node = node.find("skills")
        if skills_node is not None:
            for sk in skills_node:
                c.skills.append(FGUSkill(
                    name=sk.tag,
                    total=_int(sk.find("total")),
                    proficient=_int(sk.find("cs")),
                ))

        # Inventory
        inv_node = node.find("inventory")
        if inv_node is not None:
            for inv_entry in inv_node:
                c.inventory.append(FGUInventoryItem(
                    name=_text(inv_entry.find("name")),
                    count=_int(inv_entry.find("count"), 1),
                    weight=_float(inv_entry.find("weight")),
                    equipped=bool(_int(inv_entry.find("carried"), 1)),
                    item_type=_text(inv_entry.find("type")),
                ))

        # Personality traits / bonds / ideals / flaws
        char_data = node.find("chardetails") or node
        c.personality = _text(char_data.find("personality") or node.find("personality"))
        c.ideals      = _text(char_data.find("ideals")      or node.find("ideals"))
        c.bonds       = _text(char_data.find("bonds")       or node.find("bonds"))
        c.flaws       = _text(char_data.find("flaws")       or node.find("flaws"))

        return c

    # ── NPC parsing ────────────────────────────────────────────────────────────

    def _parse_npc(self, node: ET.Element) -> FGUNPC:
        n = FGUNPC(fgu_id=node.tag)
        n.name       = _text(node.find("name"))
        n.npc_type   = _text(node.find("type"))
        n.size       = _text(node.find("size"))
        n.alignment  = _text(node.find("alignment"))
        n.cr         = _text(node.find("cr"))
        n.speed      = _text(node.find("speed"))
        n.senses     = _text(node.find("senses"))
        n.languages  = _text(node.find("languages"))
        n.xp         = _int(node.find("xp"))

        # HP — FGU uses two forms:
        #   Leaf:   <hp type="number">10</hp>
        #   Nested: <hp><total type="number">10</total><desc ...>2d6+4</desc></hp>
        hp_node = node.find("hp")
        if hp_node is not None:
            if hp_node.get("type"):          # leaf form
                n.hp_max = _int(hp_node)
            else:                            # nested form
                n.hp_max  = _int(hp_node.find("total"))
                n.hp_desc = _text(hp_node.find("desc"))

        # AC — FGU stores NPC AC as a flat number or nested
        ac_node = node.find("ac")
        if ac_node is not None:
            # Could be <ac type="number">15</ac> (leaf) or subtree
            if ac_node.get("type"):
                n.ac = _int(ac_node)
            else:
                n.ac      = _int(ac_node.find("total"), _int(ac_node.find("ac"), 10))
                n.ac_desc = _text(ac_node.find("calculatedbonus")) or _text(ac_node.find("desc"))

        # Abilities
        abilities = node.find("abilities")
        if abilities is not None:
            n.strength     = _ability(abilities.find("strength"))
            n.dexterity    = _ability(abilities.find("dexterity"))
            n.constitution = _ability(abilities.find("constitution"))
            n.intelligence = _ability(abilities.find("intelligence"))
            n.wisdom       = _ability(abilities.find("wisdom"))
            n.charisma     = _ability(abilities.find("charisma"))

        n.traits    = _action_list(node.find("traits"))
        n.actions   = _action_list(node.find("actions"))
        n.reactions = _action_list(node.find("reactions"))
        n.legendary = _action_list(node.find("legendary"))

        return n

    # ── Item parsing ───────────────────────────────────────────────────────────

    def _parse_item(self, node: ET.Element) -> FGUItem:
        i = FGUItem(fgu_id=node.tag)
        i.name        = _text(node.find("name"))
        i.item_type   = _text(node.find("type"))
        i.subtype     = _text(node.find("subtype"))
        i.rarity      = _text(node.find("rarity"))
        i.weight      = _float(node.find("weight"))
        i.cost        = _text(node.find("cost"))
        i.attunement  = bool(_int(node.find("attunement")))

        desc = node.find("description") or node.find("text")
        if desc is not None:
            i.description = _strip_html(_text(desc))

        return i


# ── Obsidian note generators ───────────────────────────────────────────────────

def character_to_markdown(char: FGUCharacter) -> str:
    """Convert an FGUCharacter to an Obsidian-friendly markdown note."""
    abilities = {
        "STR": char.strength,
        "DEX": char.dexterity,
        "CON": char.constitution,
        "INT": char.intelligence,
        "WIS": char.wisdom,
        "CHA": char.charisma,
    }

    lines = [
        f"# {char.name}",
        "",
        "```",
        f"{'Race:':<18}{char.race}",
        f"{'Class:':<18}{char.class_string}",
        f"{'Background:':<18}{char.background}",
        f"{'Alignment:':<18}{char.alignment}",
        f"{'Level:':<18}{char.level}",
        f"{'XP:':<18}{char.xp}",
        "```",
        "",
        "## Stats",
        "",
        f"| HP | AC | Speed | Prof. Bonus |",
        f"|----|----|-------|-------------|",
        f"| {char.hp_current}/{char.hp_max} | {char.ac} | {char.speed} | +{char.proficiency_bonus} |",
        "",
        "## Ability Scores",
        "",
        "| | STR | DEX | CON | INT | WIS | CHA |",
        "|---|---|---|---|---|---|---|",
        "| **Score** | " + " | ".join(str(a.score) for a in abilities.values()) + " |",
        "| **Mod**   | " + " | ".join(_fmt_mod(a.bonus) for a in abilities.values()) + " |",
        "| **Save**  | " + " | ".join(_fmt_mod(a.save) for a in abilities.values()) + " |",
        "",
    ]

    if char.skills:
        lines += ["## Skills", ""]
        skill_cols = [char.skills[i:i+3] for i in range(0, len(char.skills), 3)]
        for row in skill_cols:
            lines.append("| " + " | ".join(f"{s.name.title()} {_fmt_mod(s.total)}" for s in row) + " |")
        lines.append("")

    if char.inventory:
        lines += ["## Inventory", ""]
        lines.append("| Item | Count | Weight |")
        lines.append("|------|-------|--------|")
        for item in char.inventory:
            lines.append(f"| {item.name} | {item.count} | {item.weight} lb |")
        lines.append("")

    if any([char.personality, char.ideals, char.bonds, char.flaws]):
        lines += ["## Character Details", ""]
        if char.personality:
            lines += [f"**Personality:** {char.personality}", ""]
        if char.ideals:
            lines += [f"**Ideals:** {char.ideals}", ""]
        if char.bonds:
            lines += [f"**Bonds:** {char.bonds}", ""]
        if char.flaws:
            lines += [f"**Flaws:** {char.flaws}", ""]

    lines += [
        "## Notes",
        "",
        "*(imported from Fantasy Grounds Unity)*",
        "",
        "---",
        "tags: character, pc",
    ]
    return "\n".join(lines)


def npc_to_markdown(npc: FGUNPC) -> str:
    """Convert an FGUNPC to an Obsidian-friendly markdown note."""
    abilities = {
        "STR": npc.strength, "DEX": npc.dexterity, "CON": npc.constitution,
        "INT": npc.intelligence, "WIS": npc.wisdom, "CHA": npc.charisma,
    }

    lines = [
        f"# {npc.name}",
        "",
        f"*{npc.size} {npc.npc_type}, {npc.alignment}*",
        "",
        "---",
        "",
        f"**Armor Class** {npc.ac}" + (f" ({npc.ac_desc})" if npc.ac_desc else ""),
        f"**Hit Points** {npc.hp_max}" + (f" ({npc.hp_desc})" if npc.hp_desc else ""),
        f"**Speed** {npc.speed}",
        "",
        "---",
        "",
        "| STR | DEX | CON | INT | WIS | CHA |",
        "|---|---|---|---|---|---|",
        "| " + " | ".join(
            f"{a.score} ({_fmt_mod(a.bonus)})" for a in abilities.values()
        ) + " |",
        "",
        "---",
        "",
    ]

    if npc.senses:
        lines.append(f"**Senses** {npc.senses}")
    if npc.languages:
        lines.append(f"**Languages** {npc.languages}")
    if npc.cr:
        xp_str = f" ({npc.xp} XP)" if npc.xp else ""
        lines.append(f"**Challenge** {npc.cr}{xp_str}")
    lines.append("")

    for section, entries in [
        ("Traits", npc.traits),
        ("Actions", npc.actions),
        ("Reactions", npc.reactions),
        ("Legendary Actions", npc.legendary),
    ]:
        if entries:
            lines += [f"## {section}", ""]
            for action in entries:
                lines.append(f"**{action.name}.** {action.description}")
                lines.append("")

    lines += [
        "## Notes",
        "",
        "*(imported from Fantasy Grounds Unity)*",
        "",
        "---",
        f"tags: npc, {npc.npc_type.lower().split('(')[0].strip() if npc.npc_type else 'creature'}",
    ]
    return "\n".join(lines)


def item_to_markdown(item: FGUItem) -> str:
    """Convert an FGUItem to an Obsidian-friendly markdown note."""
    lines = [
        f"# {item.name}",
        "",
        f"*{item.item_type}" + (f", {item.subtype}" if item.subtype else "") + "*",
        "",
    ]
    if item.rarity:
        lines.append(f"**Rarity:** {item.rarity}")
    if item.attunement:
        lines.append("**Requires Attunement**")
    if item.weight:
        lines.append(f"**Weight:** {item.weight} lb.")
    if item.cost:
        lines.append(f"**Cost:** {item.cost}")
    lines.append("")

    if item.description:
        lines += ["## Description", "", item.description, ""]

    lines += [
        "## Notes",
        "",
        "*(imported from Fantasy Grounds Unity)*",
        "",
        "---",
        f"tags: item, {item.item_type.lower() if item.item_type else 'gear'}",
    ]
    return "\n".join(lines)


def _fmt_mod(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


# ── Import helper ──────────────────────────────────────────────────────────────

def import_entity_to_vault(
    entity,           # FGUCharacter | FGUNPC | FGUItem
    vault_path: Path,
    subfolder: str = "FGU Imports",
    overwrite: bool = False,
) -> Path:
    """
    Write a parsed FGU entity as a markdown note into the vault.

    Returns the path of the written note.
    Raises FileExistsError if overwrite=False and file exists.
    """
    if isinstance(entity, FGUCharacter):
        content = character_to_markdown(entity)
        folder  = vault_path / subfolder / "Characters"
    elif isinstance(entity, FGUNPC):
        content = npc_to_markdown(entity)
        folder  = vault_path / subfolder / "NPCs"
    elif isinstance(entity, FGUItem):
        content = item_to_markdown(entity)
        folder  = vault_path / subfolder / "Items"
    else:
        raise TypeError(f"Unknown entity type: {type(entity)}")

    folder.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_name = "".join(
        c if c.isalnum() or c in " -_.()" else "_"
        for c in entity.name
    ).strip()
    note_path = folder / f"{safe_name}.md"

    if note_path.exists() and not overwrite:
        raise FileExistsError(f"Note already exists: {note_path}")

    note_path.write_text(content, encoding="utf-8")
    return note_path
