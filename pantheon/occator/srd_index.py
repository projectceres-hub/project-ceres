"""
SRD Index module for Project Ceres.

Provides functionality for indexing and searching SRD (System Reference Document)
markdown files in the /SRDs/ directory of vaults.

This module is part of the Occator domain in the Pantheon architecture,
responsible for search and SRD index refinement.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

# Import tag extraction from Obarator domain
from pantheon.obarator import extract_frontmatter, extract_inline_tags


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


def extract_content_sample(content: str, max_chars: int = 1000) -> str:
    """
    Extract a sample of content from markdown for snippet generation.
    
    Removes frontmatter, headers, and code blocks, then returns up to
    max_chars of text content suitable for generating search snippets.
    
    Args:
        content: Markdown content string
        max_chars: Maximum number of characters to extract (default: 1000)
        
    Returns:
        Content sample as a string (truncated to max_chars)
    """
    # Remove YAML frontmatter if present
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            content = content[end + 3:].strip()
    
    # Extract text content, skipping headers, code blocks, and lists
    lines = content.split('\n')
    text_lines: List[str] = []
    
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        
        # Track code blocks
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        
        if in_code_block:
            continue
        
        # Skip headers, list markers, empty lines
        if (not stripped or 
            stripped.startswith('#') or 
            stripped.startswith('-') or 
            stripped.startswith('*') or
            stripped.startswith('|')):  # Skip tables
            continue
        
        text_lines.append(stripped)
    
    # Join and truncate
    sample = ' '.join(text_lines)
    if len(sample) > max_chars:
        sample = sample[:max_chars].rsplit(' ', 1)[0] + '...'  # Cut at word boundary
    
    return sample




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
                
                # Extract content sample for snippet generation
                content_sample = extract_content_sample(content, max_chars=1000)
                
                # Create record
                record: Dict[str, Any] = {
                    'path': rel_path,
                    'title': title,
                    'system': system,
                    'tags': sorted(all_tags),
                    'summary': summary,
                    'content_sample': content_sample
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


def _calculate_fuzzy_score(
    text: str,
    query_terms: List[str],
    match_type: str = "substring"
) -> float:
    """
    Calculate a fuzzy relevance score for text matching query terms.
    
    Score based on substring match depth:
    - Exact match: highest score
    - Starts with: medium score
    - Contains: lower score based on position
    
    Args:
        text: Text to score against
        query_terms: List of query terms to match
        match_type: Type of match ("title", "tag", "system", or "substring")
        
    Returns:
        Relevance score (higher is better)
    """
    if not text or not query_terms:
        return 0.0
    
    text_lower = text.lower()
    score = 0.0
    
    for term in query_terms:
        term_lower = term.lower()
        
        # Exact match
        if text_lower == term_lower:
            score += 20.0
        # Starts with term
        elif text_lower.startswith(term_lower):
            score += 10.0
        # Contains term - score based on substring match depth
        elif term_lower in text_lower:
            # Score based on position (earlier matches score higher)
            pos = text_lower.find(term_lower)
            position_bonus = 1.0 - (pos / max(len(text), 1))
            # Base score decreases with longer text (deeper match)
            depth_score = max(0.5, 5.0 * (len(term_lower) / max(len(text_lower), 1)))
            score += depth_score + position_bonus
    
    return score


def _generate_snippet(content: str, query_terms: List[str], max_length: int = 100) -> str:
    """
    Generate a snippet from content highlighting query terms.
    
    Finds the first occurrence of any query term in summary or body and
    extracts ~100 chars around it.
    
    Args:
        content: Content text to extract snippet from (summary or body)
        query_terms: List of query terms to highlight
        max_length: Maximum snippet length (default: 100)
        
    Returns:
        Snippet string with ~100 chars around first match
    """
    if not content:
        return ""
    
    if not query_terms:
        # No query terms, return beginning of content
        snippet = content[:max_length]
        if len(content) > max_length:
            snippet = snippet.rsplit(' ', 1)[0] + '...'
        return snippet
    
    content_lower = content.lower()
    
    # Find first occurrence of any query term
    best_pos = len(content)
    best_term = None
    for term in query_terms:
        pos = content_lower.find(term.lower())
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_term = term
    
    if best_pos == len(content):
        # No match found, return beginning
        snippet = content[:max_length]
        if len(content) > max_length:
            snippet = snippet.rsplit(' ', 1)[0] + '...'
        return snippet
    
    # Extract ~100 chars around the match
    context_chars = max_length // 2  # 50 chars before and after
    start = max(0, best_pos - context_chars)
    end = min(len(content), best_pos + len(best_term) + context_chars)
    
    # Try to start at word boundary
    if start > 0:
        word_start = content.rfind(' ', 0, start)
        if word_start != -1:
            start = word_start + 1
        else:
            start = 0
    
    # Try to end at word boundary
    if end < len(content):
        word_end = content.find(' ', end)
        if word_end != -1:
            end = word_end
        else:
            end = len(content)
    
    snippet = content[start:end].strip()
    
    # Add ellipsis if truncated
    if start > 0:
        snippet = '...' + snippet
    if end < len(content):
        snippet = snippet + '...'
    
    return snippet


def search_srd_index(query: str, index_path: Path, max_results: int = 25) -> List[Dict[str, Any]]:
    """
    Search the SRD index with fuzzy matching and filters.
    
    Parses query for filters (tag:, system:, name:), applies filters,
    performs fuzzy matching on remaining terms, ranks by relevance,
    and returns top results with snippets.
    
    Args:
        query: Search query string (e.g., "spell tag:magic system:dnd-5e")
        index_path: Path to the JSON index file
        max_results: Maximum number of results to return (default: 25)
        
    Returns:
        List of ranked record dictionaries with snippets, each containing:
        - title: Record title
        - path: File path
        - system: System name (if available)
        - tags: List of tags
        - snippet: Relevant snippet highlighting matches
        - score: Relevance score (for internal ranking)
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
    
    # Parse query into filters and search terms
    terms = query.strip().split()
    filters: Dict[str, str] = {}
    search_terms: List[str] = []
    
    for term in terms:
        if ':' in term:
            # Filter term (tag:, system:, name:)
            key, value = term.split(':', 1)
            key = key.lower()
            filters[key] = value.lower()
        else:
            # Search term
            search_terms.append(term)
    
    # Apply filters
    filtered_records = records
    for filter_key, filter_value in filters.items():
        if filter_key == 'tag':
            filtered_records = [
                r for r in filtered_records
                if any(filter_value in str(t).lower() for t in r.get('tags', []))
            ]
        elif filter_key == 'system':
            filtered_records = [
                r for r in filtered_records
                if filter_value in str(r.get('system', '')).lower()
            ]
        elif filter_key == 'name':
            filtered_records = [
                r for r in filtered_records
                if filter_value in str(r.get('title', '')).lower()
            ]
    
    # Calculate scores and generate snippets for each record
    scored_records: List[Dict[str, Any]] = []
    for record in filtered_records:
        if not search_terms:
            # No search terms, all filtered results match
            score = 1.0
        else:
            score = 0.0
            
            # Score based on substring match depth for title
            title = record.get('title', '')
            
            # Base substring match score for title (includes exact match bonus)
            title_score = _calculate_fuzzy_score(title, search_terms, match_type="title")
            score += title_score
            
            # Tag matches: +5 points per matching tag
            tags = record.get('tags', [])
            tags_text = ' '.join(tags).lower()
            for tag in tags:
                tag_lower = str(tag).lower()
                for term in search_terms:
                    term_lower = term.lower()
                    if term_lower in tag_lower or tag_lower in term_lower:
                        score += 5.0
            
            # System match: +10 points
            system = record.get('system', '')
            if system:
                system_lower = str(system).lower()
                for term in search_terms:
                    term_lower = term.lower()
                    if term_lower in system_lower:
                        score += 10.0
                        break
            
            # Add base substring match score for content
            content_sample = record.get('content_sample', record.get('summary', ''))
            content_score = _calculate_fuzzy_score(content_sample, search_terms, match_type="substring")
            score += content_score * 0.5  # Content matches weighted less
        
        # Generate snippet from summary or content
        summary = record.get('summary', '')
        content_sample = record.get('content_sample', '')
        # Try summary first, fall back to content_sample
        snippet_source = summary if summary else content_sample
        snippet = _generate_snippet(snippet_source, search_terms, max_length=100)
        
        # Create result record
        result = {
            'title': record.get('title', 'Untitled'),
            'path': record.get('path', 'unknown'),
            'system': record.get('system'),
            'tags': record.get('tags', []),
            'snippet': snippet,
            'score': score
        }
        
        scored_records.append(result)
    
    # Sort by score (descending) and limit results
    scored_records.sort(key=lambda x: x['score'], reverse=True)
    
    # Filter out zero-score results (unless no search terms)
    if search_terms:
        scored_records = [r for r in scored_records if r['score'] > 0]
    
    # Remove score from output
    for record in scored_records:
        del record['score']
    
    return scored_records[:max_results]


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
    
    # Use new fuzzy search function
    results = search_srd_index(args, index_path, max_results=25)
    
    if not results:
        print("No matches found.")
        return
    
    print(f"\nFound {len(results)} result(s):\n")
    print("=" * 80)
    
    for i, record in enumerate(results, 1):
        print(f"\n{i}. {record.get('title', 'Untitled')}")
        
        system = record.get('system')
        if system:
            print(f"   System: {system}")
        
        print(f"   Path: {record.get('path', 'unknown')}")
        
        snippet = record.get('snippet', '')
        if snippet:
            print(f"   Snippet: {snippet}")
        
        if i < len(results):
            print("-" * 80)
    
    print("\n" + "=" * 80)

