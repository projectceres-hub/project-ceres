"""
Search index module for Project Ceres.

Provides functionality for building and managing search indices of markdown notes,
including frontmatter extraction and tag indexing.
"""

import os
import yaml
import json
import re
from typing import Dict, List, Any, Optional, Callable


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


def extract_inline_tags(content: str) -> List[str]:
    """
    Extract inline tags from markdown content.
    
    Tags are identified by #tag format.
    
    Args:
        content: Markdown content string
        
    Returns:
        List of unique tag names (without # prefix)
    """
    return list(set(re.findall(r'#(\w+)', content)))


def build_search_index(vault_path: str) -> List[Dict[str, Any]]:
    """
    Build a search index for all markdown files in a vault.
    
    Extracts frontmatter, tags, and file metadata for each markdown file.
    
    Args:
        vault_path: Path to the vault directory
        
    Returns:
        List of index entry dictionaries
    """
    index: List[Dict[str, Any]] = []
    for root, _, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, vault_path)
                with open(full_path, encoding="utf-8") as f:
                    content = f.read()
                fm = extract_frontmatter(content)
                inline_tags = extract_inline_tags(content)
                entry = {
                    "id": fm.get("id", rel_path.replace(".md", "")),
                    "path": rel_path,
                    "title": fm.get("title", os.path.splitext(file)[0]),
                    "tags": list(set(fm.get("tags", []) + inline_tags)),
                    "system": fm.get("system"),
                    "type": fm.get("type"),
                }
                index.append(entry)
    return index


def save_index(index: List[Dict[str, Any]], path: str = "index.json") -> None:
    """
    Save search index to a JSON file.
    
    Args:
        index: List of index entry dictionaries
        path: Path to the output JSON file (default: "index.json")
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def load_index(path: str = "index.json") -> List[Dict[str, Any]]:
    """
    Load search index from a JSON file.
    
    Args:
        path: Path to the JSON file (default: "index.json")
        
    Returns:
        List of index entry dictionaries (empty list if file doesn't exist)
    """
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            return loaded if isinstance(loaded, list) else []
    return []


def search_index(
    index: List[Dict[str, Any]],
    query: str
) -> List[Dict[str, Any]]:
    """
    Search the index using a query string.
    
    Supports field-specific searches (key:value) and title searches.
    
    Args:
        index: List of index entry dictionaries
        query: Search query string (e.g., "spell system:dnd-5e")
        
    Returns:
        List of matching index entries
    """
    terms = query.strip().split()
    results = index
    for term in terms:
        if ":" in term:
            key, value = term.split(":", 1)
            results = [entry for entry in results if str(entry.get(key)) == value]
        else:
            results = [
                entry for entry in results
                if term.lower() in entry.get("title", "").lower()
            ]
    return results


def cmd_search(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error: Callable[[str, ...], None]
) -> None:
    """
    Command handler for searching notes in the current vault.
    
    Args:
        args: Search query string
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return

    vault_path = vaults[current_vault]
    index = build_search_index(vault_path)
    results = search_index(index, args)

    if not results:
        print("No matches found.")
        return

    for r in results:
        tags_str = ', '.join(r.get('tags', []))
        print(f"- {r.get('title', 'Untitled')} ({r.get('path', 'unknown')}) [tags: {tags_str}]")
