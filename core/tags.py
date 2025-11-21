"""
Tags module for Project Ceres.

Provides functionality for managing Obsidian-style tags in markdown notes,
including YAML frontmatter tags and inline #tags.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Set, Any


def extract_frontmatter(content: str) -> Dict[str, Any]:
    """
    Extract YAML frontmatter from markdown content.
    
    Args:
        content: Markdown content string
        
    Returns:
        Dictionary of frontmatter fields (empty dict if no frontmatter)
    """
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            fm_text = content[3:end].strip()
            try:
                parsed = yaml.safe_load(fm_text)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    return {}


def extract_inline_tags(content: str) -> Set[str]:
    """
    Extract inline tags from markdown content.
    
    Tags are identified by #tag format. Matches Obsidian-style tags.
    
    Args:
        content: Markdown content string
        
    Returns:
        Set of unique tag names (without # prefix)
    """
    # Match #tag patterns, but not in code blocks or frontmatter
    # Simple regex: # followed by word characters
    # This matches Obsidian's tag format
    tags = re.findall(r'#([a-zA-Z][a-zA-Z0-9/_-]*)', content)
    return set(tags)


def get_tags_for_note(path: Path) -> Set[str]:
    """
    Get all tags for a note (from frontmatter and inline tags).
    
    Args:
        path: Path to the markdown file
        
    Returns:
        Set of tag names (without # prefix)
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise RuntimeError(f"Failed to read file '{path}': {e}")
    
    tags: Set[str] = set()
    
    # Extract frontmatter tags
    frontmatter = extract_frontmatter(content)
    if "tags" in frontmatter:
        tag_list = frontmatter["tags"]
        if isinstance(tag_list, list):
            tags.update(str(tag) for tag in tag_list)
        elif isinstance(tag_list, str):
            tags.add(tag_list)
    
    # Extract inline tags
    inline_tags = extract_inline_tags(content)
    tags.update(inline_tags)
    
    return tags


def _get_body_content(content: str) -> str:
    """
    Extract body content (everything after frontmatter).
    
    Args:
        content: Full markdown content
        
    Returns:
        Body content without frontmatter
    """
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            return content[end + 3:].lstrip()
    return content


def _write_note_with_frontmatter(path: Path, frontmatter: Dict[str, Any], body: str) -> None:
    """
    Write a note with frontmatter.
    
    Args:
        path: Path to the markdown file
        frontmatter: Dictionary of frontmatter fields
        body: Body content (without frontmatter)
    """
    try:
        # Build frontmatter YAML
        if frontmatter:
            # Use yaml.dump for proper formatting
            yaml_content = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True)
            frontmatter_text = f"---\n{yaml_content}---\n"
        else:
            frontmatter_text = ""
        
        # Write file
        with open(path, "w", encoding="utf-8") as f:
            if frontmatter_text:
                f.write(frontmatter_text)
            f.write(body)
    except (PermissionError, OSError) as e:
        raise RuntimeError(f"Failed to write file '{path}': {e}")


def add_tag(path: Path, tag: str) -> None:
    """
    Add a tag to a note's frontmatter.
    
    If the note has no frontmatter, creates a minimal one with the tags field.
    Does not modify inline tags in the body.
    
    Args:
        path: Path to the markdown file
        tag: Tag name to add (without # prefix)
        
    Raises:
        RuntimeError: If file read/write fails
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    # Read current content
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise RuntimeError(f"Failed to read file '{path}': {e}")
    
    # Extract frontmatter and body
    frontmatter = extract_frontmatter(content)
    body = _get_body_content(content)
    
    # Get current tags list
    current_tags = frontmatter.get("tags", [])
    if isinstance(current_tags, str):
        current_tags = [current_tags]
    elif not isinstance(current_tags, list):
        current_tags = []
    
    # Add tag if not already present
    tag_lower = tag.lower()
    if tag_lower not in [t.lower() for t in current_tags]:
        current_tags.append(tag)
        frontmatter["tags"] = current_tags
    
    # Write back
    _write_note_with_frontmatter(path, frontmatter, body)


def remove_tag(path: Path, tag: str) -> None:
    """
    Remove a tag from a note's frontmatter.
    
    Only removes from frontmatter, not from inline tags in the body.
    
    Args:
        path: Path to the markdown file
        tag: Tag name to remove (without # prefix, case-insensitive)
        
    Raises:
        RuntimeError: If file read/write fails
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    # Read current content
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise RuntimeError(f"Failed to read file '{path}': {e}")
    
    # Extract frontmatter and body
    frontmatter = extract_frontmatter(content)
    body = _get_body_content(content)
    
    # Get current tags list
    current_tags = frontmatter.get("tags", [])
    if isinstance(current_tags, str):
        current_tags = [current_tags]
    elif not isinstance(current_tags, list):
        current_tags = []
    
    # Remove tag (case-insensitive)
    tag_lower = tag.lower()
    current_tags = [t for t in current_tags if t.lower() != tag_lower]
    
    if current_tags:
        frontmatter["tags"] = current_tags
    elif "tags" in frontmatter:
        # Remove tags field if empty
        del frontmatter["tags"]
    
    # Write back
    _write_note_with_frontmatter(path, frontmatter, body)


def list_all_tags(root: Path) -> Dict[str, List[Path]]:
    """
    List all tags found in notes and which notes have each tag.
    
    Searches recursively through all .md files in the root directory.
    
    Args:
        root: Root directory to search for markdown files
        
    Returns:
        Dictionary mapping tag names to lists of file paths that contain them
    """
    tag_map: Dict[str, List[Path]] = {}
    
    if not root.exists() or not root.is_dir():
        return tag_map
    
    # Walk through all markdown files
    for md_file in root.rglob("*.md"):
        try:
            tags = get_tags_for_note(md_file)
            for tag in tags:
                if tag not in tag_map:
                    tag_map[tag] = []
                tag_map[tag].append(md_file)
        except Exception:
            # Skip files that can't be read
            continue
    
    return tag_map


def get_all_tags(vault_root: Path) -> Set[str]:
    """
    Get all unique tags found in a vault.
    
    Args:
        vault_root: Root directory of the vault to search
        
    Returns:
        Set of unique tag names (without # prefix)
    """
    tag_map = list_all_tags(vault_root)
    return set(tag_map.keys())

