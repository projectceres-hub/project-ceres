import argparse, pathlib, re, yaml
from bs4 import BeautifulSoup
from markdownify import markdownify as md

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def main():
    parser = argparse.ArgumentParser(description="Convert HTML SRD to Obsidian-compatible Markdown")
    parser.add_argument("--input", required=True, help="Path to HTML file (converted from PDF)")
    parser.add_argument("--output", required=True, help="Destination folder for Markdown files")
    parser.add_argument("--system", required=True, help="System ID (e.g., dnd-5e, pathfinder-2e)")
    parser.add_argument("--type", required=True, help="Content type (e.g., monster, spell)")
    parser.add_argument("--source", required=True, help="Source text version (e.g., SRD 5.1)")
    parser.add_argument("--license", required=True, help="License identifier (e.g., CC-BY-4.0)")
    parser.add_argument("--selector", default="h3", help="CSS selector for splitting entries (default: h3)")

    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    for header in soup.select(args.selector):
        title = header.get_text().strip()
        body_nodes = []
        for sibling in header.next_siblings:
            if getattr(sibling, "name", "") == args.selector:
                break
            body_nodes.append(str(sibling))

        markdown_body = md("".join(body_nodes))
        file_slug = slugify(title)
        frontmatter = {
            "id": f"{args.system}--{args.type}--{file_slug}",
            "system": args.system,
            "type": args.type,
            "source": args.source,
            "license": args.license,
            "tags": ["srd", args.type, args.system]
        }

        with open(out / f"{file_slug}.md", "w", encoding="utf-8") as md_file:
            md_file.write(f"---\n{yaml.safe_dump(frontmatter)}---\n# {title}\n\n{markdown_body}\n")

    print(f"✅ Converted {len(list(out.glob('*.md')))} records to {out}")

if __name__ == "__main__":
    main()