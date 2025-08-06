import os
import json
import time
import threading
import sys

def display_numbered_vaults(vaults, ignored_vaults, vault_number_map):
    vault_number_map.clear()
    print("Available vaults:")
    i = 1
    for name in vaults:
        if name not in ignored_vaults:
            print(f"  {i}. {name}")
            vault_number_map[str(i)] = name
            i += 1

def add_vault(path, vaults, current_vault, save_vaults, save_settings):
    name = os.path.basename(path)
    if name in vaults:
        print("A vault with that name already exists.")
        return current_vault

    vaults[name] = path
    save_vaults()

    if not current_vault:
        current_vault = name
        save_settings()

    print(f"Vault '{name}' added at {path}.")
    return current_vault

def switch_vault(name_or_num, vaults, vault_number_map, save_settings):
    target = name_or_num.strip().lower()
    if vault_number_map and target in vault_number_map:
        current_vault = vault_number_map[target]
        save_settings()
        print(f"Switched to vault '{current_vault}'.")
        return current_vault

    for k in vaults:
        if k.lower() == target:
            current_vault = k
            save_settings()
            print(f"Switched to vault '{k}'.")
            return current_vault

    print(f"The correct syntax is 'switch (number or vault name)'. You entered: '{name_or_num}'. Use the 'vaults' command to see available vaults.")
    return None

def list_vaults(vaults, current_vault, ignored_vaults):
    if not current_vault or current_vault not in vaults:
        print("No current vault set.")
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

def load_vaults():
    if os.path.isfile("vaults.json"):
        with open("vaults.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_vaults(vaults):
    with open("vaults.json", "w", encoding="utf-8") as f:
        json.dump(vaults, f, ensure_ascii=False, indent=2)

def sync_obsidian_vaults(obsidian_json_path, vaults, ignored_vaults, save_vaults):
    if not os.path.isfile(obsidian_json_path):
        return

    with open(obsidian_json_path, "r", encoding="utf-8") as f:
        obsidian_data = json.load(f)

    updated = False
    for vault, info in obsidian_data.get("vaults", {}).items():
        path = info["path"]
        name = os.path.basename(path)
        if name in ignored_vaults:
            continue
        if name not in vaults:
            vaults[name] = path
            updated = True
            print(f"[Auto-Import] New vault found in Obsidian: {name}")

    if updated:
        save_vaults(vaults)

def periodic_obsidian_sync(obsidian_json_path, vaults, ignored_vaults, save_vaults, interval=15):
    def sync_loop():
        while True:
            sync_obsidian_vaults(obsidian_json_path, vaults, ignored_vaults, save_vaults)
            time.sleep(interval)
    threading.Thread(target=sync_loop, daemon=True).start()

def get_obsidian_json_path():
    if sys.platform == "win32":
        return os.path.join(os.environ["APPDATA"], "Obsidian", "obsidian.json")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/obsidian/obsidian.json")
    else:
        return os.path.expanduser("~/.config/obsidian/obsidian.json")

def ensure_default_vault(vaults, current_vault, save_vaults, save_settings):
    default_vault_name = "GMAssistantVault"
    default_vault_path = os.path.abspath("GMAssistantVault")
    if default_vault_name not in vaults:
        vaults[default_vault_name] = default_vault_path
        save_vaults(vaults)
        print(f"Default vault '{default_vault_name}' added.")
    else:
        print(f"Default vault '{default_vault_name}' already present.")

    if not current_vault:
        current_vault = default_vault_name
        save_settings()
        print(f"Current vault set to '{default_vault_name}'.")
    else:
        print(f"Current vault remains '{current_vault}'.")

    return current_vault

def cmd_addvault(args, vaults, current_vault, save_vaults, save_settings, prompt_input, list_vaults, ignored_vaults):
    path = args.strip()
    current_vault = add_vault(path, vaults, current_vault, save_vaults, save_settings)
    list_vaults(vaults, current_vault, ignored_vaults)
    return current_vault

def cmd_switch(args, vaults, current_vault, vault_number_map, save_settings, prompt_input, list_vaults, ignored_vaults, display_numbered_vaults):
    if not args.strip():
        display_numbered_vaults(vaults, ignored_vaults, vault_number_map)
        args = prompt_input("Enter vault name or number: ").strip()

    return switch_vault(args, vaults, vault_number_map, save_settings) or current_vault


def cmd_vaults(vaults, current_vault, ignored_vaults):
    return list_vaults(vaults, current_vault, ignored_vaults)

def cmd_ignorevault(args, ignored_vaults, save_settings):
    name = args.strip()
    if name not in ignored_vaults:
        ignored_vaults.append(name)
        save_settings()
        print(f"Vault '{name}' added to ignore list.")
    else:
        print(f"Vault '{name}' is already in the ignore list.")

def cmd_unignorevault(args, ignored_vaults, save_settings):
    name = args.strip()
    if name in ignored_vaults:
        ignored_vaults.remove(name)
        save_settings()
        print(f"Vault '{name}' removed from ignore list.")
    else:
        print(f"Vault '{name}' was not in the ignore list.")
