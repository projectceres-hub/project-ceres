"""
Notes module for Project Ceres.

Provides functions for reading, listing, and managing markdown notes in vaults.

Note creation is canonically implemented in ``pantheon.insitor``; this module
re-exports the public API for backward compatibility and houses the
interactive CLI wrapper (``cmd_createnote``).
"""

import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from pantheon.insitor import NoteSpec, create_note


def _assert_within(base: Path, target: Path, label: str = "path") -> Path:
    """Resolve target and assert it is inside base. Raises ValueError if not."""
    resolved = target.resolve()
    base_resolved = base.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Refusing to access {label} outside allowed directory: {resolved}")
    return resolved


def cmd_read(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error: Callable[[str, ...], None]
) -> None:
    """
    Read and display a markdown note.
    
    Args:
        args: Note name or path (with or without .md extension)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error: Error handling function
    """
    raw = args.strip().lower()
    if not raw:
        print("Usage: read [note name or path]")
        return

    files = list_md_files(vaults, current_vault, error)

    # Accept inputs like folder/note or note
    search_name = raw if raw.endswith(".md") else raw + ".md"

    matches = [f for f in files if f.lower().endswith(search_name)]
    if not matches:
        matches = [f for f in files if f.lower() == search_name]

    if len(matches) == 1:
        try:
            full_path = _assert_within(
                Path(vaults[current_vault]),
                Path(vaults[current_vault]) / matches[0],
                "note path",
            )
        except ValueError as e:
            print(f"Error: {e}")
            return
        try:
            with open(full_path, "r", encoding="utf-8") as file:
                print(file.read())
        except FileNotFoundError:
            error("file_not_found", filename=search_name)
            print(f"Hint: The file '{full_path}' was not found. It may have been moved or deleted.")
        except PermissionError as e:
            print(f"Error: Permission denied reading file '{matches[0]}': {e}")
            print(f"Hint: Check file permissions for '{full_path}'")
        except OSError as e:
            print(f"Error: Failed to read file '{matches[0]}': {e}")
            print(f"Hint: Check that the file exists and is accessible at '{full_path}'")
        except Exception as e:
            print(f"Error: Unexpected error reading file: {e}")
            print(f"Hint: The file may be corrupted or inaccessible.")
    elif len(matches) > 1:
        error("ambiguous_file", filename=search_name)
        for match in matches:
            print(f" - {match}")
        error("specify_full_path", example="read folder1/note.md")
    else:
        error("file_not_found", filename=search_name)

def cmd_list(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error: Callable[[str, ...], None]
) -> None:
    """
    List markdown files in the current vault.
    
    Args:
        args: Optional folder filter
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error: Error handling function
    """
    files = list_md_files(vaults, current_vault, error)

    folder_filter = args.strip()
    if folder_filter:
        folder_filter = folder_filter.replace("\\", "/").lower()
        files = [f for f in files if f.lower().startswith(folder_filter)]

    if not files:
        print("No markdown files found.")
        return

    print("Markdown files:")
    for f in files:
        print(f)

def cmd_send(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error: Callable[[str, ...], None],
    gpt_client
) -> None:
    """
    Send a note to GPT for analysis or summarization.
    
    Args:
        args: Note name or path (with or without .md extension)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error: Error handling function
        gpt_client: GPT client instance
    """
    raw = args.strip().lower()
    if not raw:
        print("Usage: upload [note name or path]")
        return

    files = list_md_files(vaults, current_vault, error)

    # Accept folder/note or note, handle .md automatically
    search_name = raw if raw.endswith(".md") else raw + ".md"

    matches = [f for f in files if f.lower().endswith(search_name)]
    if not matches:
        matches = [f for f in files if f.lower() == search_name]

    if len(matches) == 1:
        try:
            full_path = _assert_within(
                Path(vaults[current_vault]),
                Path(vaults[current_vault]) / matches[0],
                "note path",
            )
        except ValueError as e:
            print(f"Error: {e}")
            return
        try:
            with open(full_path, "r", encoding="utf-8") as file:
                content = file.read()
        except FileNotFoundError:
            error("file_not_found", filename=search_name)
            print(f"Hint: The file '{full_path}' was not found. It may have been moved or deleted.")
            return
        except PermissionError as e:
            print(f"Error: Permission denied reading file '{matches[0]}': {e}")
            print(f"Hint: Check file permissions for '{full_path}'")
            return
        except OSError as e:
            print(f"Error: Failed to read file '{matches[0]}': {e}")
            print(f"Hint: Check that the file exists and is accessible.")
            return
        except Exception as e:
            print(f"Error: Unexpected error reading file: {e}")
            return
        
        prompt = f"Please analyze or summarize this note:\n\n{content}"
        try:
            reply = gpt_client.chat(prompt)
            print("\n--- ChatGPT Response ---\n")
            print(reply)
            print("\n------------------------\n")
        except Exception as e:
            print(f"Error: Failed to get response from ChatGPT: {e}")
    elif len(matches) > 1:
        error("ambiguous_file", filename=search_name)
        for match in matches:
            print(f" - {match}")
        error("specify_full_path", example="upload folder1/note.md")
    else:
        error("file_not_found", filename=search_name)


