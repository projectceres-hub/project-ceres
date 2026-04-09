"""
Note creation and seeding for Project Ceres.

Provides the unified note-creation API used by all callers — CLI commands,
campaign entity functions, and future UI actions.

This module is part of the Insitor domain in the Pantheon architecture,
responsible for note creation and seeding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config

_FM_PATTERN = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)


@dataclass
class NoteSpec:
    """Everything needed to create a note.

    Attributes:
        title: Note title — also used as the filename stem via ``safe_filename()``.
        folder: Subfolder under vault root (e.g. ``"Campaigns/Underdark/NPCs/Ally"``).
            Empty string means vault root.
        template: Template name resolved via Reparator's ``apply_template_preview``.
        variables: ``{{var}}`` replacements passed to the template engine.
        frontmatter: Explicit YAML frontmatter dict. When a template is also
            provided, these values are merged on top of the template's own
            frontmatter (spec wins on conflict).
        body: Explicit body text.  Used when no template is provided.
        tags: Tags to add via Obarator after the file is written.
    """

    title: str
    folder: str = ""
    template: Optional[str] = None
    variables: Dict[str, str] = field(default_factory=dict)
    frontmatter: Optional[Dict[str, Any]] = None
    body: Optional[str] = None
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public utilities
# ---------------------------------------------------------------------------

def safe_filename(title: str, max_len: int = 80) -> str:
    """Convert a title to a safe filename stem.

    Strips characters that are illegal on Windows/macOS/Linux filesystems
    and truncates to *max_len*.  Spaces are **preserved** (Obsidian supports
    them in note names).

    Args:
        title: Raw title string.
        max_len: Maximum length of the returned stem.

    Returns:
        Sanitised filename stem (without extension).
    """
    stem = title.strip()
    stem = re.sub(r'[<>:"/\\|?*]', "", stem)
    stem = stem[:max_len]
    stem = stem.rstrip(". ")
    return stem or "Untitled"


def resolve_unique_path(directory: Path, stem: str, suffix: str = ".md") -> Path:
    """Return a path that does not collide with an existing file.

    If ``directory/stem.suffix`` is free, return it directly.  Otherwise
    append ``(2)``, ``(3)``, etc. until a free slot is found.

    Args:
        directory: Target directory (need not exist yet).
        stem: Filename stem (without extension).
        suffix: File extension including the leading dot.

    Returns:
        A :class:`Path` guaranteed not to exist at call time.
    """
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_frontmatter(fm: Dict[str, Any]) -> str:
    """Serialise a flat dictionary into a YAML frontmatter block.

    Only handles simple scalar values (strings, numbers, booleans).
    No quoting or escaping — matches the style used elsewhere in
    Project Ceres.
    """
    lines = ["---"]
    for key, value in fm.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _merge_frontmatter(content: str, overrides: Dict[str, Any]) -> str:
    """Merge *overrides* into the YAML frontmatter already present in *content*.

    If *content* has no frontmatter block, one is prepended.
    Override values win on key collisions.
    """
    match = _FM_PATTERN.match(content)
    if match:
        existing: Dict[str, Any] = {}
        for line in match.group(1).strip().split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                existing[key.strip()] = value.strip()
        existing.update(overrides)
        body = content[match.end():]
        return _build_frontmatter(existing) + "\n" + body
    return _build_frontmatter(overrides) + "\n\n" + content


# ---------------------------------------------------------------------------
# Core creation function
# ---------------------------------------------------------------------------

def create_note(
    spec: NoteSpec,
    config: "Config",
    history_manager: Any = None,
    dry_run: bool = False,
) -> Optional[Path]:
    """Create a note in the current vault from a *NoteSpec*.

    Steps:
        1. Resolve vault path from ``config``.
        2. Build destination directory (``vault / spec.folder``), creating it
           if it does not exist.
        3. Derive a safe filename from ``spec.title``.
        4. Assemble content from template, explicit body, or blank note.
        5. Back up any pre-existing file (via *history_manager*) before
           overwriting.
        6. Write the file as UTF-8 markdown.
        7. Apply tags via Obarator.

    Args:
        spec: Fully-populated :class:`NoteSpec`.
        config: Application configuration (must have ``current_vault`` set).
        history_manager: Optional history manager for backup-before-overwrite.
        dry_run: If ``True``, build content but do not write to disk.

    Returns:
        :class:`Path` of the created file, or ``None`` when *dry_run* is set.

    Raises:
        ValueError: If ``current_vault`` is unset or missing from vaults.
    """
    if not config.current_vault:
        raise ValueError("No current vault set")
    if config.current_vault not in config.vaults:
        raise ValueError(
            f"Current vault '{config.current_vault}' not found in vaults"
        )

    vault_path = Path(config.vaults[config.current_vault])
    dest_dir = vault_path / spec.folder if spec.folder else vault_path

    stem = safe_filename(spec.title)
    dest_path = dest_dir / f"{stem}.md"

    # -- assemble content --------------------------------------------------
    content: str

    if spec.template:
        from pantheon.reparator import apply_template_preview

        content = apply_template_preview(
            spec.template, config, spec.variables or {}
        )
        if spec.frontmatter:
            content = _merge_frontmatter(content, spec.frontmatter)

    elif spec.body is not None:
        if spec.frontmatter:
            content = _build_frontmatter(spec.frontmatter) + "\n\n" + spec.body
        else:
            content = spec.body

    else:
        if spec.frontmatter:
            content = (
                _build_frontmatter(spec.frontmatter)
                + f"\n\n# {spec.title}\n\n"
            )
        else:
            content = f"# {spec.title}\n\n"

    if dry_run:
        return None

    # -- write to disk -----------------------------------------------------
    dest_dir.mkdir(parents=True, exist_ok=True)

    if dest_path.exists() and history_manager is not None:
        history_manager.backup_note(dest_path)

    dest_path.write_text(content, encoding="utf-8")

    # -- post-creation tags ------------------------------------------------
    if spec.tags:
        from pantheon.obarator import add_tag

        for tag in spec.tags:
            try:
                add_tag(dest_path, tag)
            except Exception:
                pass

    return dest_path
