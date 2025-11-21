"""
Templates module for Project Ceres.

Provides functions for managing markdown note templates.
"""

import os
import shutil
from pathlib import Path
from typing import Callable, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Config
else:
    # Avoid circular import at runtime
    Config = object


def find_all_templates(template_dir: str) -> List[str]:
    """
    Find all markdown template files in a directory tree.
    
    Args:
        template_dir: Root directory to search for templates
        
    Returns:
        List of relative template file paths
    """
    templates = []
    for root, _, files in os.walk(template_dir):
        for file in files:
            if file.endswith(".md"):
                rel_path = os.path.relpath(os.path.join(root, file), template_dir)
                templates.append(rel_path)
    return templates

def cmd_showtemplates(
    args: str,
    vaults: Dict[str, str],
    prompt_input: Callable[[str], str],
    default_vault_name: str = "GMAssistantVault"
) -> None:
    """
    Show available templates and allow previewing them.
    
    Args:
        args: Command arguments (unused)
        vaults: Dictionary mapping vault names to paths
        prompt_input: Function to get user input
        default_vault_name: Name of the default vault (for template location)
    """
    template_dir = os.path.join(vaults[default_vault_name], "templates")
    if not os.path.isdir(template_dir):
        print("No templates directory found.")
        return

    templates = find_all_templates(template_dir)
    if not templates:
        print("No templates available.")
        return

    while True:
        print("\nAvailable templates:")
        for i, t in enumerate(templates, 1):
            print(f"  {i}. {t}")

        pick = prompt_input("Enter template number or name to preview (or 'cancel'): ").strip()
        if pick.lower() == "cancel":
            print("Canceled, returning to main menu.")
            break

        if pick.isdigit() and 1 <= int(pick) <= len(templates):
            template_file = templates[int(pick) - 1]
        elif pick in templates:
            template_file = pick
        else:
            print("Template not found. Try again.")
            continue

        try:
            with open(os.path.join(template_dir, template_file), "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"Error: Template file '{template_file}' not found.")
            print(f"Hint: Check that the template exists in '{template_dir}'")
            continue
        except PermissionError as e:
            print(f"Error: Permission denied reading template '{template_file}': {e}")
            print(f"Hint: Check file permissions for the template.")
            continue
        except OSError as e:
            print(f"Error: Failed to read template '{template_file}': {e}")
            print(f"Hint: Check that the template file is accessible.")
            continue
        except Exception as e:
            print(f"Error: Unexpected error reading template: {e}")
            continue

        print(f"\n--- Preview: {template_file} ---\n{content}\n{'-'*35}")
        again = prompt_input("Preview another template? (Y/N): ").strip().lower()
        if again != 'y':
            print("Returning to main menu.")
            break

def cmd_createtemplate(
    args: str,
    vaults: Dict[str, str],
    prompt_input: Callable[[str], str],
    default_vault_name: str = "GMAssistantVault",
    history_manager = None
) -> None:
    """
    Create a new template by typing or pasting content.
    
    Args:
        args: Optional template name
        vaults: Dictionary mapping vault names to paths
        prompt_input: Function to get user input
        default_vault_name: Name of the default vault (for template location)
    """
    template_dir = os.path.join(vaults[default_vault_name], "templates")
    try:
        if not os.path.isdir(template_dir):
            os.makedirs(template_dir)
    except (PermissionError, OSError) as e:
        print(f"Error: Failed to create template directory: {e}")
        print(f"Hint: Check that the vault path '{vaults[default_vault_name]}' is writable.")
        return
    except Exception as e:
        print(f"Error: Unexpected error accessing template directory: {e}")
        return

    name = args.strip()
    if not name:
        name = prompt_input("Enter template name (without .md): ").strip()
    if not name.endswith(".md"):
        name += ".md"

    path = os.path.join(template_dir, name)
    if os.path.exists(path):
        overwrite = prompt_input(f"Template '{name}' already exists. Overwrite? (Y/N): ").strip().lower()
        if overwrite != "y":
            print("Canceled. Template not saved.")
            return

    print("Enter/paste your template content below. Type 'END' on a new line to finish.")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)

    content = "\n".join(lines)
    print(f"\n--- Preview: {name} ---\n{content}\n{'-'*35}")
    confirm = prompt_input("Save this template? (Y/N): ").strip().lower()
    if confirm == "y":
        try:
            template_path = Path(path)
            # Backup if template already exists (overwrite case)
            if template_path.exists() and history_manager is not None:
                history_manager.backup_note(template_path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Template '{name}' saved!")
        except PermissionError as e:
            print(f"Error: Permission denied writing template '{name}': {e}")
            print(f"Hint: Check that '{template_dir}' is writable.")
        except OSError as e:
            print(f"Error: Failed to save template '{name}': {e}")
            print(f"Hint: Check that the template directory exists and is accessible.")
        except Exception as e:
            print(f"Error: Unexpected error saving template: {e}")
            print("Hint: Check file permissions and disk space.")
    else:
        print("Canceled. Nothing saved.")

def cmd_uploadtemplate(
    args: str,
    vaults: Dict[str, str],
    prompt_input: Callable[[str], str],
    default_vault_name: str = "GMAssistantVault",
    history_manager = None
) -> None:
    """
    Upload an existing markdown file as a template.
    
    Args:
        args: Optional full path to the file
        vaults: Dictionary mapping vault names to paths
        prompt_input: Function to get user input
        default_vault_name: Name of the default vault (for template location)
    """
    template_dir = os.path.join(vaults[default_vault_name], "templates")
    try:
        if not os.path.isdir(template_dir):
            os.makedirs(template_dir)
    except (PermissionError, OSError) as e:
        print(f"Error: Failed to create template directory: {e}")
        print(f"Hint: Check that the vault path '{vaults[default_vault_name]}' is writable.")
        return
    except Exception as e:
        print(f"Error: Unexpected error accessing template directory: {e}")
        return

    full_path = args.strip()
    if not full_path:
        full_path = prompt_input("Enter the full path to the .md file to upload as a template: ").strip()

    if not os.path.isfile(full_path):
        print(f"File not found: {full_path}")
        return
    if not full_path.endswith(".md"):
        print("Only .md files can be uploaded as templates.")
        return

    template_name = os.path.basename(full_path)
    dest_path = os.path.join(template_dir, template_name)
    if os.path.exists(dest_path):
        overwrite = prompt_input(f"Template '{template_name}' already exists. Overwrite? (Y/N): ").strip().lower()
        if overwrite != "y":
            print("Canceled. Template not uploaded.")
            return

    try:
        dest_template_path = Path(dest_path)
        # Backup if template already exists (overwrite case)
        if dest_template_path.exists() and history_manager is not None:
            history_manager.backup_note(dest_template_path)
        shutil.copyfile(full_path, dest_path)
        print(f"Template '{template_name}' uploaded successfully.")
    except FileNotFoundError:
        print(f"Error: Source file '{full_path}' not found.")
        print("Hint: Check that the file path is correct and the file exists.")
    except PermissionError as e:
        print(f"Error: Permission denied copying file: {e}")
        print(f"Hint: Check read permissions for '{full_path}' and write permissions for '{template_dir}'")
    except OSError as e:
        print(f"Error: Failed to copy template file: {e}")
        print(f"Hint: Check that both source and destination paths are accessible.")
    except Exception as e:
        print(f"Error: Unexpected error uploading template: {e}")
        print("Hint: Check file permissions and disk space.")

def cmd_uploadalltemplates(
    args: str,
    vaults: Dict[str, str],
    prompt_input: Callable[[str], str],
    default_vault_name: str = "GMAssistantVault",
    history_manager = None
) -> None:
    """
    Upload all markdown files from a folder as templates.
    
    Args:
        args: Optional folder path
        vaults: Dictionary mapping vault names to paths
        prompt_input: Function to get user input
        default_vault_name: Name of the default vault (for template location)
    """
    folder_path = args.strip()
    if not folder_path:
        folder_path = prompt_input("Enter the full path to the folder containing .md templates: ").strip()

    if not os.path.isdir(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    template_dir = os.path.join(vaults[default_vault_name], "templates")
    try:
        os.makedirs(template_dir, exist_ok=True)
    except (PermissionError, OSError) as e:
        print(f"Error: Failed to create template directory: {e}")
        print(f"Hint: Check that the vault path '{vaults[default_vault_name]}' is writable.")
        return
    except Exception as e:
        print(f"Error: Unexpected error accessing template directory: {e}")
        return

    try:
        md_files = [f for f in os.listdir(folder_path) if f.endswith(".md")]
    except PermissionError as e:
        print(f"Error: Permission denied reading folder '{folder_path}': {e}")
        print("Hint: Check that you have read permissions for the source folder.")
        return
    except OSError as e:
        print(f"Error: Failed to read folder '{folder_path}': {e}")
        print("Hint: Check that the folder path exists and is accessible.")
        return
    except Exception as e:
        print(f"Error: Unexpected error reading folder: {e}")
        return

    if not md_files:
        print("No .md files found in that folder.")
        return

    print(f"Found {len(md_files)} templates:")
    for f in md_files:
        print(f" - {f}")

    confirm = prompt_input(f"Upload all of these to {default_vault_name}/templates? (Y/N): ").strip().lower()
    if confirm != 'y':
        print("Canceled.")
        return

    for f in md_files:
        src = os.path.join(folder_path, f)
        dst = os.path.join(template_dir, f)
        if os.path.exists(dst):
            overwrite = prompt_input(f"'{f}' already exists. Overwrite? (Y/N): ").strip().lower()
            if overwrite != 'y':
                print(f"Skipped: {f}")
                continue
        try:
            dst_template_path = Path(dst)
            # Backup if template already exists (overwrite case)
            if dst_template_path.exists() and history_manager is not None:
                history_manager.backup_note(dst_template_path)
            shutil.copyfile(src, dst)
            print(f"Uploaded: {f}")
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Error: Failed to upload '{f}': {e}")
            print(f"Hint: Check file permissions and that both source and destination are accessible.")
        except Exception as e:
            print(f"Error: Unexpected error uploading '{f}': {e}")
    print("Batch upload complete.")

def cmd_deletetemplate(
    args: str,
    vaults: Dict[str, str],
    prompt_input: Callable[[str], str],
    default_vault_name: str = "GMAssistantVault"
) -> None:
    """
    Delete a template file.
    
    Args:
        args: Command arguments (unused)
        vaults: Dictionary mapping vault names to paths
        prompt_input: Function to get user input
        default_vault_name: Name of the default vault (for template location)
    """
    template_dir = os.path.join(vaults[default_vault_name], "templates")
    if not os.path.isdir(template_dir):
        print("No templates directory found.")
        return

    templates = [f for f in os.listdir(template_dir) if f.endswith(".md")]
    if not templates:
        print("No templates available to delete.")
        return

    print("Available templates:")
    for i, t in enumerate(templates, 1):
        print(f"  {i}. {t}")
    selection = prompt_input("Enter the number or name of the template to delete: ").strip()

    template_file = None
    if selection.isdigit() and 1 <= int(selection) <= len(templates):
        template_file = templates[int(selection) - 1]
    elif selection in templates:
        template_file = selection

    if not template_file:
        print("Template not found.")
        return

    confirm = prompt_input(f"Are you sure you want to delete '{template_file}'? (Y/N): ").strip().lower()
    if confirm == 'y':
        template_path = os.path.join(template_dir, template_file)
        try:
            os.remove(template_path)
            print(f"Template '{template_file}' deleted.")
        except FileNotFoundError:
            print(f"Error: Template file '{template_file}' not found.")
            print(f"Hint: The file may have already been deleted.")
        except PermissionError as e:
            print(f"Error: Permission denied deleting template '{template_file}': {e}")
            print(f"Hint: Check that you have write permissions for '{template_dir}'")
        except OSError as e:
            print(f"Error: Failed to delete template '{template_file}': {e}")
            print(f"Hint: Check that the file exists and is accessible.")
        except Exception as e:
            print(f"Error: Unexpected error deleting template: {e}")
    else:
        print("Canceled. Template not deleted.")


def sync_templates_from_remote(config: "Config") -> None:
    """
    Sync templates from a remote source defined in config.templates_remote_url
    into the local templates directory at config.templates_local_path.
    
    This is a placeholder implementation. Future implementations should:
    - Support GitHub repositories (via git clone or API)
    - Support HTTP/HTTPS URLs for template archives
    - Handle authentication for private repositories
    - Support incremental updates (only download changed templates)
    - Validate downloaded templates before saving
    - Handle conflicts with local templates
    
    Args:
        config: Config object containing:
            - templates_remote_url: Optional URL to remote template source
            - templates_local_path: Optional path to local templates directory
            - default_vault_name: Name of default vault (for default template path)
            - vaults: Dictionary mapping vault names to paths
            
    Raises:
        ValueError: If templates_local_path is not set and cannot be determined
        OSError: If local template directory cannot be created or accessed
    """
    # Check if remote URL is configured
    if not config.templates_remote_url:
        print("Template remote sync is not configured.")
        print("Set templates_remote_url in settings to enable remote template syncing.")
        return
    
    # Determine local template path
    templates_local_path = config.templates_local_path
    if not templates_local_path:
        # Default to default vault's templates directory
        if config.default_vault_name not in config.vaults:
            raise ValueError(f"Cannot determine template path: default vault '{config.default_vault_name}' not found")
        templates_local_path = Path(config.vaults[config.default_vault_name]) / "templates"
    
    # Ensure local template directory exists
    templates_local_path = Path(templates_local_path)
    try:
        templates_local_path.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating template directory '{templates_local_path}': {e}")
    except OSError as e:
        raise OSError(f"Failed to create template directory '{templates_local_path}': {e}")
    
    # Placeholder implementation
    # TODO: Implement actual remote sync (e.g., GitHub API, HTTP download, git clone)
    # Example future implementation:
    #   if config.templates_remote_url.startswith("https://github.com"):
    #       # Use GitHub API or git to sync templates
    #       sync_from_github(config.templates_remote_url, templates_local_path)
    #   elif config.templates_remote_url.startswith("http"):
    #       # Download and extract template archive
    #       download_and_extract_templates(config.templates_remote_url, templates_local_path)
    
    print(f"Template remote sync from '{config.templates_remote_url}' is not yet implemented.")
    print(f"Templates would be synced to: {templates_local_path}")
    print("Future implementations will support GitHub repositories and HTTP template archives.")