def list_md_files(
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error: Callable[[str, ...], None],
    default_vault_name: str = "GMAssistantVault"
) -> List[str]:
    """
    List all markdown files in the current vault.
    
    Excludes template files from the default vault.
    
    Args:
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error: Error handling function
        default_vault_name: Name of the default vault (for template exclusion)
        
    Returns:
        List of relative file paths (empty list if no vault or error)
    """
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return []
    path = vaults[current_vault]
    md_files = []
    try:
        vault_path = Path(path).resolve()
        for root, dirs, files in os.walk(path):
            if default_vault_name in path and "templates" in root:
                continue
            for file in files:
                if file.endswith('.md'):
                    try:
                        _assert_within(vault_path, Path(root) / file, "note path")
                    except ValueError:
                        continue
                    rel_dir = os.path.relpath(root, path)
                    rel_file = os.path.join(rel_dir, file) if rel_dir != "." else file
                    md_files.append(rel_file)
    except PermissionError as e:
        print(f"Error: Permission denied accessing vault directory '{path}': {e}")
        print("Hint: Check that you have read permissions for the vault directory.")
    except OSError as e:
        print(f"Error: Failed to access vault directory '{path}': {e}")
        print("Hint: Check that the vault path exists and is accessible.")
    except Exception as e:
        print(f"Error: Unexpected error listing files in vault: {e}")
    return md_files

