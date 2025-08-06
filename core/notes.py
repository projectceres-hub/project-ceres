# core/notes.py

import os

def cmd_read(args, vaults, current_vault, error):
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
        with open(full_path, "r", encoding="utf-8") as file:
            print(file.read())
    elif len(matches) > 1:
        error("ambiguous_file", filename=search_name)
        for match in matches:
            print(f" - {match}")
        error("specify_full_path", example="read folder1/note.md")
    else:
        error("file_not_found", filename=search_name)

def cmd_list(args, vaults, current_vault, error):
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

def cmd_send(args, vaults, current_vault, error, chat_with_gpt):
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
        with open(full_path, "r", encoding="utf-8") as file:
            content = file.read()
        prompt = f"Please analyze or summarize this note:\n\n{content}"
        reply = chat_with_gpt(prompt)
        print("\n--- ChatGPT Response ---\n")
        print(reply)
        print("\n------------------------\n")
    elif len(matches) > 1:
        error("ambiguous_file", filename=search_name)
        for match in matches:
            print(f" - {match}")
        error("specify_full_path", example="upload folder1/note.md")
    else:
        error("file_not_found", filename=search_name)


def list_md_files(vaults, current_vault, error):
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return []
    path = vaults[current_vault]
    md_files = []
    for root, dirs, files in os.walk(path):
        if "GMAssistantVault" in path and "templates" in root:
            continue
        for file in files:
            if file.endswith('.md'):
                rel_dir = os.path.relpath(root, path)
                rel_file = os.path.join(rel_dir, file) if rel_dir != "." else file
                md_files.append(rel_file)
    return md_files

def read_md_file(filename, vaults, current_vault, error):
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return ""
    path = vaults[current_vault]
    full_path = os.path.join(path, filename)
    with open(full_path, "r", encoding="utf-8") as file:
        return file.read()

def cmd_createnote(args, vaults, current_vault, prompt_input):
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

def cmd_tree(args, vaults, current_vault, error):
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
        for d in dirs:
            pass
        for f in files:
            if f.endswith(".md"):
                print(f"{indent}📄 {f}")
