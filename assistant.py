#!/usr/bin/env python3


# 1. IMPORTS AND STUFF
from dotenv import load_dotenv
import os # where are we
import json # for settings
from core.gpt import cmd_gptwrite, cmd_editnote, chat_with_gpt
from core.notes import cmd_read, cmd_list, cmd_send, list_md_files, read_md_file, cmd_createnote, cmd_tree
from core.templates import cmd_showtemplates, cmd_createtemplate, cmd_deletetemplate, cmd_uploadalltemplates, cmd_uploadtemplate
from core.vaults import (
    add_vault,
    list_vaults,
    load_vaults,
    save_vaults,
    sync_obsidian_vaults,
    periodic_obsidian_sync,
    get_obsidian_json_path,
    ensure_default_vault,
    cmd_addvault,
    cmd_switch,
    cmd_vaults,
    cmd_ignorevault,
    cmd_unignorevault,
    display_numbered_vaults
)
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import NestedCompleter


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

def get_note_names():
    note_tree = {}

    notes = list_md_files(vaults, current_vault, error)
    for note in notes:
        parts = note.split(os.sep)
        current_level = note_tree
        for part in parts[:-1]:  # folders
            current_level = current_level.setdefault(part + "/", {})
        current_level[parts[-1]] = None  # final file

    return note_tree

def get_vault_names():
    return {v: None for v in vaults}

def build_completer():
    return NestedCompleter.from_nested_dict({
        "help": None,
        "exit": None,
        "read": get_note_names(),
        "send": get_note_names(),
        "editnote": get_note_names(),
        "switch": get_vault_names(),
        "vaults": None,
        "addvault": None,
        "ignorevault": get_vault_names(),
        "unignorevault": get_vault_names(),
        "createnote": None,
        "tree": None,
        "reset": None,
        "list": None,
        "showignored": None,
        "gptwrite": None,
        "showtemplates": None,
        "uploadtemplate": None,
        "uploadalltemplates": None,
        "deletetemplate": None,
        "createtemplate": None,
        "upload": None  # Deprecated
    })

def error(msg_key, **kwargs):
    msg = ERRORS.get(msg_key, "Unknown error.").format(**kwargs)
    print(msg)

def prompt_input(message): 
    ans = input(message).strip()
    if ans.lower() == "cancel":
        print("Action canceled.")
        raise KeyboardInterrupt("Canceled by user")
    return ans

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



# 3. WHO COMMANDS THE COMMANDER

def register_command(name, func, help_text): # this is what makes our commands and the order we decided for it
    commands[name] = (func, help_text)

def cmd_exit(args):
    """Exit the assistant."""
    exit()

def cmd_help(args):
    print("Available commands:")
    for cmd, (_, help_text) in commands.items():
        print(f" {cmd}: {help_text}")

def cmd_showignored(args):
    if not ignored_vaults:
        error("no_ignored_vaults")
    else:
        print("Ignored vaults:")
        for name in ignored_vaults:
            print(f" - {name}")

def cmd_reset(args):
    confirm = prompt_input("Are you sure you want to reset all GM Assistant settings? This will remove all saved vaults and settings (your notes will NOT be deleted). Type YES to confirm: ")
    if confirm.strip().upper() == "YES":
        for fname in ["settings.json", "vaults.json"]:
            if os.path.isfile(fname):
                os.remove(fname)
                print(f"Deleted {fname}.")
        print("GM Assistant settings reset. Please restart the program to see the onboarding/startup flow again.")
        exit()
    else:
        print("Reset cancelled.")



# 6. BOOT UP, BOOT

# 6.1 Registration of all commands (name, func, help_text)

register_command("exit", cmd_exit, "Exit the assistant.")
register_command("help", cmd_help, "Show this help message.")
register_command("showignored", cmd_showignored, "Show all currently ignored vaults")
register_command("reset", cmd_reset, "Reset all GM Assistant settings to first-launch state (will not delete notes, just assistant config).")
register_command(
    "tree",
    lambda args: cmd_tree(args, vaults, current_vault, error),
    "Show the current vault's folder and note structure (tree view)."
)