def read_md_file(
    filename: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error: Callable[[str, ...], None]
) -> str:
    """
    Read content from a markdown file.
    
    Args:
        filename: Relative path to the markdown file
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error: Error handling function
        
    Returns:
        File content as string (empty string if error)
    """
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return ""
    path = vaults[current_vault]
    try:
        full_path = _assert_within(Path(path), Path(path) / filename, "note path")
    except ValueError as e:
        print(f"Error: {e}")
        return ""
    try:
        with open(full_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        error("file_not_found", filename=filename)
        print(f"Hint: The file '{full_path}' was not found. It may have been moved or deleted.")
        return ""
    except PermissionError as e:
        print(f"Error: Permission denied reading file '{filename}': {e}")
        print(f"Hint: Check file permissions for '{full_path}'")
        return ""
    except OSError as e:
        print(f"Error: Failed to read file '{filename}': {e}")
        print(f"Hint: Check that the file exists and is accessible.")
        return ""
    except Exception as e:
        print(f"Error: Unexpected error reading file: {e}")
        return ""

def cmd_createnote(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    prompt_input: Callable[[str], str],
    default_vault_name: str = "GMAssistantVault",
    history_manager = None,
    config = None
) -> None:
    """
    Create a new markdown note, optionally from a template.
    
    Supports flags:
    - --template <name>: Use specified template
    - --dry-run: Preview without writing to disk
    - Variable replacement: var=value var2=value2 ...
    
    Internally delegates to :func:`pantheon.insitor.create_note`.
    
    Args:
        args: Command arguments (flags and variables)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        prompt_input: Function to get user input
        default_vault_name: Name of the default vault (for template location)
        history_manager: History manager instance (optional)
        config: Config object (optional, for variable replacement)
    """
    import shlex
    from pantheon.reparator import apply_template_preview
    
    # Parse arguments
    dry_run = False
    template_name = None
    variables: Dict[str, str] = {}
    
    if args.strip():
        parts = shlex.split(args.strip())
        i = 0
        while i < len(parts):
            if parts[i] == "--template" and i + 1 < len(parts):
                template_name = parts[i + 1]
                i += 2
            elif parts[i] == "--dry-run":
                dry_run = True
                i += 1
            elif "=" in parts[i]:
                var_parts = parts[i].split("=", 1)
                if len(var_parts) == 2:
                    variables[var_parts[0].strip()] = var_parts[1].strip()
                i += 1
            else:
                i += 1
    
    choice = ""
    content = ""
    
    # If template specified via flag, use it; otherwise prompt
    if template_name:
        choice = "t"
    else:
        choice = prompt_input("Create from (T)emplate or (B)lank? ").strip().lower()
    
    if choice == "t":
        template_dir = os.path.join(vaults[default_vault_name], "templates")
        try:
            if not os.path.isdir(template_dir):
                os.makedirs(template_dir)
            templates = [f for f in os.listdir(template_dir) if f.endswith(".md")]
            if not templates:
                print("No templates found. Creating blank note instead.")
            else:
                if template_name:
                    template_name_clean = template_name if not template_name.endswith(".md") else template_name[:-3]
                    template_file = None
                    for t in templates:
                        if t == template_name or t == template_name + ".md":
                            template_file = t
                            break
                        if t[:-3] == template_name_clean:
                            template_file = t
                            break
                    if not template_file:
                        print(f"Error: Template '{template_name}' not found. Available templates:")
                        for i, t in enumerate(templates, 1):
                            print(f"  {i}. {t}")
                        return
                else:
                    print("Available templates:")
                    for i, t in enumerate(templates, 1):
                        print(f"  {i}. {t}")
                    pick = prompt_input("Select template number or name: ").strip()
                    if pick.isdigit() and 1 <= int(pick) <= len(templates):
                        template_file = templates[int(pick) - 1]
                    else:
                        template_file = pick if pick in templates else None
                
                if template_file:
                    try:
                        if config:
                            content = apply_template_preview(template_file, config, variables)
                        else:
                            with open(os.path.join(template_dir, template_file), "r", encoding="utf-8") as f:
                                content = f.read()
                    except (FileNotFoundError, PermissionError, OSError) as e:
                        print(f"Error: Failed to read template '{template_file}': {e}")
                        print("Hint: Check that the template file exists and is readable.")
                        content = ""
                    except Exception as e:
                        print(f"Error: Unexpected error reading template: {e}")
                        content = ""
                else:
                    print("Warning: Template not found. Creating blank note.")
        except (PermissionError, OSError) as e:
            print(f"Error: Failed to access template directory: {e}")
            print(f"Hint: Check that '{template_dir}' exists and is accessible.")
            content = ""
        except Exception as e:
            print(f"Error: Unexpected error accessing templates: {e}")
            content = ""

    name = prompt_input("Enter name for new note (without .md): ").strip()
    if not name.endswith(".md"):
        name += ".md"

    print(f"\n--- Preview: {name} ---\n{content}\n-------------------")
    
    if dry_run:
        print("(Dry-run: Note not written to disk)")
        return
    
    if prompt_input("Create this note? (Y/N): ").strip().lower() == "y":
        try:
            name_path = Path(name)
            folder = str(name_path.parent).replace("\\", "/")
            if folder == ".":
                folder = ""
            title = name_path.stem

            spec = NoteSpec(title=title, folder=folder, body=content)
            result = create_note(
                spec, config, history_manager=history_manager, dry_run=False
            )
            if result:
                print(f"Note {name} created in {current_vault}!")
        except ValueError as e:
            print(f"Error: {e}")
        except PermissionError as e:
            print(f"Error: Permission denied writing to '{name}': {e}")
            print(f"Hint: Check that the vault path '{vaults[current_vault]}' is writable.")
        except OSError as e:
            print(f"Error: Failed to create note '{name}': {e}")
            print(f"Hint: Check that the vault directory exists and is accessible.")
        except Exception as e:
            print(f"Error: Unexpected error creating note: {e}")
            print("Hint: Check file permissions and disk space.")
    else:
        print("Canceled. Nothing saved.")

def cmd_tree(
    args: str,
    vaults: Dict[str, str],
    current_vault: Optional[str],
    error: Callable[[str, ...], None]
) -> None:
    """
    Display vault structure as a tree view.
    
    Args:
        args: Command arguments (unused)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        error: Error handling function
    """
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return
    path = vaults[current_vault]
    try:
        for root, dirs, files in os.walk(path):
            rel_root = os.path.relpath(root, path)
            indent_level = 0 if rel_root == "." else rel_root.count(os.sep) + 1
            indent = "    " * indent_level
            if rel_root != ".":
                print(f"{'    ' * (indent_level-1)}📁 {os.path.basename(root)}/")
            for d in dirs:
                pass
            for f in files:
                if f.endswith(".md"):
                    print(f"{indent}📄 {f}")
    except PermissionError as e:
        print(f"Error: Permission denied accessing vault directory '{path}': {e}")
        print("Hint: Check that you have read permissions for the vault directory.")
    except OSError as e:
        print(f"Error: Failed to access vault directory '{path}': {e}")
        print("Hint: Check that the vault path exists and is accessible.")
    except Exception as e:
        print(f"Error: Unexpected error displaying vault tree: {e}")
