#!/usr/bin/env python3


# 1. IMPORTS AND STUFF
from dotenv import load_dotenv
import os # where are we
import sys # help finding stuff
import openai # for chat gpt
import json # for settings
import threading # loop stuff
import time # self explanatory
import shutil

commands = {}
vault_number_map = {}
vaults = {}
current_vault = None
ignored_vaults = []
VERSION = "0.1"

# 1.1 Start Up


def print_startup_summary():
    print(f"\nGM Assistant v{VERSION}\n")
    active_vaults = [v for v in vaults if v not in ignored_vaults]
    print(f"Loaded {len(active_vaults)} vaults:")
    for v in active_vaults:
        print(f" - {v}")
    print(f"\nCurrent vault: {current_vault}")
    if ignored_vaults:
        print("Ignored vaults: " + ", ".join(ignored_vaults))
    else:
        print("Ignored vaults: (none)")
    print("Tip: Type 'help' to see available commands!\n")


# 2. APP SETTINGS

# 2.1 ERROR REPOSITORY
ERRORS = {
    "no_vault": "No current vault set. Use 'switch' to select one or 'addvault' to add one.",
    "file_not_found": "File not found: {filename}. Use 'list' to see available files or 'switch' to switch vaults.",
    "ambiguous_file": "Multiple notes found named '{filename}':",
    "vault_not_found": "Vault '{name}' not found.",
    "already_ignored": "Vault '{name}' is already ignored.",
    "not_ignored": "Vault '{name}' is not currently ignored.",
    "usage_ignorevault": "Usage: ignorevault VAULTNAME",
    "usage_unignorevault": "Usage: unignorevault VAULTNAME",
    "default_exists": "A vault with that name already exists.",
    "obsidian_not_found": "Obsidian config not found. Manual vault add only.",
    "unknown_command": "Unknown command. Type 'help' to see available commands.",
    "no_ignored_vaults": " There are currently no ignored vaults.",
    "specify_full_path": "Please specify the full path (e.g., '{example}').",
    "vault_switch_fail": "No vault named or numbered '{query}'. Use the 'vaults' command to see available vaults.",

}

def error(msg_key, **kwargs):
    msg = ERRORS.get(msg_key, "Unknown error.").format(**kwargs)
    print(msg)

def prompt_input(message): # CANCEL
    ans = input(message).strip()
    if ans.lower() == "cancel":
        print("Action canceled.")
        raise KeyboardInterrupt("Canceled by user")
    return ans

# 2.2 JSONs and Default Vault
def save_settings():
    with open("settings.json", "w", encoding="utf-8") as f:
        json.dump({
            "current_vault": current_vault,
            "ignored_vaults": ignored_vaults
        }, f)

