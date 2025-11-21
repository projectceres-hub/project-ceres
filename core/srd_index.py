"""
SRD Index module for Project Ceres.

Provides functionality for indexing and searching SRD (System Reference Document)
markdown files in the /SRDs/ directory of vaults.
"""

import os
import re
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Set


def extract_first_paragraph(content: str) -> str:
    """
    Extract the first non-empty paragraph from markdown content.
    
    Skips YAML frontmatter and returns the first meaningful text block.
    
    Args:
        content: Markdown content string
        
    Returns:
        First paragraph as a string (empty if none found)
    """
    # Remove YAML frontmatter if present
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            content = content[end + 3:].strip()
    
    # Split into lines and find first non-empty paragraph
    lines = content.split('\n')
    current_paragraph: List[str] = []
    
    for line in lines:
        stripped = line.strip()
        # Skip empty lines, headers, list markers, code blocks
        if not stripped or stripped.startswith('#') or stripped.startswith('-') or stripped.startswith('*'):
            if current_paragraph:
                paragraph = ' '.join(current_paragraph).strip()
                if len(paragraph) > 10:  # Only return substantial paragraphs
                    return paragraph[:200] + '...' if len(paragraph) > 200 else paragraph
                current_paragraph = []
            continue
        
        # Skip code blocks
        if stripped.startswith('```'):
            continue
            
        current_paragraph.append(stripped)
    
    # Return last paragraph if we have one
    if current_paragraph:
        paragraph = ' '.join(current_paragraph).strip()
        return paragraph[:200] + '...' if len(paragraph) > 200 else paragraph
    
    return ""


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
    # Skip frontmatter
    body_start = 0
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            body_start = end + 3
    
    body_content = content[body_start:]
    
    # Match #tag patterns (Obsidian-style: #tag or #tag/subtag)
    tags = re.findall(r'#([a-zA-Z][a-zA-Z0-9/_-]*)', body_content)
    return set(tags)


def build_srd_index(root: Path, output: Path) -> None:
    """
    Build an index of SRD markdown files in a directory.
    
    Recursively walks the root directory, parses each .md file, extracts
    metadata (title, system, tags) and summary, then saves to a JSON index file.
    
    Args:
        root: Root directory to index (e.g., vault/SRDs/)
        output: Path to output JSON index file (e.g., .ceres_index/records.json)
    """
    if not root.exists() or not root.is_dir():
        print(f"Warning: SRD directory '{root}' does not exist or is not a directory.")
        return
    
    records: List[Dict[str, Any]] = []
    root_str = str(root)
    
    # Walk directory recursively
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            
            for filename in filenames:
                if not filename.endswith('.md'):
                    continue
                
                full_path = Path(dirpath) / filename
                
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except PermissionError as e:
                    print(f"Warning: Permission denied reading '{full_path}': {e}")
                    continue
                except OSError as e:
                    print(f"Warning: Failed to read '{full_path}': {e}")
                    continue
                except Exception as e:
                    print(f"Warning: Unexpected error reading '{full_path}': {e}")
                    continue
                
                # Extract metadata
                frontmatter = extract_frontmatter(content)
                inline_tags = extract_inline_tags(content)
                
                # Combine frontmatter tags and inline tags
                frontmatter_tags = frontmatter.get('tags', [])
                if isinstance(frontmatter_tags, str):
                    frontmatter_tags = [frontmatter_tags]
                elif not isinstance(frontmatter_tags, list):
                    frontmatter_tags = []
                
                all_tags = list(set(frontmatter_tags + list(inline_tags)))
                
                # Get relative path from vault root
                try:
                    # Calculate relative path from root
                    rel_path = os.path.relpath(str(full_path), root_str)
                    # Normalize path separators
                    rel_path = rel_path.replace('\\', '/')
                except ValueError:
                    # If paths are on different drives, use absolute path
                    rel_path = str(full_path)
                
                # Extract title from frontmatter or filename
                title = frontmatter.get('title', filename.replace('.md', ''))
                
                # Extract system from frontmatter
                system = frontmatter.get('system')
                
                # Extract summary (first paragraph)
                summary = extract_first_paragraph(content)
                
                # Create record
                record: Dict[str, Any] = {
                    'path': rel_path,
                    'title': title,
                    'system': system,
                    'tags': sorted(all_tags),
                    'summary': summary
                }
                
                records.append(record)
    
    except PermissionError as e:
        print(f"Error: Permission denied accessing directory '{root}': {e}")
        print("Hint: Check that you have read permissions for the SRD directory.")
        return
    except OSError as e:
        print(f"Error: Failed to access directory '{root}': {e}")
        print("Hint: Check that the directory exists and is accessible.")
        return
    except Exception as e:
        print(f"Error: Unexpected error indexing SRD directory: {e}")
        return
    
    # Save index to output file
    output.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"SRD index built: {len(records)} records saved to '{output}'")
    except PermissionError as e:
        print(f"Error: Permission denied writing to '{output}': {e}")
        print("Hint: Check that you have write permissions for the output directory.")
    except OSError as e:
        print(f"Error: Failed to write index to '{output}': {e}")
        print("Hint: Check that the output directory is writable and disk space is available.")
    except Exception as e:
        print(f"Error: Unexpected error writing index: {e}")