register_command(
    "createnote",
    lambda args: cmd_createnote(args, vaults, current_vault, prompt_input),
    "Create a new note, optionally from a template."
)
register_command(
    "gptwrite",
    lambda args: cmd_gptwrite(args, vaults, current_vault, prompt_input, chat_with_gpt),
    "Ask ChatGPT a question and optionally save to a note: gptwrite NoteName.md: prompt text"
)
register_command(
    "editnote",
    lambda args: cmd_editnote(args, vaults, current_vault, prompt_input, list_md_files, read_md_file, chat_with_gpt),
    "Edit a note with ChatGPT and choose how to save: editnote"
)
register_command(
    "showtemplates",
    lambda args: cmd_showtemplates(args, vaults, prompt_input),
    "List and preview note templates."
)
register_command(
    "createtemplate",
    lambda args: cmd_createtemplate(args, vaults, prompt_input),
    "Create a new markdown template by typing or pasting content."
)
register_command(
    "uploadtemplate",
    lambda args: cmd_uploadtemplate(args, vaults, prompt_input),
    "Upload an existing .md file into the GMAssistantVault's templates."
)
register_command(
    "uploadalltemplates",
    lambda args: cmd_uploadalltemplates(args, vaults, prompt_input),
    "Upload all .md files from a folder into the GMAssistantVault's templates."
)
register_command(
    "deletetemplate",
    lambda args: cmd_deletetemplate(args, vaults, prompt_input),
    "Delete a template."
)
register_command(
    "addvault",
    lambda args: cmd_addvault(args, vaults, current_vault, save_vaults, save_settings, prompt_input, list_vaults, ignored_vaults),
    "Add a new Obsidian vault."
)

register_command(
    "switch",
    lambda args: globals().update(current_vault=cmd_switch(args, vaults, current_vault, vault_number_map, save_settings, prompt_input, list_vaults, ignored_vaults, display_numbered_vaults)),
    "Switch to a different vault."
)

register_command(
    "vaults",
    lambda args: cmd_vaults(vaults, current_vault, ignored_vaults),
    "List available vaults."
)

register_command(
    "ignorevault",
    lambda args: cmd_ignorevault(args, ignored_vaults, save_settings),
    "Ignore a vault from auto-importing."
)

register_command(
    "unignorevault",
    lambda args: cmd_unignorevault(args, ignored_vaults, save_settings),
    "Stop ignoring a vault."
)
register_command(
    "read",
    lambda args: cmd_read(args, vaults, current_vault, error),
    "Read a markdown file: read FILENAME"
)

register_command(
    "list",
    lambda args: cmd_list(args, vaults, current_vault, error),
    "List markdown files in the current vault."
)

register_command(
    "send",
    lambda args: cmd_send(args, vaults, current_vault, error, chat_with_gpt),
    "Send a note to ChatGPT: 'send NOTE' or 'upload FOLDER/NOTE'"
)

register_command(
    "upload",
    lambda args: print("Use 'send' instead. This command is deprecated."),
    "Deprecated. Use 'send' instead."
)

# 6.2 LOAD

vaults = load_vaults()
load_settings()

obsidian_json_path = get_obsidian_json_path()
if os.path.isfile(obsidian_json_path):
    sync_obsidian_vaults(obsidian_json_path, vaults, ignored_vaults, save_vaults)
    periodic_obsidian_sync(obsidian_json_path, vaults, ignored_vaults, save_vaults)
else:
    error("obsidian_not_found")

ensure_default_vault(vaults, current_vault, save_vaults, save_settings)
print_startup_summary()

if not current_vault:
    error("no_vault")
    while not current_vault:
        user_path = prompt_input("Please enter the path to your Obsidian vault folder (or type 'quit' to exit): ").strip()
        if user_path.lower() == "quit":
            print("Exiting GM Assistant. Goodbye!")
            exit()
        add_vault(user_path)


# 7. I FIGHT FOR THE USER  aka da loop
# 7.1 Enhanced loop with prompt_toolkit

session = PromptSession(
    history=FileHistory(".gm_assistant_history"),
    complete_while_typing=True
)

# Auto-completion setup
command_completer = build_completer()

while True:
    try:
        cmd_line = session.prompt("> ", completer=command_completer).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting GM Assistant. Goodbye!")
        break

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


