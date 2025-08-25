import re
import yaml
import pathlib
import argparse

def read_lines(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def looks_like_start(lines, i, rule):
    name_pat = re.compile(rule["start"]["name_pattern"])
    line = lines[i].strip()
    if not name_pat.match(line):
        return False
    look = int(rule["start"].get("lookahead_lines", 5))
    window = "\n".join(lines[i+1:i+1+look])
    for pat in rule["start"].get("must_contain_next_lines", []):
        if not re.search(pat, window, re.IGNORECASE | re.MULTILINE):
            return False
    return True

def extract_fields(text: str, fields: dict) -> dict:
    out = {}
    for key, pat in fields.items():
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            out[key] = m.group(1).strip()
    return out

def chunk_with_rule(lines, rule, meta):
    # find candidate starts
    starts = [i for i in range(len(lines)) if looks_like_start(lines, i, rule)]
    chunks = []
    for idx, i in enumerate(starts):
        j = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block_lines = lines[i:j]
        title = block_lines[0].strip()
        block_text = "\n".join(block_lines).strip()
        fields = extract_fields(block_text, rule.get("fields", {}))

        fm = {
            "id": f"{meta['system']}--{rule['type']}--{slug(title)}",
            "system": meta["system"],
            "type": rule["type"],
            "source": meta.get("source"),
            "license": meta.get("license"),
            "title": title,
            "tags": rule.get("tags", []),
            **fields,
        }
        chunks.append((title, fm, block_text))
    return chunks

def write_markdown(out_dir: pathlib.Path, title: str, frontmatter: dict, body: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug(title)}.md"
    import io
    import yaml as _yaml
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n")
        _yaml.safe_dump(frontmatter, f, sort_keys=False, allow_unicode=True)
        f.write("---\n\n")
        f.write(f"# {frontmatter.get('title', title)}\n\n")
        f.write(body.strip() + "\n")
    return path

def main():
    ap = argparse.ArgumentParser(description="Chunk SRD plain text into Markdown using YAML rules.")
    ap.add_argument("--text", required=True, help="Input text file (from pdftotext).")
    ap.add_argument("--rules", required=True, help="YAML rules file.")
    ap.add_argument("--out", required=True, help="Output folder for Markdown files.")
    ap.add_argument("--only", help="Only run a specific rule type (e.g., monster, spell).")
    args = ap.parse_args()

    lines = read_lines(args.text)
    rules_doc = yaml.safe_load(open(args.rules, "r", encoding="utf-8"))
    meta = {
        "system": rules_doc.get("system", "unknown"),
        "source": rules_doc.get("source"),
        "license": rules_doc.get("license"),
    }
    rules = rules_doc.get("rules", [])

    out_root = pathlib.Path(args.out)
    total = 0
    for rule in rules:
        if args.only and rule.get("type") != args.only:
            continue
        print(f"→ Chunking rule: {rule.get('type')}")
        chunks = chunk_with_rule(lines, rule, meta)
        rule_out = out_root / rule["type"]
        for title, fm, body in chunks:
            write_markdown(rule_out, title, fm, body)
        print(f"   - wrote {len(chunks)} files to {rule_out}")
        total += len(chunks)

    print(f"\n✅ Done. Total files written: {total}")

if __name__ == "__main__":
    main()
