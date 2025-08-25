# core/search_index.py

import os
import yaml
import json
import re


def extract_frontmatter(content):
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            fm_text = content[3:end].strip()
            try:
                return yaml.safe_load(fm_text)
            except Exception:
                return {}
    return {}


def extract_inline_tags(content):
    return list(set(re.findall(r'#(\w+)', content)))


def build_search_index(vault_path):
    index = []
    for root, _, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, vault_path)
                with open(full_path, encoding="utf-8") as f:
                    content = f.read()
                fm = extract_frontmatter(content)
                inline_tags = extract_inline_tags(content)
                entry = {
                    "id": fm.get("id", rel_path.replace(".md", "")),
                    "path": rel_path,
                    "title": fm.get("title", os.path.splitext(file)[0]),
                    "tags": list(set(fm.get("tags", []) + inline_tags)),
                    "system": fm.get("system"),
                    "type": fm.get("type"),
                }
                index.append(entry)
    return index


def save_index(index, path="index.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def load_index(path="index.json"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def search_index(index, query):
    terms = query.strip().split()
    results = index
    for term in terms:
        if ":" in term:
            key, value = term.split(":", 1)
            results = [entry for entry in results if str(entry.get(key)) == value]
        else:
            results = [entry for entry in results if term.lower() in entry["title"].lower()]
    return results


def cmd_search(args, vaults, current_vault, error):
    if not current_vault or current_vault not in vaults:
        error("no_vault")
        return

    vault_path = vaults[current_vault]
    index = build_search_index(vault_path)
    results = search_index(index, args)

    if not results:
        print("No matches found.")
        return

    for r in results:
        print(f"- {r['title']} ({r['path']}) [tags: {', '.join(r['tags'])}]")