def load_settings():
    global current_vault, ignored_vaults
    if os.path.isfile("settings.json"):
        with open("settings.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            current_vault = data.get("current_vault")
            ignored_vaults = data.get("ignored_vaults", [])
    else:
        current_vault = next(iter(vaults), None)
        ignored_vaults = []

def ensure_default_vault():
    default_vault_name = "GMAssistantVault"
    default_vault_path = os.path.abspath("GMAssistantVault")
    if default_vault_name not in vaults:
        vaults[default_vault_name] = default_vault_path
        save_vaults()
        print(f"Default vault '{default_vault_name}' added.")
    else:
        print(f"Default vault '{default_vault_name}' already present.")
    global current_vault
    if not current_vault:
        current_vault = default_vault_name
        save_settings()
        print(f"Current vault set to '{default_vault_name}'.")
    else:
        print(f"Current vault remains '{current_vault}'.")


# 3. WHO COMMANDS THE COMMANDER

def register_command(name, func, help_text): # this is what makes our commands and the order we decided for it
    commands[name] = (func, help_text)

# 3.1 without argument from me
def cmd_exit(args):
    """Exit the assistant."""
    exit()

def cmd_help(args):
    print("Available commands:")
    for cmd, (_, help_text) in commands.items():
        print(f" {cmd}: {help_text}")
    
def cmd_vaults(args):
    global vault_number_map
    vault_number_map = list_vaults()

def cmd_showignored(args):
    if not ignored_vaults:
        error("no_ignored_vaults")
    else:
        print("Ignored vaults:")
        for name in ignored_vaults:
            print(f" - {name}")

def print_vault_tree():
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return
    path = vaults[current_vault]
    for root, dirs, files in os.walk(path):
        rel_root = os.path.relpath(root, path)
        indent_level = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        indent = "    " * indent_level
        if rel_root != ".":
            print(f"{'    ' * (indent_level-1)}📁 {os.path.basename(root)}/")
        for d in dirs: # Empty dirs will show as we continue walking
            pass
        for f in files:
            if f.endswith(".md"):
                print(f"{indent}📄 {f}")

def cmd_tree(args):
    print_vault_tree()

def cmd_reset(args):
    confirm = prompt_input("Are you sure you want to reset all GM Assistant settings? This will remove all saved vaults and settings (your notes will NOT be deleted). Type YES to confirm: ")
    if confirm.strip().upper() == "YES":
        for fname in ["settings.json", "vaults.json"]:
            if os.path.isfile(fname):
                os.remove(fname)
                print(f"Deleted {fname}.")
        # Optionally reset other state or logs here
        print("GM Assistant settings reset. Please restart the program to see the onboarding/startup flow again.")
        exit()
    else:
        print("Reset cancelled.")


#  3.2 with argument

def cmd_list(args):
    files = list_md_files()
    if args:
        folder = args.strip()
        files = [f for f in files if f.startswith(folder)]
    print("Markdown files:")
    for f in files:
        print(f)

def cmd_read(args):
    fname = args.strip().lower()
    files = list_md_files()
    matches = [f for f in files if f.lower().endswith(fname)]
    if len(matches) == 1:
        full_path = os.path.join(vaults[current_vault], matches[0])
        with open(full_path, "r", encoding="utf-8") as file:
            print(file.read())
    elif len(matches) > 1:
        error("ambiguous_file", filename=args)
        for match in matches:
            print(f" - {match}")
        error("specify_full_path", example="read folder1/note.md")
    else:
        error("file_not_found", filename=args)

def cmd_switch(args):
    global vault_number_map
    if not vault_number_map:
        vault_number_map = list_vaults() 
    vault_name_or_num = args.strip()
    switch_vault(vault_name_or_num, vault_number_map)

def cmd_addvault(args):
    global vault_number_map
    path = args.strip()
    add_vault(path)
    vault_number_map = list_vaults()

def cmd_ignorevault(args):
    global ignored_vaults
    name = args.strip()
    if not name:
        error("usage_ignorevault")
        return
    if name not in vaults:
        error("vault_not_found", name=name)
        return
    if name in ignored_vaults:
        error("already_ignored", name=name)
        return
    ignored_vaults.append(name)
    save_settings()
    print(f"Vault '{name}' is now ignored. Use 'vaults' to see the updated list.")

def cmd_unignorevault(args):
    global ignored_vaults
    name = args.strip()
    if not name:
        error("usage_unignorevault")
        return
    if name not in ignored_vaults:
        error("not_ignored", name=name)
        return
    ignored_vaults.remove(name)
    save_settings()
    print(f"Vault '{name}' is no longer ignored.")

def cmd_upload(args):
    fname = args.strip().lower()
    files = list_md_files()
    matches = [f for f in files if f.lower().endswith(fname)]
    if len(matches) == 1:
        full_path = os.path.join(vaults[current_vault], matches[0])
        with open(full_path, "r", encoding="utf-8") as file:
            content = file.read()
        prompt = f"Please analyze or summarize this note:\n\n{content}"
        reply = chat_with_gpt(prompt)
        print("ChatGPT:", reply)
    elif len(matches) > 1:
        error("ambiguous_file", filename=args)
        for match in matches:
            print(f" - {match}")
        error("specify_full_path", example="read folder1/note.md")
    else:
        error("file_not_found", filename=args)

# 4. THE OBSIDIAN CONNECTION

def list_md_files():
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return []
    path = vaults[current_vault]
    md_files = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.md'): # Get the path relative to the vault root (Obsidian-style)
                rel_dir = os.path.relpath(root, path)
                rel_file = os.path.join(rel_dir, file) if rel_dir != "." else file
                md_files.append(rel_file)
    return md_files

def read_md_file(filename):
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return []
    path = vaults[current_vault]
    full_path = os.path.join(path, filename)
    with open(full_path, "r", encoding="utf-8") as file:
        return file.read()

def cmd_createnote(args):
    choice = prompt_input("Create from (T)emplate or (B)lank? ").strip().lower()
    content = ""
    if choice == "t":
        template_dir = os.path.join(vaults["GMAssistantVault"], "templates")
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
                with open(os.path.join(template_dir, template_file), "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                print("Template not found. Creating blank note.")
    name = prompt_input("Enter name for new note (without .md): ").strip()
    if not name.endswith(".md"):
        name += ".md"
    full_path = os.path.join(vaults[current_vault], name)
    print(f"\n--- Preview: {name} ---\n{content}\n-------------------") 
    if prompt_input("Create this note? (Y/N): ").strip().lower() == "y":
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Note {name} created in {current_vault}!")
    else:
        print("Canceled. Nothing saved.")
    
# 4.1 vault functions

def list_vaults():
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return {}
    print("Current Vault:")
    print(f"- {current_vault}: {vaults[current_vault]}")
    print("\nOther Vaults:")
    other_vaults = [k for k in vaults if k != current_vault and k not in ignored_vaults]
    vault_number_map = {}
    for idx, k in enumerate(other_vaults, start=1):
        print(f"Vault {idx}: {k} ({vaults[k]})")
        vault_number_map[str(idx)] = k
    return vault_number_map

def switch_vault(name_or_num, vault_number_map=None):
    global current_vault
    target = name_or_num.strip().lower()
    if vault_number_map and target in vault_number_map:
        current_vault = vault_number_map[target] # Switch by number
        save_settings()
        print(f"Switched to vault '{current_vault}'.")
        return
    for k in vaults:
        if k.lower() == target:
            current_vault = k
            save_settings()
            print(f"Switched to vault '{k}'.")
            return
    print(f"No vault named or numbered '{name_or_num}'. Use the 'vaults' command to see available vaults.")

def add_vault(path):
    name = os.path.basename(path)
    if name in vaults:
        error("default_exists")
        return
    vaults[name] = path
    save_vaults()
    global current_vault
    if not current_vault:
        current_vault = name
        save_settings()
    print(f"Vault '{name}' added at {path}.")

def load_vaults():
    global vaults
    if os.path.isfile("vaults.json"):
        with open("vaults.json", "r", encoding="utf-8") as f:
            vaults = json.load(f)
    else:
        vaults = {}

def save_vaults():
    with open("vaults.json", "w", encoding="utf-8") as f:
        json.dump(vaults, f, ensure_ascii=False, indent=2)

def sync_obsidian_vaults(obsidian_json_path): # syncing obsidian vaults starts here
    if not os.path.isfile(obsidian_json_path):
        return
    with open(obsidian_json_path, "r", encoding="utf-8") as f:
        obsidian_data = json.load(f)
    updated = False
    for vault, info in obsidian_data.get("vaults", {}).items():
        path = info["path"]
        name = os.path.basename(path)
        if name in ignored_vaults:
            continue  # Skip ignored vaults
        if name not in vaults:
            vaults[name] = path
            updated = True
            print(f"[Auto-Import] New vault found in Obsidian: {name}")

    if updated:
        save_vaults()

def periodic_obsidian_sync(obsidian_json_path, interval=15):
    def sync_loop():
        while True:
            sync_obsidian_vaults(obsidian_json_path)
            time.sleep(interval)
    threading.Thread(target=sync_loop, daemon=True).start()

def get_obsidian_json_path():
    if sys.platform == "win32":
        return os.path.join(os.environ["APPDATA"], "Obsidian", "obsidian.json")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/obsidian/obsidian.json")
    else:  # Assume Linux or other Unix
        return os.path.expanduser("~/.config/obsidian/obsidian.json")
    
# 4.2 Templates

def find_all_templates(template_dir):
    templates = []
    for root, _, files in os.walk(template_dir):
        for file in files:
            if file.endswith(".md"):
                rel_path = os.path.relpath(os.path.join(root, file), template_dir)
                templates.append(rel_path)
    return templates

def cmd_showtemplates(args):
    template_dir = os.path.join(vaults["GMAssistantVault"], "templates")
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
            template_file = templates[int(pick)-1]
        elif pick in templates:
            template_file = pick
        else:
            print("Template not found. Try again.")
            continue

        with open(os.path.join(template_dir, template_file), "r", encoding="utf-8") as f:
            content = f.read()
        print(f"\n--- Preview: {template_file} ---\n{content}\n{'-'*35}")

        again = prompt_input("Preview another template? (Y/N): ").strip().lower()
        if again != 'y':
            print("Returning to main menu.")
            break

def cmd_createtemplate(args):
    template_dir = os.path.join(vaults["GMAssistantVault"], "templates")
    if not os.path.isdir(template_dir):
        os.makedirs(template_dir)

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
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Template '{name}' saved!")
    else:
        print("Canceled. Nothing saved.")

def cmd_uploadtemplate(args):
    template_dir = os.path.join(vaults["GMAssistantVault"], "templates")
    if not os.path.isdir(template_dir):
        os.makedirs(template_dir)

    full_path = args.strip()
    if not full_path:
        full_path = prompt_input("Enter the full path to the .md file to upload as a template: ").strip()
    
    if not os.path.isfile(full_path):
        error("file_not_found", filename=full_path)
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

    shutil.copyfile(full_path, dest_path)
    print(f"Template '{template_name}' uploaded successfully.")

def cmd_deletetemplate(args):
    template_dir = os.path.join(vaults["GMAssistantVault"], "templates")
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
        os.remove(os.path.join(template_dir, template_file))
        print(f"Template '{template_file}' deleted.")
    else:
        print("Canceled. Template not deleted.")

def cmd_uploadalltemplates(args):
    folder_path = args.strip()
    if not folder_path:
        folder_path = prompt_input("Enter the full path to the folder containing .md templates: ").strip()

    if not os.path.isdir(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    template_dir = os.path.join(vaults["GMAssistantVault"], "templates")
    os.makedirs(template_dir, exist_ok=True)

    md_files = [f for f in os.listdir(folder_path) if f.endswith(".md")]
    if not md_files:
        print("No .md files found in that folder.")
        return

    print(f"Found {len(md_files)} templates:")
    for f in md_files:
        print(f" - {f}")

    confirm = prompt_input("Upload all of these to GMAssistantVault/templates? (Y/N): ").strip().lower()
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
        shutil.copyfile(src, dst)
        print(f"Uploaded: {f}")
    print("Batch upload complete.")
    
# 5. THE CHAT GPT RAILWAY

load_dotenv("variables.env") 
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=openai.api_key)

def chat_with_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",  # or "gpt-3.5-turbo"
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content 

def cmd_gptwrite(args):
    if ':' not in args:
        print("Usage: gptwrite NoteName.md: prompt text here")
        return
    note_name, prompt = [a.strip() for a in args.split(':', 1)]
    if not note_name.endswith(".md"):
        note_name += ".md"
    print(f"Sending to ChatGPT: {prompt}")
    response = chat_with_gpt(prompt)
    print("\n--- ChatGPT Response ---\n")
    print(response)
    print("\n------------------------\n")
    confirm = prompt_input(f"Append to {note_name}? (Y/N): ").strip().lower()
    if confirm == 'y':
        note_path = os.path.join(vaults[current_vault], note_name)
        with open(note_path, "a", encoding="utf-8") as f:
            f.write("\n" + response + "\n")
        print(f"Content added to {note_name}.")
    else:
        print("Content not saved.")

def cmd_editnote(args):
    files = list_md_files()
    if not files:
        print("No markdown files in the current vault.")
        return
    print("Notes in current vault:")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")
    selection = prompt_input("Enter the number or name of the note to edit: ").strip()
    try:
        idx = int(selection) - 1
        if 0 <= idx < len(files):
            note_file = files[idx]
        else:
            print("Invalid selection.")
            return
    except ValueError:
        note_file = None
        for f in files:
            if f.lower() == selection.lower():
                note_file = f
                break
        if not note_file:
            print("Note not found.")
            return
    instruction = prompt_input("What do you want ChatGPT to do with this note? (e.g., summarize, fix grammar):\n").strip()
    full_path = os.path.join(vaults[current_vault], note_file)
    with open(full_path, "r", encoding="utf-8") as file:
        content = file.read()
    prompt = f"Here is a note:\n\n{content}\n\nUser asks: {instruction}\n\nPlease respond appropriately."
    try:
        gpt_response = chat_with_gpt(prompt)
    except Exception as e:
        print(f"Error communicating with ChatGPT: {e}")
        return

    print(f"\n--- ChatGPT Response ---\n{gpt_response}\n")
    print("What do you want to do with ChatGPT’s response?")
    print("  [A]ppend to note\n  [O]verwrite note\n  [S]ave as new file\n  [C]ancel")
    choice = prompt_input("Choose (A/O/S/C): ").strip().lower()
    if choice == 'a':
        with open(full_path, "a", encoding="utf-8") as f:
            f.write("\n\n--- ChatGPT Edit ---\n" + gpt_response + "\n")
        print(f"Appended to {note_file}.")
    elif choice == 'o':
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(gpt_response)
        print(f"Overwrote {note_file} with ChatGPT’s response.")
    elif choice == 's':
        new_name = prompt_input("Enter new note name (with or without .md): ").strip()
        if not new_name.endswith(".md"):
            new_name += ".md"
        new_path = os.path.join(vaults[current_vault], new_name)
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(gpt_response)
        print(f"Saved as new note: {new_name}")
    else:
        print("Canceled. No changes made.")



   
# 6. BOOT UP, BOOT

# 6.1 Registration of all commands (name, func, help_text)

register_command("exit", cmd_exit, "Exit the assistant.")
register_command("help", cmd_help, "Show this help message.")
register_command("list", cmd_list, "List markdown files in the current vault.")
register_command("vaults", cmd_vaults, "List available vaults.")
register_command("read", cmd_read, "Read a markdown file: read FILENAME")
register_command("switch", cmd_switch, "Switch to a vault by name or number: switch VAULTNAME|NUMBER")
register_command("addvault", cmd_addvault, "Add a new vault by folder path: addvault PATH")
register_command("ignorevault", cmd_ignorevault, "Ignore a vault by name: ignorevault VAULTNAME")
register_command("unignorevault", cmd_unignorevault, "Stop ignoring a vault: unignorevault VAULTNAME")
register_command("showignored", cmd_showignored, "Show all currently ignored vaults")
register_command("upload", cmd_upload, "Send the contents of a note to ChatGPT: upload FILENAME")
register_command("tree", lambda args: print_vault_tree(), "Show the current vault's folder and note structure (tree view).")
register_command("reset", cmd_reset, "Reset all GM Assistant settings to first-launch state (will not delete notes, just assistant config).")
register_command("gptwrite", cmd_gptwrite, "Ask ChatGPT a question and optionally save to a note: gptwrite NoteName.md: prompt text")
register_command("editnote", cmd_editnote, "Edit a note with ChatGPT and choose how to save: editnote")
register_command("createnote", cmd_createnote, "Create a new note, optionally from a template.")
register_command("showtemplates", cmd_showtemplates, "List and preview note templates.")
register_command("createtemplate", cmd_createtemplate, "Create a new markdown template by typing or pasting content.")
register_command("uploadtemplate", cmd_uploadtemplate, "Upload an existing .md file into the GMAssistantVault's templates.")
register_command("deletetemplate", cmd_deletetemplate, "Delete a template from the GMAssistantVault.")
register_command("uploadalltemplates", cmd_uploadalltemplates, "Upload all .md files from a folder into the GMAssistantVault's templates.")


# 6.2 LOAD

load_vaults()
load_settings()

obsidian_json_path = get_obsidian_json_path()
if os.path.isfile(obsidian_json_path):
    sync_obsidian_vaults(obsidian_json_path)
    periodic_obsidian_sync(obsidian_json_path, 15)
else:
    error("obsidian_not_found")

ensure_default_vault()
print_startup_summary()

if not current_vault:
    error("no_vault")
    while not current_vault:
        user_path = prompt_input("Please enter the path to your Obsidian vault folder (or type 'quit' to exit): ").strip()
        if user_path.lower() == "quit":
            print("Exiting GM Assistant. Goodbye!")
            exit()
        add_vault(user_path)


# 7. I FIGHT FOR THE USER 

# 7.1 da loop

while True:
    cmd_line = input("> ").strip()
    if not cmd_line:
        continue  # Ignore empty input
    cmd_parts = cmd_line.split(maxsplit=1)
    cmd = cmd_parts[0].lower()
    args = cmd_parts[1] if len(cmd_parts) > 1 else ""
    if cmd in commands:
        try:
            commands[cmd][0](args)
        except KeyboardInterrupt:
            print("Action canceled. Back to main menu.")
        except Exception as e:
            print(f"Error running command '{cmd}': {e}")
    else:
        error("unknown_command")