def search_index(query: str, index_path: Path, strict: bool = False) -> List[Dict[str, Any]]:
    """
    Search the SRD index using a query string.
    
    Supports filters:
    - tag:<value> - matches tags
    - system:<value> - matches system field
    - name:<value> - matches title
    
    By default, performs fuzzy matching on title and tags. Set strict=True
    for exact matches only.
    
    Args:
        query: Search query string (e.g., "spell tag:magic system:dnd-5e")
        index_path: Path to the JSON index file
        strict: If True, use exact matches. If False, use fuzzy substring matches (default)
        
    Returns:
        List of matching record dictionaries
    """
    # Load index
    if not index_path.exists():
        return []
    
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse index file '{index_path}': {e}")
        print("Hint: The index file may be corrupted. Rebuild it with 'srd-index'.")
        return []
    except PermissionError as e:
        print(f"Error: Permission denied reading index file '{index_path}': {e}")
        return []
    except OSError as e:
        print(f"Error: Failed to read index file '{index_path}': {e}")
        return []
    except Exception as e:
        print(f"Error: Unexpected error reading index: {e}")
        return []
    
    if not isinstance(records, list):
        return []
    
    # Parse query terms
    terms = query.strip().split()
    results = records
    
    for term in terms:
        if ':' in term:
            # Field-specific filter
            key, value = term.split(':', 1)
            key = key.lower()
            value = value.lower()
            
            if key == 'tag':
                if strict:
                    results = [
                        r for r in results
                        if value in [t.lower() for t in r.get('tags', [])]
                    ]
                else:
                    results = [
                        r for r in results
                        if any(value in t.lower() for t in r.get('tags', []))
                    ]
            elif key == 'system':
                if strict:
                    results = [
                        r for r in results
                        if str(r.get('system', '')).lower() == value
                    ]
                else:
                    results = [
                        r for r in results
                        if value in str(r.get('system', '')).lower()
                    ]
            elif key == 'name':
                if strict:
                    results = [
                        r for r in results
                        if r.get('title', '').lower() == value
                    ]
                else:
                    results = [
                        r for r in results
                        if value in r.get('title', '').lower()
                    ]
        else:
            # General search: match title or tags
            term_lower = term.lower()
            if strict:
                results = [
                    r for r in results
                    if term_lower == r.get('title', '').lower()
                    or term_lower in [t.lower() for t in r.get('tags', [])]
                ]
            else:
                results = [
                    r for r in results
                    if term_lower in r.get('title', '').lower()
                    or any(term_lower in t.lower() for t in r.get('tags', []))
                ]
    
    return results


def cmd_srd_index(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error_func: Any
) -> None:
    """
    Command handler for building the SRD index.
    
    Args:
        args: Command arguments (unused)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error_func: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error_func("no_vault")
        return
    
    vault_path = Path(vaults[current_vault])
    srd_dir = vault_path / "SRDs"
    index_dir = vault_path / ".ceres_index"
    index_path = index_dir / "records.json"
    
    build_srd_index(srd_dir, index_path)


def cmd_search_srd(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error_func: Any
) -> None:
    """
    Command handler for searching the SRD index.
    
    Pretty-prints search results with filename, title, system, and summary.
    
    Args:
        args: Search query string
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error_func: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error_func("no_vault")
        return
    
    if not args.strip():
        print("Usage: search-srd <query>")
        print("Example: search-srd spell")
        print("Example: search-srd tag:magic system:dnd-5e")
        return
    
    vault_path = Path(vaults[current_vault])
    index_path = vault_path / ".ceres_index" / "records.json"
    
    if not index_path.exists():
        print("SRD index not found. Run 'srd-index' to build it first.")
        return
    
    results = search_index(args, index_path, strict=False)
    
    if not results:
        print("No matches found.")
        return
    
    print(f"\nFound {len(results)} result(s):\n")
    print("=" * 80)
    
    for i, record in enumerate(results, 1):
        print(f"\n{i}. {record.get('title', 'Untitled')}")
        print(f"   Path: {record.get('path', 'unknown')}")
        
        system = record.get('system')
        if system:
            print(f"   System: {system}")
        
        tags = record.get('tags', [])
        if tags:
            tags_str = ', '.join(f"#{tag}" for tag in tags)
            print(f"   Tags: {tags_str}")
        
        summary = record.get('summary', '')
        if summary:
            print(f"   Summary: {summary}")
        
        if i < len(results):
            print("-" * 80)
    
    print("\n" + "=" * 80)

