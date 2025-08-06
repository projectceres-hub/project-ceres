import os
import shutil

def find_all_templates(template_dir):
    templates = []
    for root, _, files in os.walk(template_dir):
        for file in files:
            if file.endswith(".md"):
                rel_path = os.path.relpath(os.path.join(root, file), template_dir)
                templates.append(rel_path)
    return templates

def cmd_showtemplates(args, vaults, prompt_input):
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
            template_file = templates[int(pick) - 1]
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

def cmd_createtemplate(args, vaults, prompt_input):
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

def cmd_uploadtemplate(args, vaults, prompt_input):
    template_dir = os.path.join(vaults["GMAssistantVault"], "templates")
    if not os.path.isdir(template_dir):
        os.makedirs(template_dir)

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

    shutil.copyfile(full_path, dest_path)
    print(f"Template '{template_name}' uploaded successfully.")

def cmd_uploadalltemplates(args, vaults, prompt_input):
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

def cmd_deletetemplate(args, vaults, prompt_input):
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