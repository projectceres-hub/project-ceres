"""
Notes module for Project Ceres.

Provides functions for reading, listing, and managing markdown notes in vaults.
"""

import os
from pathlib import Path
from typing import Callable, Dict, List, Optional


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
        full_path = os.path.join(vaults[current_vault], matches[0])
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
        full_path = os.path.join(vaults[current_vault], matches[0])
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
        for root, dirs, files in os.walk(path):
            if default_vault_name in path and "templates" in root:
                continue
            for file in files:
                if file.endswith('.md'):
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
    full_path = os.path.join(path, filename)
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
    history_manager = None
) -> None:
    """
    Create a new markdown note, optionally from a template.
    
    Args:
        args: Command arguments (unused)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        prompt_input: Function to get user input
        default_vault_name: Name of the default vault (for template location)
    """
    choice = prompt_input("Create from (T)emplate or (B)lank? ").strip().lower()
    content = ""
    if choice == "t":
        template_dir = os.path.join(vaults[default_vault_name], "templates")
        try:
            if not os.path.isdir(template_dir):
                os.makedirs(template_dir)
            templates = [f for f in os.listdir(template_dir) if f.endswith(".md")]
            if not templates:
                print("No templates found. Creating blank note instead.")
            else:
                print("Available templates:")
                for i, t in enumerate(templates, 1):
                    print(f"{i}. {t}")
                pick = prompt_input("Select template number or name: ").strip()
                if pick.isdigit() and 1 <= int(pick) <= len(templates):
                    template_file = templates[int(pick) - 1]
                else:
                    template_file = pick if pick in templates else None
                if template_file:
                    try:
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
                    print("Template not found. Creating blank note.")
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
    full_path = Path(vaults[current_vault]) / name
    print(f"\n--- Preview: {name} ---\n{content}\n-------------------") 
    if prompt_input("Create this note? (Y/N): ").strip().lower() == "y":
        try:
            # Backup if file already exists (overwrite case)
            if full_path.exists() and history_manager is not None:
                history_manager.backup_note(full_path)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Note {name} created in {current_vault}!")
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
